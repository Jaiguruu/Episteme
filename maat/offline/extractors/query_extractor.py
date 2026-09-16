"""Stage 4 — the query-driven extractor.

One implementation serves all 18 languages. What differs between languages is
the ``.scm`` query file; what stays identical is everything here.

Three mechanisms are worth understanding, because they are what make a single
engine work across grammars that agree on almost nothing:

**Pairing by match.** Each definition pattern captures the declaration node with
``@def.*`` and its identifier with ``@name.*`` in the same pattern, so a query
*match* carries both. This matters because the name node's parent is frequently
not the declaration node -- in C the identifier sits inside a ``function_declarator``,
in Go a method name is a ``field_identifier`` inside a ``method_declaration``.
Pairing per match avoids needing to know any of that.

**Nesting by span containment.** tree-sitter gives every node a byte range, and
declaration ranges are properly nested. So a declaration's parent is simply the
innermost other declaration whose range contains it -- no per-language list of
"container node types" required. This is what produces qualified names and
``CONTAINS`` edges.

**Reclassification by context.** Some grammars cannot distinguish a top-level
function from a method in the query itself (Kotlin, Swift, Scala, Dart and C++
all use one ``function_declaration``-style node in both positions). Rather than
encode per-language rules, the extractor reclassifies: a function whose nearest
enclosing declaration is a class, interface or enum becomes a method. That is
true in every language in the registry, so the rule needs no exceptions.
"""

from __future__ import annotations

import bisect
from functools import lru_cache
from typing import Any

import tree_sitter as ts

from ...core.contracts import Diagnostic
from ...core.enums import RECOVERY_NONE, BindingScope, DiagnosticSeverity, SymbolType
from ...core.locations import SourceSpan
from .. import languages
from ..parser import GrammarUnavailableError, ParseOutcome, load_grammar
from .base import (
    INSTANCE_RECEIVER_TOKENS,
    BindingFact,
    CallFact,
    ExtractionFacts,
    ImportFact,
    InheritFact,
    SymbolFact,
    looks_like_identifier,
    module_path_for,
    module_symbol_name,
)

#: Capture prefix -> symbol type.
DEF_CAPTURES: dict[str, SymbolType] = {
    "def.class": SymbolType.CLASS,
    "def.interface": SymbolType.INTERFACE,
    "def.enum": SymbolType.ENUM,
    "def.function": SymbolType.FUNCTION,
    "def.method": SymbolType.METHOD,
    "def.constructor": SymbolType.CONSTRUCTOR,
    "def.field": SymbolType.FIELD,
    "def.type": SymbolType.TYPE_ALIAS,
    "def.module": SymbolType.MODULE,
}

#: Containers that turn a nested function into a method.
METHOD_CONTAINERS = frozenset(
    {SymbolType.CLASS, SymbolType.INTERFACE, SymbolType.ENUM}
)

#: Maximum length of a stored signature line.
MAX_SIGNATURE_CHARS = 200

#: Maximum length of stored documentation.
MAX_DOC_CHARS = 1200

#: Leading markers stripped when cleaning a documentation comment.
DOC_PREFIXES: tuple[str, ...] = (
    "///", "//!", "//", "/**", "/*", "*", "#", "--", ";;", "%", "\\",
)

#: Lines that are decorators/annotations rather than the declaration itself.
DECORATOR_PREFIXES: tuple[str, ...] = ("@", "#", "[", "///", "//", "/*", "*")


class QueryUnavailableError(RuntimeError):
    """No extraction query exists for this language."""


# ---------------------------------------------------------------------------
# Query loading
# ---------------------------------------------------------------------------


@lru_cache(maxsize=128)
def _load_query(language: str) -> Any:
    """Compile and cache the extraction query for a language."""
    path = languages.extraction_query_path(language)
    if path is None:
        raise QueryUnavailableError(
            f"no extraction query for language {language!r}"
        )
    source = path.read_text(encoding="utf-8")
    try:
        return ts.Query(load_grammar(language), source)
    except GrammarUnavailableError as error:
        raise QueryUnavailableError(
            f"grammar for {language!r} could not be loaded: {error}"
        ) from error
    except Exception as error:  # noqa: BLE001
        raise QueryUnavailableError(
            f"extraction query for {language!r} failed to compile: {error}"
        ) from error


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _clean_doc(raw: str) -> str:
    """Strip comment markers and quotes from a documentation node."""
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        for prefix in DOC_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].strip()
                break
        for quote in ('"""', "'''", '"', "'"):
            if stripped.startswith(quote) and stripped.endswith(quote) and len(stripped) > 2:
                stripped = stripped[len(quote): -len(quote)].strip()
                break
        lines.append(stripped)
    text = "\n".join(lines).strip()
    return text[:MAX_DOC_CHARS]


def _signature_of(node: Any, source: bytes) -> str:
    """First meaningful line of a declaration.

    Decorator and annotation lines are skipped, because for a decorated Python
    function the captured node starts at the decorator, and a signature of
    ``@staticmethod`` tells a reader nothing.
    """
    text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(p) for p in DECORATOR_PREFIXES):
            continue
        return stripped[:MAX_SIGNATURE_CHARS]
    return ""


# ---------------------------------------------------------------------------
# The extractor
# ---------------------------------------------------------------------------


class QueryExtractor:
    """Extract facts from a parse outcome using a declarative query."""

    def extract(self, outcome: ParseOutcome, file_path: str) -> ExtractionFacts:
        language = outcome.language or ""
        module_path = module_path_for(file_path, language)
        facts = ExtractionFacts(
            file_path=file_path,
            language=language,
            module_qualified_name=module_path,
            module_name=module_symbol_name(module_path),
        )

        # The module is always a symbol, even for a file with nothing in it.
        # It gives top-level statements somewhere to attach, so a top-level call
        # is never orphaned, and it makes an empty file's parse status
        # meaningful rather than producing an empty model entry.
        facts.symbols.append(
            SymbolFact(
                name=facts.module_name,
                symbol_type=SymbolType.MODULE,
                qualified_name=module_path,
                span=SourceSpan.whole_file(_line_count(outcome.source)),
                signature=None,
                documentation=None,
                parent_qualified_name=None,
            )
        )

        if outcome.tree is None:
            return facts

        try:
            query = _load_query(language)
        except QueryUnavailableError as error:
            facts.diagnostics.append(
                Diagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="extract.no_query",
                    message=(
                        f"{error}. The file was parsed but yields no symbols; "
                        "add a query file to maat/offline/queries/ to enable extraction."
                    ),
                    file_path=file_path,
                    language=language,
                    recovery_action=RECOVERY_NONE,
                )
            )
            return facts

        matches = ts.QueryCursor(query).matches(outcome.tree.root_node)

        declarations: dict[int, tuple[Any, SymbolType, str]] = {}
        import_captures: list[tuple[Any, str, str]] = []
        # (callee node, receiver node or None, is member call)
        call_matches: list[tuple[Any, Any | None, bool]] = []
        inherit_nodes: list[Any] = []
        doc_nodes: list[Any] = []
        # (name node, type node, receiver node or None, statement node, is param)
        binding_matches: list[tuple[Any, Any, Any | None, Any | None, bool]] = []

        # matches() yields (pattern_index, {capture_name: [node, ...]}). The
        # values are *lists*: one pattern can bind a capture several times, as
        # when a class has multiple base classes. Taking only the first node of
        # each capture would silently drop every base after the first, so the
        # loop below is careful to iterate the lists where multiplicity is real.
        for _pattern_index, capture_map in matches:

            def first(capture: str, _map: dict[str, list[Any]] = capture_map) -> Any | None:
                nodes = _map.get(capture)
                return nodes[0] if nodes else None

            # --- definitions -------------------------------------------------
            for capture_name, symbol_type in DEF_CAPTURES.items():
                node = first(capture_name)
                if node is None:
                    continue
                suffix = capture_name.split(".", 1)[1]
                name_node = first(f"name.{suffix}")
                name = (
                    outcome.text_of(name_node).strip()
                    if name_node is not None
                    else outcome.text_of(node).strip()[:MAX_SIGNATURE_CHARS]
                )
                if not name:
                    continue
                # Keyed by node id so a declaration matched by two patterns is
                # recorded once.
                declarations.setdefault(node.id, (node, symbol_type, name))

            # --- imports -----------------------------------------------------
            for capture_name, kind in (
                ("import.module", "module"),
                ("import.name", "name"),
                ("import.alias", "alias"),
            ):
                for node in capture_map.get(capture_name, []):
                    text = outcome.text_of(node).strip()
                    if text:
                        import_captures.append((node, kind, text))

            # --- calls -------------------------------------------------------
            callee_node = first("call.fn")
            is_member = False
            if callee_node is None:
                callee_node = first("call.attr")
                is_member = callee_node is not None
            if callee_node is not None:
                call_matches.append((callee_node, first("call.recv"), is_member))

            # --- inheritance -------------------------------------------------
            inherit_nodes.extend(capture_map.get("inherit", []))

            # --- bindings ----------------------------------------------------
            # @bind.param marks a parameter binding; @bind.name a local or
            # instance one. The query decides which, so no language-specific
            # node type appears here.
            param_node = first("bind.param")
            binding_name = param_node if param_node is not None else first("bind.name")
            if binding_name is not None:
                binding_matches.append(
                    (
                        binding_name,
                        first("bind.type"),
                        first("bind.receiver"),
                        first("bind.assign"),
                        param_node is not None,
                    )
                )

            # --- documentation ----------------------------------------------
            doc_nodes.extend(capture_map.get("doc", []))

        # No early return here even when no declarations were found. A file can
        # legitimately contain imports, calls or inheritance without declaring
        # anything -- `import ujson as json` alone is such a file -- and bailing
        # out would silently drop them. With no declarations the containment
        # tree is just the module root, and everything attaches to it.

        # --- build the declaration tree by span containment -------------------
        # The module is modelled as the outermost declaration rather than being
        # special-cased. That single choice makes three things fall out for
        # free: top-level symbols acquire a parent, module-level docstrings have
        # somewhere to attach, and the containment walk needs no exceptions.
        root_node = outcome.tree.root_node
        module_fact = facts.symbols[0]

        ordered = sorted(
            declarations.values(), key=lambda item: (item[0].start_byte, -item[0].end_byte)
        )
        ordered.append((root_node, SymbolType.MODULE, facts.module_name))
        ordered.sort(key=lambda item: (item[0].start_byte, -item[0].end_byte))
        starts = [item[0].start_byte for item in ordered]

        parent_of: dict[int, Any | None] = {}
        stack: list[Any] = []
        for node, _symbol_type, _name in ordered:
            while stack and not (
                stack[-1].start_byte <= node.start_byte and node.end_byte <= stack[-1].end_byte
            ):
                stack.pop()
            parent_of[node.id] = stack[-1] if stack else None
            stack.append(node)

        # --- qualified names --------------------------------------------------
        symbol_of_node: dict[int, SymbolFact] = {root_node.id: module_fact}

        for node, symbol_type, name in ordered:
            if node.id == root_node.id:
                continue

            parent_node = parent_of.get(node.id)
            # A top-level declaration's parent is the file root, which *is* the
            # module. It is treated as "no enclosing symbol" so the qualified
            # name takes the `module:Symbol` form instead of `module.Symbol`.
            if parent_node is None or parent_node.id == root_node.id:
                parent_fact = None
            else:
                parent_fact = symbol_of_node.get(parent_node.id)

            if parent_fact is None:
                qualified_name = f"{module_path}:{name}"
                parent_qualified_name = module_path
            else:
                qualified_name = f"{parent_fact.qualified_name}.{name}"
                parent_qualified_name = parent_fact.qualified_name

            # A function declared inside a class is a method, whatever the
            # query called it.
            if (
                symbol_type is SymbolType.FUNCTION
                and parent_fact is not None
                and parent_fact.symbol_type in METHOD_CONTAINERS
            ):
                symbol_type = SymbolType.METHOD

            fact = SymbolFact(
                name=name,
                symbol_type=symbol_type,
                qualified_name=qualified_name,
                span=SourceSpan.from_tree_sitter(node),
                signature=_signature_of(node, outcome.source),
                documentation=None,
                parent_qualified_name=parent_qualified_name,
            )
            symbol_of_node[node.id] = fact
            facts.symbols.append(fact)

        # --- attach documentation --------------------------------------------
        span_ordered = [(node, symbol_of_node[node.id]) for node, _t, _nm in ordered]
        if doc_nodes:
            _attach_docs(facts, doc_nodes, span_ordered, outcome)

        # --- innermost-symbol lookup -----------------------------------------
        def enclosing(start_byte: int, end_byte: int) -> SymbolFact | None:
            """Innermost declaration containing the byte range, else the module."""
            index = bisect.bisect_right(starts, start_byte) - 1
            best: SymbolFact | None = None
            while index >= 0:
                node, _symbol_type, _name = ordered[index]
                if node.start_byte <= start_byte and end_byte <= node.end_byte:
                    best = symbol_of_node[node.id]
                    break
                index -= 1
            if best is not None:
                return best
            return facts.symbols[0] if facts.symbols else None

        # --- imports ----------------------------------------------------------
        declaration_ids = {node.id for node, _t, _nm in ordered}
        grouped: dict[int, list[tuple[Any, str, str]]] = {}
        for node, kind, text in import_captures:
            if not text:
                continue
            statement = _statement_ancestor(node, declaration_ids)
            grouped.setdefault(statement.id, []).append((statement, kind, text))

        for entries in grouped.values():
            statement = entries[0][0]
            module = ""
            names: list[str] = []
            alias: str | None = None
            for _node, kind, text in entries:
                if kind == "module" and not module:
                    module = text
                elif kind == "name":
                    names.append(text)
                elif kind == "alias" and alias is None:
                    alias = text

            # ``import os as o`` yields a name and an alias but no module
            # capture, because the module *is* the aliased name. Promote it.
            if not module and names:
                module = names.pop(0)

            if not module:
                continue

            owner = enclosing(statement.start_byte, statement.end_byte)
            facts.imports.append(
                ImportFact(
                    module=module,
                    span=SourceSpan.from_tree_sitter(statement),
                    names=_dedupe(names),
                    alias=alias,
                    enclosing_qualified_name=owner.qualified_name if owner else None,
                )
            )

        # --- calls ------------------------------------------------------------
        seen_calls: set[tuple[str, int]] = set()
        for callee_node, receiver_node, is_member in call_matches:
            callee = outcome.text_of(callee_node).strip()
            if not looks_like_identifier(callee):
                continue

            receiver = (
                outcome.text_of(receiver_node).strip() if receiver_node is not None else None
            )

            # A receiver that is not a plain dotted name is an expression
            # (`foo().bar`, `arr[0].baz`). Recording it would put syntax into a
            # semantic field, so the receiver is dropped and the call is
            # demoted to a plain call rather than stored misleadingly.
            if receiver is not None and not looks_like_identifier(receiver):
                receiver = None
                is_member = False

            key = (callee, callee_node.start_byte)
            if key in seen_calls:
                continue
            seen_calls.add(key)

            owner = enclosing(callee_node.start_byte, callee_node.end_byte)
            facts.calls.append(
                CallFact(
                    callee_name=callee,
                    span=SourceSpan.from_tree_sitter(callee_node),
                    receiver=receiver,
                    is_member_call=is_member,
                    enclosing_qualified_name=owner.qualified_name if owner else None,
                )
            )

        # --- inheritance --------------------------------------------------------
        seen_bases: set[tuple[str, int]] = set()
        for base_node in inherit_nodes:
            base = outcome.text_of(base_node).strip()
            if not base or not looks_like_identifier(base):
                continue
            key = (base, base_node.start_byte)
            if key in seen_bases:
                continue
            seen_bases.add(key)

            owner = enclosing(base_node.start_byte, base_node.end_byte)
            facts.inherits.append(
                InheritFact(
                    base_name=base,
                    span=SourceSpan.from_tree_sitter(base_node),
                    enclosing_qualified_name=owner.qualified_name if owner else None,
                )
            )

        # --- bindings -----------------------------------------------------------
        # A binding records "this name holds this type here". It is what makes a
        # call through a receiver (`self.repository.save`) resolvable at all:
        # the call site alone never says what type `repository` has.
        #
        # Note what is deliberately NOT done here. No deduplication, because
        # rebinding is real: `x = A(); x = B()` genuinely binds x twice, and
        # collapsing it would move the resolver's "last write wins" decision
        # into the extractor. No resolution either -- `type_name` stays the raw
        # text the source used.
        for (
            name_node,
            type_node,
            receiver_node,
            statement_node,
            is_parameter,
        ) in binding_matches:
            if type_node is None:
                continue

            bound_name = outcome.text_of(name_node).strip()
            type_name = outcome.text_of(type_node).strip()
            # A complex annotation (`Optional[Repo]`, `map[string]Service`)
            # is not a name we can resolve, so it is skipped rather than
            # stored as a string that looks like a symbol.
            if not bound_name or not looks_like_identifier(type_name):
                continue

            receiver = (
                outcome.text_of(receiver_node).strip()
                if receiver_node is not None
                else None
            )

            if is_parameter:
                scope = BindingScope.PARAMETER
            elif receiver is None:
                scope = BindingScope.LOCAL
            elif receiver in INSTANCE_RECEIVER_TOKENS:
                scope = BindingScope.INSTANCE
            else:
                # `other.field = Service()` binds an attribute of a *different*
                # object. Filing it under this file's scope would attribute
                # someone else's type to our class, so it is dropped. The call
                # is still recorded as a CallFact; only the type claim is not.
                continue

            anchor = statement_node if statement_node is not None else name_node
            owner = enclosing(anchor.start_byte, anchor.end_byte)

            facts.bindings.append(
                BindingFact(
                    bound_name=bound_name,
                    type_name=type_name,
                    span=SourceSpan.from_tree_sitter(anchor),
                    scope=scope,
                    enclosing_qualified_name=owner.qualified_name if owner else None,
                )
            )

        # Sorted so that "last write in source order wins" is a property of the
        # source, not of the order the query engine happened to match in.
        facts.bindings.sort(key=lambda b: (b.span, str(b.scope), b.bound_name))

        return facts


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _line_count(source: bytes) -> int:
    return source.count(b"\n") + (1 if source and not source.endswith(b"\n") else 0)


def _dedupe(values: list[str]) -> list[str]:
    """Order-preserving dedupe, so output stays deterministic."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _statement_ancestor(node: Any, declaration_ids: set[int]) -> Any:
    """Walk up to the node whose parent is a declaration body or the root.

    That node is the import *statement* -- ``import_from_statement`` in Python,
    ``import_declaration`` in Java, ``import_statement`` in JavaScript. It is
    the unit that groups the module, names and alias captures belonging to one
    import, which arrive as separate query matches and would otherwise be
    impossible to reassemble.
    """
    current = node
    while True:
        parent = current.parent
        if parent is None:
            return current
        if parent.parent is None:
            return current
        if parent.id in declaration_ids:
            return current
        current = parent


def _attach_docs(
    facts: ExtractionFacts,
    doc_nodes: list[Any],
    span_ordered: list[tuple[Any, SymbolFact]],
    outcome: ParseOutcome,
) -> None:
    """Attach the earliest documentation node inside each symbol's span.

    "Earliest" rather than "nearest": a leading docstring or header comment is
    the documentation of a symbol, while a comment buried in the middle of its
    body is an implementation note. Picking the earliest one inside the span
    captures the first case and ignores the second, with no language-specific
    rules about where a doc comment is allowed to live.
    """
    starts = [node.start_byte for node, _fact in span_ordered]
    assigned: set[int] = set()

    for doc_node in sorted(doc_nodes, key=lambda n: n.start_byte):
        index = bisect.bisect_right(starts, doc_node.start_byte) - 1
        while index >= 0:
            node, fact = span_ordered[index]
            if node.start_byte <= doc_node.start_byte and doc_node.end_byte <= node.end_byte:
                if id(fact) not in assigned:
                    fact.documentation = _clean_doc(outcome.text_of(doc_node))
                    assigned.add(id(fact))
                break
            index -= 1
