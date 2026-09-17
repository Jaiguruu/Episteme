"""Stage 6: resolve observed references into edges to real symbols.

The resolver is a pure function of the model. It reads symbols, relationships and
bindings, and returns a new set of relationships -- it never parses, never reads
the filesystem, and never calls a language. That is what keeps it on the semantic
side of the tier boundary.

Section 4.2 governs everything here: **an explicit unresolved edge is preferred
over an incorrect confident edge.** Every rung that cannot reach certainty returns
UNRESOLVED or AMBIGUOUS rather than a best guess, and AC5 asserts the property
directly -- the resolver may never invent a target that no syntax justified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from ..core.contracts import SemanticIR, Relationship, Symbol
from ..core.enums import RelationshipType, ResolutionStatus
from .ladder import INSTANCE_RECEIVERS, ResolutionRung, resolve_qualified_name


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------


@dataclass
class _ModelIndex:
    """Lookup structures built once per model, so resolution stays linear."""

    symbols: dict[str, Symbol]
    #: qualified_name -> symbols with that name (a list, because a name is not a key)
    by_qualified_name: dict[str, list[Symbol]] = field(default_factory=dict)
    #: simple name -> symbols with that simple name
    by_name: dict[str, list[Symbol]] = field(default_factory=dict)
    #: file_id -> symbols declared in that file
    by_file: dict[str, list[Symbol]] = field(default_factory=dict)
    #: qualified_name of the containing class -> its members
    members_of: dict[str, list[Symbol]] = field(default_factory=dict)
    #: symbol_id -> the qualified name of its enclosing class, if any
    owner_class: dict[str, str] = field(default_factory=dict)
    #: file_id -> module qualified names imported by that file
    imports_of: dict[str, list[str]] = field(default_factory=dict)
    #: every qualified name in the model, for prefix matching
    names: frozenset[str] = frozenset()

    @classmethod
    def build(cls, ir: SemanticIR) -> "_ModelIndex":
        index = cls(symbols={s.id: s for s in ir.symbols})
        for symbol in ir.symbols:
            index.by_qualified_name.setdefault(symbol.qualified_name, []).append(symbol)
            index.by_name.setdefault(symbol.name, []).append(symbol)
            index.by_file.setdefault(symbol.file_id, []).append(symbol)

        # Class membership. A member's qualified name is ``pkg.mod:Class.member``,
        # so the owner is the text before the last dot *within the part after the
        # colon*. This is the one structural convention the extractor guarantees,
        # and it is language-neutral: it describes nesting, not grammar.
        for symbol in ir.symbols:
            owner = _enclosing_class_name(symbol)
            if owner is not None:
                index.members_of.setdefault(owner, []).append(symbol)
                index.owner_class[symbol.id] = owner

        for relationship in ir.relationships:
            if relationship.relationship_type is not RelationshipType.IMPORTS:
                continue
            source = index.symbols.get(relationship.source_symbol_id)
            if source is None or not relationship.target_name:
                continue
            # An IMPORTS edge is emitted from the module symbol of a file, so
            # attribute every import in the file to that file id.
            index.imports_of.setdefault(source.file_id, []).append(
                relationship.target_name
            )

        index.names = frozenset(index.by_qualified_name)
        return index


def _enclosing_class_name(symbol: Symbol) -> str | None:
    """The qualified name of the class a member belongs to, if it is nested.

    ``services.payment_service:PaymentService.process`` -> ``...:PaymentService``.
    A module symbol, or a top-level function, has no owner and returns ``None``.
    """
    qualified = symbol.qualified_name
    if ":" not in qualified:
        return None
    module, _, local = qualified.partition(":")
    if "." not in local:
        return None
    return f"{module}:{local.rsplit('.', 1)[0]}"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class ResolutionReport:
    """What one resolution pass did, rung by rung.

    Kept deliberately separate from the model: the rung is *evidence about the
    resolver*, not an attribute of an edge, and persisting it would tie the model
    schema to the algorithm that produced it.
    """

    counts: dict[ResolutionRung, int] = field(default_factory=dict)
    resolved: int = 0
    ambiguous: int = 0
    unresolved: int = 0
    #: Edges whose target changed, for a reuse/re-resolution diff.
    retargeted: int = 0

    def record(self, rung: ResolutionRung) -> None:
        self.counts[rung] = self.counts.get(rung, 0) + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "by_rung": {
                rung.value: self.counts[rung]
                for rung in sorted(self.counts, key=lambda r: r.order)
            },
            "resolved": self.resolved,
            "ambiguous": self.ambiguous,
            "unresolved": self.unresolved,
            "retargeted": self.retargeted,
        }


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class Resolver:
    """Resolves a model's observed edges, in place, deterministically."""

    def __init__(self, ir: SemanticIR) -> None:
        self.ir = ir
        self.index = _ModelIndex.build(ir)

    # -- entry point ------------------------------------------------------

    def resolve(self) -> ResolutionReport:
        """Upgrade every resolvable edge. Returns the run's report."""
        report = ResolutionReport()
        for relationship in self.ir.relationships:
            if relationship.relationship_type not in _RESOLVABLE:
                continue
            before = relationship.target_symbol_id
            self._resolve_one(relationship, report)
            if relationship.target_symbol_id != before:
                report.retargeted += 1
        self._tally(report)
        return report

    # -- the ladder -------------------------------------------------------

    def _resolve_one(
        self, relationship: Relationship, report: ResolutionReport
    ) -> None:
        """Try each rung in order and stop at the first that answers."""
        source = self.index.symbols.get(relationship.source_symbol_id)
        if source is None or not relationship.target_name:
            # Nothing to work with; leave the edge exactly as it was found.
            report.record(ResolutionRung.NONE)
            return

        name = relationship.target_name
        # Strip any call syntax the raw text may still carry. The extractor
        # captures the callee expression; a trailing ``()`` is not part of a name.
        lookup = name.split("(", 1)[0].strip()
        if not lookup:
            report.record(ResolutionRung.NONE)
            return

        rung, candidates = self._walk_ladder(lookup, source, relationship)
        self._apply(relationship, rung, candidates, report)

    def _walk_ladder(
        self, name: str, source: Symbol, relationship: Relationship
    ) -> tuple[ResolutionRung, list[Symbol]]:
        head = name.split(".", 1)[0]

        # S2/S3: an instance receiver. ``self.validate`` is a member of the class
        # the caller lives in; ``self.payment_service.process`` needs the binding.
        if head in INSTANCE_RECEIVERS:
            return self._resolve_receiver_chain(name, source)

        # S1: same file, exact name. The narrowest scope available.
        local = self._same_file(source, name)
        if local is not None:
            return ResolutionRung.SAME_FILE_EXACT, [local]

        # S4: a symbol in a module this file imports.
        imported = self._imported(source, name)
        if imported:
            return ResolutionRung.IMPORTED_MODULE_SYMBOL, imported

        # S5/S6: anywhere in the model, by uniqueness.
        unique = self._unique_in_model(name)
        if unique[0] is not ResolutionRung.NONE:
            return unique

        # S7/S8: a dotted name whose head we may still be able to place.
        if "." in name:
            rung, qnames = resolve_qualified_name(name, self.index.names)
            if rung is not ResolutionRung.NONE:
                resolved = [
                    symbol
                    for qname in qnames
                    for symbol in self.index.by_qualified_name.get(qname, [])
                ]
                if resolved:
                    return rung, resolved
            # A chain that could not be placed is still reported as such.
            return ResolutionRung.NONE, []

        return ResolutionRung.NONE, []

    def _resolve_receiver_chain(
        self, name: str, source: Symbol
    ) -> tuple[ResolutionRung, list[Symbol]]:
        """Handle ``self.x``, ``self.m()`` and ``self.x.m()``.

        ``self.m()`` is a member of the caller's own class (S2). ``self.x.m()``
        needs the declared type of ``x``, which is a ``Binding`` (S3) -- this is
        exactly the path D23/D34 exist to make possible.
        """
        parts = name.split(".")

        # ``self.member`` -- the owner class is known from the enclosing symbol,
        # so this is a closed-set lookup and certain.
        if len(parts) == 2:
            owner = self.index.owner_class.get(source.id)
            if owner is None:
                return ResolutionRung.NONE, []
            member = self._member_of(owner, parts[1])
            if member is not None:
                return ResolutionRung.RECEIVER_CLASS_MEMBER, [member]
            # Not a declared member. Fall through to the weak rungs rather than
            # guessing, because the class may inherit it from a base we can see.
            inherited = self._inherited_member(source, owner, parts[1])
            if inherited is not None:
                return ResolutionRung.RECEIVER_CLASS_MEMBER, [inherited]
            return ResolutionRung.NONE, []

        # ``self.receiver.member`` -- resolve ``receiver`` through its binding.
        if len(parts) >= 3:
            receiver, member = parts[1], parts[-1]
            type_name = self._bound_type_of(source, receiver)
            if type_name is None:
                return ResolutionRung.NONE, []
            type_symbols = self._class_named(type_name)
            if not type_symbols:
                return ResolutionRung.NONE, []
            if len(type_symbols) > 1:
                # Same type name in two modules: ambiguous, and we say so.
                candidates = [
                    symbol
                    for type_symbol in type_symbols
                    for symbol in self.index.members_of.get(
                        type_symbol.qualified_name, []
                    )
                    if symbol.name == member
                ]
                if candidates:
                    return ResolutionRung.ATTRIBUTE_CHAIN_AMBIGUOUS, candidates
                return ResolutionRung.NONE, []
            owner = type_symbols[0].qualified_name
            found = self._member_of(owner, member)
            if found is not None:
                return ResolutionRung.BOUND_TYPE_MEMBER, [found]
            inherited = self._inherited_member(source, owner, member)
            if inherited is not None:
                return ResolutionRung.BOUND_TYPE_MEMBER, [inherited]
            return ResolutionRung.NONE, []

        return ResolutionRung.NONE, []

    # -- rung helpers -----------------------------------------------------

    def _same_file(self, source: Symbol, name: str) -> Symbol | None:
        """A symbol declared in the caller's file whose name matches exactly."""
        matches = [
            symbol
            for symbol in self.index.by_file.get(source.file_id, [])
            if symbol.name == name or symbol.qualified_name.endswith(f":{name}")
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def _imported(self, source: Symbol, name: str) -> list[Symbol]:
        """Symbols matching ``name`` in a module this file imports.

        Handles both ``Payment`` (imported from ``models.payment``) and
        ``service.checkout`` (an import chain whose head names a module). The
        match is on the *simple* name against the imported module's symbols, which
        is what an author means by writing an imported name in a call.
        """
        imported_modules = self.index.imports_of.get(source.file_id, [])
        if not imported_modules:
            return []

        matches: list[Symbol] = []
        head, _, tail = name.partition(".")
        for module_name in imported_modules:
            symbols = [
                symbol
                for symbol in self.index.by_file.get(
                    self._file_id_of_module(module_name), []
                )
            ]
            for symbol in symbols:
                if tail:
                    # ``service.checkout`` -- the tail must be a member of the
                    # imported module (or of a class named by the head).
                    if symbol.name == tail and (
                        symbol.qualified_name.startswith(f"{module_name}:")
                    ):
                        matches.append(symbol)
                elif symbol.name == head or symbol.qualified_name.endswith(
                    f":{head}"
                ):
                    matches.append(symbol)
        unique: dict[str, Symbol] = {symbol.id: symbol for symbol in matches}
        return list(unique.values())

    def _file_id_of_module(self, module_name: str) -> str:
        """The file id of a module symbol, or a value that matches nothing."""
        for symbol in self.index.by_qualified_name.get(module_name, []):
            return symbol.file_id
        return ""

    def _unique_in_model(
        self, name: str
    ) -> tuple[ResolutionRung, list[Symbol]]:
        """A name that appears exactly once in the whole model resolves (S5)."""
        simple = name.rsplit(".", 1)[-1] if "." in name else name
        matches = self.index.by_name.get(simple, [])
        if len(matches) == 1:
            return ResolutionRung.UNIQUE_IN_MODEL, list(matches)
        if len(matches) > 1:
            # Several equally plausible targets. Marked, with the candidates,
            # never guessed (AC3, D26).
            return ResolutionRung.AMBIGUOUS_IN_MODEL, list(matches)
        return ResolutionRung.NONE, []

    def _bound_type_of(self, source: Symbol, receiver: str) -> str | None:
        """The declared type of ``receiver`` as seen from ``source``.

        Two scopes can apply, and the narrower wins: a binding in the caller's own
        body (a local), then one in the class constructor (an instance attribute,
        which is where ``self.x = ...`` is recorded). If both exist and disagree,
        the local wins because it is closer to the call site.

        An unannotated alias is followed one hop. ``self.repository = repository``
        records the type as the literal text ``repository``, which is the name of
        another bound thing rather than a class; when that name is itself bound in
        the same constructor, its type is the answer. This is how the common
        constructor-injection shape resolves, and it is language-neutral -- it says
        "a type name that is also a bound name is an alias", not anything about
        Python.
        """
        owners = [source.id]
        constructor = self._constructor_of(source)
        if constructor is not None:
            owners.append(constructor.id)

        # Several bindings can share a name in one scope: ``def __init__(self,
        # repository: PaymentRepository)`` produces both a PARAMETER binding
        # carrying the real type and an INSTANCE binding for ``self.repository =
        # repository`` carrying the literal text ``repository``. Taking the first
        # match would pick whichever the extractor happened to emit first, so pick
        # by declared quality instead: an annotated type wins over a self-named
        # alias.
        candidates: list[str] = []
        for owner_id in owners:
            for binding in self.ir.bindings:
                if binding.enclosing_symbol_id != owner_id:
                    continue
                if binding.bound_name != receiver:
                    continue
                candidates.append(binding.type_name)

        best = self._best_type_name(candidates, receiver)
        if best is None:
            return None

        # Follow the alias, bounded so a cycle cannot spin.
        seen: set[str] = set()
        while best not in seen and not self._class_named(best):
            seen.add(best)
            aliased = self._binding_named(best, owners)
            if aliased is None or aliased == best:
                break
            best = aliased
        return best

    @staticmethod
    def _best_type_name(candidates: list[str], receiver: str) -> str | None:
        """Pick the most informative of several types recorded for one name.

        A binding whose type text equals the bound name is the signature of an
        unannotated alias -- ``self.repository = repository`` is recorded as
        ``repository: repository`` -- and carries no type information. It is
        therefore the last resort, and a declared type in the same scope wins.
        """
        usable = [name for name in candidates if name]
        if not usable:
            return None
        declared = [name for name in usable if name != receiver]
        return declared[0] if declared else usable[0]

    def _binding_named(self, name: str, owner_ids: list[str]) -> str | None:
        """The declared type of a binding called ``name`` in any of these scopes."""
        for owner_id in owner_ids:
            for binding in self.ir.bindings:
                if binding.enclosing_symbol_id == owner_id and binding.bound_name == name:
                    return binding.type_name
        return None

    def _constructor_of(self, source: Symbol) -> Symbol | None:
        owner = self.index.owner_class.get(source.id)
        if owner is None:
            return None
        for symbol in self.index.members_of.get(owner, []):
            if symbol.name in {"__init__", "constructor", "new"}:
                return symbol
        return None

    def _class_named(self, type_name: str) -> list[Symbol]:
        """Symbols whose *class* name matches ``type_name``.

        The binding records the type as written, which may or may not be
        qualified. Both forms are accepted; more than one match is reported rather
        than broken by an arbitrary pick.
        """
        simple = type_name.rsplit(".", 1)[-1]
        matches = [
            symbol
            for symbol in self.index.by_name.get(simple, [])
            if str(symbol.symbol_type) in {"CLASS", "INTERFACE", "STRUCT", "ENUM", "TRAIT"}
        ]
        if matches:
            return matches
        # A generic like ``Optional[Payment]`` -- take the inner name.
        if "[" in type_name:
            inner = type_name[type_name.index("[") + 1 : type_name.rindex("]")]
            return self._class_named(inner)
        return []

    def _member_of(self, owner_qualified_name: str, member: str) -> Symbol | None:
        for symbol in self.index.members_of.get(owner_qualified_name, []):
            if symbol.name == member:
                return symbol
        return None

    def _inherited_member(
        self, source: Symbol, owner_qualified_name: str, member: str
    ) -> Symbol | None:
        """Look for ``member`` on a class this one inherits from.

        Deliberately one level of indirection: enough to resolve the common
        ``Base.validate`` case, and shallow enough that the edge it produces is
        still traceable to a declared relationship rather than to a search.
        """
        source_symbol = next(
            (
                symbol
                for symbol in self.index.by_qualified_name.get(
                    owner_qualified_name, []
                )
            ),
            None,
        )
        if source_symbol is None:
            return None
        for relationship in self.ir.relationships:
            if relationship.source_symbol_id != source_symbol.id:
                continue
            if relationship.relationship_type is not RelationshipType.INHERITS:
                continue
            target_name = relationship.target_name
            if not target_name:
                continue
            for base in self._class_named(target_name):
                found = self._member_of(base.qualified_name, member)
                if found is not None:
                    return found
        return None

    # -- applying a result ------------------------------------------------

    def _apply(
        self,
        relationship: Relationship,
        rung: ResolutionRung,
        candidates: list[Symbol],
        report: ResolutionReport,
    ) -> None:
        """Write a rung's answer onto the edge, or record why there wasn't one."""
        report.record(rung)

        if rung is ResolutionRung.NONE or not candidates:
            # D29: leave it explicitly unresolved. Keep target_name (D25) so the
            # ID stays stable and the raw text stays available for a later pass.
            relationship.resolution_status = ResolutionStatus.UNRESOLVED
            relationship.confidence = 0.0
            relationship.candidate_symbol_ids = []
            return

        relationship.resolution_status = rung.status
        relationship.confidence = rung.confidence

        if rung.status is ResolutionStatus.AMBIGUOUS:
            # D28: an ambiguous edge keeps its placeholder target, so edge counts
            # do not inflate and a caller must consult resolution_status before
            # trusting target_symbol_id.
            #
            # The candidate list is capped. It exists so a reader can *act* on the
            # ambiguity, and 135 ids for a name that is simply common across 18
            # generated modules is not actionable -- it is a payload. The cap
            # keeps the marker honest (the edge is still AMBIGUOUS) while the
            # stored list only claims to be a bounded set of the closest
            # candidates, which is what ``candidate_symbol_ids`` documents.
            ordered = sorted(
                candidates, key=lambda s: (s.file_id, s.qualified_name, s.id)
            )
            relationship.candidate_symbol_ids = [
                symbol.id for symbol in ordered[:MAX_CANDIDATES]
            ]
            return

        # Exact: point at the winner, deterministically.
        winner = sorted(candidates, key=lambda s: (s.qualified_name, s.id))[0]
        relationship.target_symbol_id = winner.id
        relationship.candidate_symbol_ids = []

    def _tally(self, report: ResolutionReport) -> None:
        for relationship in self.ir.relationships:
            status = relationship.resolution_status
            if status in (
                ResolutionStatus.RESOLVED_EXACT,
                ResolutionStatus.RESOLVED_HEURISTIC,
            ):
                report.resolved += 1
            elif status is ResolutionStatus.AMBIGUOUS:
                report.ambiguous += 1
            elif status is ResolutionStatus.UNRESOLVED:
                report.unresolved += 1


#: Only these edge types carry a resolvable target. CONTAINS is structural and
#: already exact; inventing rungs for it would be scope for no benefit.
_RESOLVABLE = frozenset(
    {RelationshipType.CALLS, RelationshipType.IMPORTS, RelationshipType.INHERITS}
)

#: Upper bound on the candidates recorded for an ambiguous edge (D26).
#:
#: Chosen so the list stays readable in a report and cheap to serialise, while
#: still naming enough targets to disambiguate a real case. A name common across
#: every generated module in a large repository can match hundreds of symbols, and
#: storing all of them turns a diagnostic into a payload without helping anyone.
MAX_CANDIDATES: Final[int] = 8


def resolve_ir(ir: SemanticIR) -> ResolutionReport:
    """Resolve ``ir`` in place and return the report. Convenience wrapper."""
    return Resolver(ir).resolve()
