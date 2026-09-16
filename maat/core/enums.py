"""Closed vocabularies used across the semantic model.

Every value here is part of a persisted contract. Adding a member is a
backward-compatible change; renaming or removing one is not, because stored
model versions contain these literal strings.

Spec references (section numbers refer to SPEC.md):
    ParseStatus      -- section 10 (AC2, AC3, AC4, AC6) and section 30
    SymbolType       -- section 12 (Symbol.symbol_type)
    RelationshipType -- section 4.3 (observed relationships only)
    ResolutionStatus -- section 4.2 and section 13
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    """String enum whose ``str()`` is the bare value.

    Needed because these values are serialised directly into canonical JSON and
    into SQLite/FTS5 columns later. ``str(ParseStatus.OK)`` must be ``"OK"``,
    not ``"ParseStatus.OK"``.
    """

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class ParseStatus(_StrEnum):
    """Outcome of parsing one file.

    The distinction between FAILED and PARTIAL is load-bearing: FAILED means we
    hold no usable structure for the file, PARTIAL means we hold real structure
    for part of it and the file is marked degraded (section 10 AC6, section 30 AC2).
    """

    OK = "OK"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    EMPTY = "EMPTY"
    UNSUPPORTED = "UNSUPPORTED"

    @property
    def is_error(self) -> bool:
        """True only for FAILED. EMPTY and UNSUPPORTED are expected states."""
        return self is ParseStatus.FAILED

    @property
    def is_degraded(self) -> bool:
        return self in (ParseStatus.PARTIAL, ParseStatus.FAILED)


class SymbolType(_StrEnum):
    """What kind of thing a symbol is.

    Deliberately small and language-neutral. Language-specific node types
    (tree-sitter's ``decorated_definition``, Java's ``annotation_type_declaration``)
    must be mapped onto this set by the extractor, never leaked (section 11 AC3).
    """

    MODULE = "MODULE"
    CLASS = "CLASS"
    INTERFACE = "INTERFACE"
    ENUM = "ENUM"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    CONSTRUCTOR = "CONSTRUCTOR"
    PARAMETER = "PARAMETER"
    FIELD = "FIELD"
    VARIABLE = "VARIABLE"
    IMPORT = "IMPORT"
    TYPE_ALIAS = "TYPE_ALIAS"


class BindingScope(_StrEnum):
    """Where a name-to-type binding lives, which decides how it is looked up.

    Introduced for Stage 6. Resolving ``self.repository.save`` requires knowing
    that ``repository`` is an *instance* attribute and what type it holds, and
    that information is not recoverable from the call site alone.

    The three scopes are kept apart because the same name can mean different
    things at different scopes -- a local ``repository`` and a field
    ``repository`` in one method are two different types -- so a flat name map
    would silently conflate them.
    """

    LOCAL = "LOCAL"
    """A name bound inside a function body: ``x = Service()``."""

    INSTANCE = "INSTANCE"
    """An attribute of the current instance: ``self.x = Service()``."""

    PARAMETER = "PARAMETER"
    """A declared parameter: ``def f(self, repo: PaymentRepository)``."""


class RelationshipType(_StrEnum):
    """Observed relationships only (section 4.3).

    Derived relationships (DEPENDS_ON, TRANSITIVELY_DEPENDS_ON, IMPACTED_BY,
    REACHABLE_FROM) are intentionally absent: they are computed by the graph
    projection in a later stage and must never be written into the semantic
    model as if they had been observed.
    """

    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    REFERENCES = "REFERENCES"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"


class ResolutionStatus(_StrEnum):
    """How confident the resolver is that a relationship's target is correct.

    Stage M1 emits only UNRESOLVED. This is deliberate (section 4.2): an
    explicit unresolved edge is preferred over a confident wrong edge. The
    resolver in a later stage upgrades edges to the other three states.
    """

    RESOLVED_EXACT = "RESOLVED_EXACT"
    RESOLVED_HEURISTIC = "RESOLVED_HEURISTIC"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class DiagnosticSeverity(_StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class VersionStatus(_StrEnum):
    """Lifecycle of a model version (section 19).

    A version is BUILT in full, validated, and only then flipped to PUBLISHED.
    Readers only ever observe PUBLISHED versions, which is what makes the
    active-version pointer safe to swap atomically.
    """

    BUILDING = "BUILDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


class FileKind(_StrEnum):
    """Classification applied during snapshotting (section 8 AC4)."""

    SOURCE = "SOURCE"
    BINARY = "BINARY"
    GENERATED = "GENERATED"
    IGNORED = "IGNORED"
    UNSUPPORTED = "UNSUPPORTED"


class ChangeKind(_StrEnum):
    """How a path differs between two snapshots (section 9)."""

    NEW = "NEW"
    CHANGED = "CHANGED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"


#: Recovery levels used by the parser, from section 30.
RECOVERY_NONE = "none"
RECOVERY_STATEMENT = "statement"
RECOVERY_BLOCK = "block"
RECOVERY_FILE = "file"
