"""Stage 4 — the extractor interface and its fact vocabulary (spec section 11).

This module defines the *boundary* between Tier 2 (a syntax tree, which is
language-specific and disposable) and Tier 3 (the semantic model, which is
language-neutral and canonical).

The facts defined here are deliberately not the semantic model. They are an
intermediate shape: they carry source spans and raw names, but no IDs, no
version, and no resolved targets. Turning facts into a validated model is
``ir_builder``'s job. Keeping the two apart is what lets a new language be added
by writing one query file, with no change to the model.

Section 11 AC3 requires that "no language-specific AST structure should leak
into the canonical semantic model". The type signatures here enforce that: a
:class:`SymbolFact` has no ``node``, no ``node_type``, and no reference to
tree-sitter at all. There is nothing language-specific left to leak.

The fact vocabulary is:

    SymbolFact    a named declaration
    ImportFact    an import / include / use / require
    CallFact      a call site, receiver recorded as raw text
    InheritFact   a base type reference
    BindingFact   a name bound to a type in a scope  (added for Stage 6)

``BindingFact`` was added after Stage 5 shipped, when tracing the spec's section 7
expected graph showed that every edge in its call chain is reached through a
*bound* receiver (``self.payment_service``, ``self.repository``, a local
``service``) rather than through a name. Syntax alone cannot resolve those, so
the missing information had to be captured here rather than guessed later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ...core.contracts import Diagnostic
from ...core.enums import BindingScope, SymbolType
from ...core.locations import SourceSpan
from ..parser import ParseOutcome


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


@dataclass
class SymbolFact:
    """A named declaration observed in the syntax tree."""

    name: str
    symbol_type: SymbolType
    qualified_name: str
    span: SourceSpan
    signature: str | None = None
    documentation: str | None = None
    parent_qualified_name: str | None = None
    """Qualified name of the nearest enclosing declaration, or ``None`` for a
    top-level declaration. Drives the ``CONTAINS`` relationship."""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "symbol_type": str(self.symbol_type),
            "qualified_name": self.qualified_name,
            "span": self.span.to_dict(),
            "signature": self.signature,
            "documentation": self.documentation,
            "parent_qualified_name": self.parent_qualified_name,
        }


@dataclass
class ImportFact:
    """An import, include, use or require observed in the syntax tree."""

    module: str
    span: SourceSpan
    names: list[str] = field(default_factory=list)
    alias: str | None = None
    enclosing_qualified_name: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module,
            "span": self.span.to_dict(),
            "names": self.names,
            "alias": self.alias,
            "enclosing_qualified_name": self.enclosing_qualified_name,
        }


@dataclass
class CallFact:
    """A call site observed in the syntax tree.

    A call fact is *not* a resolved relationship. It records what the source
    said -- a callee name, optionally a receiver expression -- and nothing more.
    Deciding which symbol ``self.validate`` refers to is the resolver's job
    (section 13), and it is emphatically not this stage's job to guess.
    """

    callee_name: str
    span: SourceSpan
    receiver: str | None = None
    is_member_call: bool = False
    enclosing_qualified_name: str | None = None

    @property
    def target_name(self) -> str:
        """The raw dotted name as written, e.g. ``self.validate``."""
        if self.receiver:
            return f"{self.receiver}.{self.callee_name}"
        return self.callee_name

    def to_dict(self) -> dict[str, object]:
        return {
            "callee_name": self.callee_name,
            "span": self.span.to_dict(),
            "receiver": self.receiver,
            "is_member_call": self.is_member_call,
            "enclosing_qualified_name": self.enclosing_qualified_name,
        }


@dataclass
class InheritFact:
    """A base type / superclass reference."""

    base_name: str
    span: SourceSpan
    enclosing_qualified_name: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "base_name": self.base_name,
            "span": self.span.to_dict(),
            "enclosing_qualified_name": self.enclosing_qualified_name,
        }


@dataclass
class BindingFact:
    """A name bound to a type within one scope (added for Stage 6).

    This exists because syntax alone cannot resolve a member call. A ``CallFact``
    records ``receiver="self.repository"`` as raw text, and nothing in the tree
    says what type ``repository`` holds. Without that, the edge stays
    ``UNRESOLVED`` -- and the spec's own section 7 expected graph cannot be
    satisfied, because every edge in its call chain is reached through a bound
    receiver rather than a name.

    ``type_name`` is deliberately left **raw and unresolved**, exactly like
    ``CallFact.callee_name``. A binding records what the source *said*; deciding
    that ``PaymentRepository`` means ``repositories.payment_repository`` is the
    resolver's job in Stage 6, using the same import table as any other name.

    Two kinds of ``type_name`` are produced, and both are useful:

    * a constructed type -- ``x = Service()`` gives ``"Service"``
    * a referenced name -- ``self.repo = repo`` gives ``"repo"``, which the
      resolver follows through the parameter binding for ``repo``

    The second case is why this is one field rather than a flag: an aliasing
    assignment is just a binding whose type is another bound name, and the
    resolver resolves it by the same lookup, one hop further.
    """

    bound_name: str
    """``"service"`` for a local, ``"payment_service"`` for an instance attribute."""

    type_name: str
    """The raw name the binding was given, unresolved."""

    span: SourceSpan
    scope: BindingScope
    enclosing_qualified_name: str | None = None
    """Qualified name of the method the binding occurs in. For an ``INSTANCE``
    binding this is the method that performed the assignment -- usually
    ``__init__`` -- which is why resolution must fall back from the call site's
    method to the class's constructor."""

    def to_dict(self) -> dict[str, object]:
        return {
            "bound_name": self.bound_name,
            "type_name": self.type_name,
            "span": self.span.to_dict(),
            "scope": str(self.scope),
            "enclosing_qualified_name": self.enclosing_qualified_name,
        }


#: Receiver tokens that mean "the current instance" across object-oriented
#: languages. A shared vocabulary, not a per-language rule: ``self``, ``this``,
#: ``cls`` and ``$this`` express the same concept, so they are one set rather
#: than eighteen branches. Used to classify a binding as INSTANCE and, later, to
#: route a member call to the current class's members.
INSTANCE_RECEIVER_TOKENS: frozenset[str] = frozenset(
    {"self", "this", "cls", "Self", "Me", "$this", "static", "@"}
)


@dataclass
class ExtractionFacts:
    """Everything one file yielded, still language-neutral and still unresolved."""

    file_path: str
    language: str
    module_qualified_name: str
    module_name: str
    symbols: list[SymbolFact] = field(default_factory=list)
    imports: list[ImportFact] = field(default_factory=list)
    calls: list[CallFact] = field(default_factory=list)
    inherits: list[InheritFact] = field(default_factory=list)
    bindings: list[BindingFact] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "symbols": len(self.symbols),
            "imports": len(self.imports),
            "calls": len(self.calls),
            "inherits": len(self.inherits),
            "bindings": len(self.bindings),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "module_qualified_name": self.module_qualified_name,
            "module_name": self.module_name,
            "counts": self.counts(),
            "symbols": [s.to_dict() for s in self.symbols],
            "imports": [i.to_dict() for i in self.imports],
            "calls": [c.to_dict() for c in self.calls],
            "inherits": [h.to_dict() for h in self.inherits],
            "bindings": [b.to_dict() for b in self.bindings],
        }


# ---------------------------------------------------------------------------
# The interface
# ---------------------------------------------------------------------------


class Extractor(Protocol):
    """Turns a parse outcome into facts.

    One implementation ships today: :class:`~.query_extractor.QueryExtractor`,
    which is driven by a declarative ``.scm`` query file per language. Adding a
    language therefore means adding data, not code.
    """

    def extract(self, outcome: ParseOutcome, file_path: str) -> ExtractionFacts:
        ...


# ---------------------------------------------------------------------------
# Module naming
# ---------------------------------------------------------------------------


def module_path_for(file_path: str, language: str | None) -> str:
    """Derive a dotted module path from a repository-relative file path.

    ``services/payment_service.py`` -> ``services.payment_service``
    ``pkg/__init__.py``            -> ``pkg``
    ``src/api/index.ts``           -> ``src.api.index``

    This is a *naming convention*, not a resolution. It gives symbols a stable,
    human-readable prefix so two same-named classes in different files stay
    distinct (section 13 AC2). Whether the language would actually import the
    module by that name is a question for the resolver, and for languages whose
    module naming does not follow the file tree (Go packages, Java packages) the
    convention is a best-effort label rather than a claim.
    """
    stem = file_path
    dot = stem.rfind(".")
    slash = stem.rfind("/")
    if dot > slash:
        stem = stem[:dot]

    parts = [p for p in stem.split("/") if p]

    # __init__.py / index.ts / mod.rs denote the directory itself.
    if parts and parts[-1] in ("__init__", "index", "mod"):
        parts = parts[:-1]

    return ".".join(parts) if parts else stem


def module_symbol_name(module_path: str) -> str:
    """Short name of a module: the last dotted segment."""
    return module_path.rsplit(".", 1)[-1] if module_path else ""


#: Characters that may appear in an identifier across the supported languages.
#: Used to decide whether a captured call target is plausibly a symbol name
#: rather than an expression.
_IDENTIFIER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.$"
)


def looks_like_identifier(text: str) -> bool:
    """True if ``text`` is a plausible dotted identifier.

    Guards the call extractor against capturing an arbitrary expression as a
    callee name. ``obj.method`` passes; ``foo().bar[0]`` does not.
    """
    if not text:
        return False
    return all(ch in _IDENTIFIER_CHARS for ch in text)
