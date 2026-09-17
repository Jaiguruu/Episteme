"""Canonical semantic model contracts (spec section 12).

These dataclasses are the *only* thing downstream stages are allowed to depend
on. Two rules hold throughout:

* **Validation never raises.** Every object exposes ``problems()`` returning a
  list of human-readable strings. An invalid object is reported, not thrown,
  because a half-parsed file legitimately produces incomplete entities and the
  pipeline must survive that (section 30).
* **Every entity carries ``model_version``** so a reader can tell whether two
  facts came from the same build (section 19 AC1, section 25 AC5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import ids as idgen
from .enums import (
    RECOVERY_NONE,
    BindingScope,
    DiagnosticSeverity,
    FileKind,
    ParseStatus,
    RelationshipType,
    ResolutionStatus,
    SymbolType,
    VersionStatus,
)
from .locations import SourceSpan


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@dataclass
class Diagnostic:
    """A machine-readable problem found while processing one file.

    Deliberately not an exception. Section 30 AC3 requires the error to be
    *persisted*, so it has to be a first-class value that survives into the
    model and can be rendered by ``maat status``.
    """

    severity: DiagnosticSeverity
    code: str
    message: str
    file_path: str | None = None
    language: str | None = None
    span: SourceSpan | None = None
    recovery_action: str = RECOVERY_NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": str(self.severity),
            "code": self.code,
            "message": self.message,
            "file_path": self.file_path,
            "language": self.language,
            "span": self.span.to_dict() if self.span else None,
            "recovery_action": self.recovery_action,
        }


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


@dataclass
class FileRecord:
    """One file in the snapshot (spec section 8).

    The seven fields listed in section 8 are all present. ``file_kind``,
    ``is_binary``, ``is_generated`` and the structural counters are additions
    needed to implement section 8 AC4 (non-source filtering) and section 23 AC4
    (index status exposes degraded files).
    """

    path: str
    language: str | None
    content_hash: str
    size: int
    parse_status: ParseStatus
    parse_error: str | None
    model_version: str
    file_kind: FileKind = FileKind.SOURCE
    id: str = ""
    is_binary: bool = False
    is_generated: bool = False
    line_count: int = 0
    node_count: int = 0
    max_depth: int = 0

    def __post_init__(self) -> None:
        if not self.id:
            self.id = idgen.file_id(self.path)

    @property
    def is_source(self) -> bool:
        return self.file_kind is FileKind.SOURCE

    @property
    def is_degraded(self) -> bool:
        return self.parse_status.is_degraded

    def problems(self) -> list[str]:
        issues: list[str] = []
        if not self.path:
            issues.append("path is empty")
        if self.path.startswith(("/", "\\")) or ":" in self.path:
            issues.append(f"path must be repository-relative, got {self.path!r}")
        if "\\" in self.path:
            issues.append(f"path must use POSIX separators, got {self.path!r}")
        if not self.content_hash:
            issues.append("content_hash is empty")
        if self.size < 0:
            issues.append(f"size must be >= 0, got {self.size}")
        if not self.model_version:
            issues.append("model_version is empty")
        if self.parse_status.is_error and not self.parse_error:
            issues.append("parse_error must be set when parse_status is FAILED")
        if self.is_source and self.language is None:
            issues.append("a SOURCE file must have a language")
        return issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "language": self.language,
            "content_hash": self.content_hash,
            "size": self.size,
            "parse_status": str(self.parse_status),
            "parse_error": self.parse_error,
            "model_version": self.model_version,
            "file_kind": str(self.file_kind),
            "is_binary": self.is_binary,
            "is_generated": self.is_generated,
            "line_count": self.line_count,
            "node_count": self.node_count,
            "max_depth": self.max_depth,
        }


@dataclass
class ExcludedFile:
    """A discovered path deliberately kept out of the file manifest.

    Section 8 AC4 requires ignored, generated and binary files to be *excluded*,
    not merely flagged. Excluding them silently would be worse than including
    them: a user asking "why is my file missing?" deserves an answer. So they
    are recorded here with the reason and counted, but they never reach the
    parser and never appear in ``snapshot.files``.
    """

    path: str
    reason: FileKind
    size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "reason": str(self.reason), "size": self.size}


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------


@dataclass
class Symbol:
    """A named thing declared in a file (spec section 12, "Symbol")."""

    id: str
    file_id: str
    name: str
    qualified_name: str
    symbol_type: SymbolType
    signature: str | None
    location: SourceSpan
    documentation: str | None
    content_hash: str
    model_version: str
    language: str | None = None

    def problems(self) -> list[str]:
        issues: list[str] = []
        if not self.name:
            issues.append("name is empty")
        if not self.qualified_name:
            issues.append("qualified_name is empty")
        if self.symbol_type is not SymbolType.MODULE and ":" not in self.qualified_name:
            issues.append(
                f"qualified_name must be 'module.path:Symbol', got {self.qualified_name!r}"
            )
        if not self.file_id:
            issues.append("file_id is empty")
        if not self.model_version:
            issues.append("model_version is empty")
        issues.extend(f"location: {p}" for p in self.location.problems())
        return issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_id": self.file_id,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "symbol_type": str(self.symbol_type),
            "signature": self.signature,
            "location": self.location.to_dict(),
            "documentation": self.documentation,
            "content_hash": self.content_hash,
            "model_version": self.model_version,
            "language": self.language,
        }


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


@dataclass
class Relationship:
    """An observed edge between two symbols (spec section 12).

    ``target_symbol_id`` may be an ``unresolved:`` placeholder. That is not a
    bug -- it is the mechanism by which section 4.2's "prefer an explicit
    unresolved relationship over an incorrect confident relationship" is
    enforced. ``target_name`` always holds the raw text we saw, so a later
    resolver has something to work with.

    Two fields exist for Stage 6 and are empty until it runs (D25, D26):

    * ``target_name`` is retained *after* resolution as well as before it, so
      ``relationship_id`` stays stable across a reindex that resolves more edges.
    * ``candidate_symbol_ids`` is populated only for an ``AMBIGUOUS`` edge, and
      lists a bounded set of the symbols the resolver could not choose between.
      The edge keeps its placeholder target (D28), so a caller must read
      ``resolution_status`` before using ``target_symbol_id``.
    """

    id: str
    source_symbol_id: str
    target_symbol_id: str
    relationship_type: RelationshipType
    resolution_status: ResolutionStatus
    confidence: float
    source_location: SourceSpan
    model_version: str
    target_name: str | None = None
    candidate_symbol_ids: list[str] = field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        return self.resolution_status in (
            ResolutionStatus.RESOLVED_EXACT,
            ResolutionStatus.RESOLVED_HEURISTIC,
        )

    def problems(self) -> list[str]:
        issues: list[str] = []
        if not self.source_symbol_id:
            issues.append("source_symbol_id is empty")
        if not self.target_symbol_id:
            issues.append("target_symbol_id is empty")
        if not 0.0 <= self.confidence <= 1.0:
            issues.append(f"confidence must be within [0,1], got {self.confidence}")
        # Confidence must be consistent with the claimed resolution state.
        # Without this, a resolver could mark an edge RESOLVED_EXACT while
        # leaving confidence at 0.0, and section 14's confidence policy would
        # have nothing to enforce.
        if (
            self.resolution_status is ResolutionStatus.RESOLVED_EXACT
            and self.confidence < 1.0
        ):
            issues.append(
                f"RESOLVED_EXACT requires confidence 1.0, got {self.confidence}"
            )
        if (
            self.resolution_status is ResolutionStatus.UNRESOLVED
            and self.confidence > 0.0
        ):
            issues.append(
                f"UNRESOLVED requires confidence 0.0, got {self.confidence}"
            )
        if idgen.is_unresolved_target(self.target_symbol_id) and not self.target_name:
            issues.append("an unresolved relationship must record target_name")
        # D26: ambiguity must be *marked*, and the candidates are the useful part.
        # An AMBIGUOUS edge with no candidates tells a reader nothing they can act
        # on, so it is treated as an error rather than an incomplete record.
        if (
            self.resolution_status is ResolutionStatus.AMBIGUOUS
            and not self.candidate_symbol_ids
        ):
            issues.append("an AMBIGUOUS relationship must record candidate_symbol_ids")
        # An exact edge that lists candidates is internally contradictory: if the
        # answer were exact there would be nothing to choose between.
        if (
            self.resolution_status is ResolutionStatus.RESOLVED_EXACT
            and self.candidate_symbol_ids
        ):
            issues.append(
                "a RESOLVED_EXACT relationship must not record candidate_symbol_ids"
            )
        if not self.model_version:
            issues.append("model_version is empty")
        issues.extend(f"source_location: {p}" for p in self.source_location.problems())
        return issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_symbol_id": self.source_symbol_id,
            "target_symbol_id": self.target_symbol_id,
            "relationship_type": str(self.relationship_type),
            "resolution_status": str(self.resolution_status),
            "confidence": self.confidence,
            "source_location": self.source_location.to_dict(),
            "model_version": self.model_version,
            "target_name": self.target_name,
            "candidate_symbol_ids": list(self.candidate_symbol_ids),
        }


# ---------------------------------------------------------------------------
# Bindings
# ---------------------------------------------------------------------------


@dataclass
class Binding:
    """A name bound to a type within one scope (added for Stage 6).

    Persisted because syntax alone cannot resolve a member call. A call site
    records ``receiver="self.repository"`` as raw text, and nothing in the tree
    says what type ``repository`` holds. Without this surviving into the model,
    Stage 6 cannot resolve a single member call, and the expected chain in
    section 7 is unreachable -- every edge in it is reached through a *bound*
    receiver rather than through a name.

    ``type_name`` is deliberately left **raw and unresolved**, exactly as
    ``Relationship.target_name`` is. Deciding that ``PaymentRepository`` means
    ``repositories.payment_repository`` is the resolver's job, using the same
    import table as any other name.
    """

    id: str
    file_id: str
    bound_name: str
    type_name: str
    scope: BindingScope
    location: SourceSpan
    model_version: str
    enclosing_symbol_id: str | None = None
    """The symbol the binding occurs in, when one was identified. For an
    ``INSTANCE`` binding this is usually the constructor, which is why resolution
    must fall back from a call site's method to its class's constructor."""

    def problems(self) -> list[str]:
        issues: list[str] = []
        if not self.bound_name:
            issues.append("bound_name is empty")
        if not self.type_name:
            issues.append("type_name is empty")
        if not self.file_id:
            issues.append("file_id is empty")
        if not self.model_version:
            issues.append("model_version is empty")
        issues.extend(f"location: {p}" for p in self.location.problems())
        return issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_id": self.file_id,
            "bound_name": self.bound_name,
            "type_name": self.type_name,
            "scope": str(self.scope),
            "location": self.location.to_dict(),
            "model_version": self.model_version,
            "enclosing_symbol_id": self.enclosing_symbol_id,
        }


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@dataclass
class Evidence:
    """Provenance for one entity (spec section 12, "Evidence").

    Section 13 AC6 requires every resolved relationship to point back at source
    evidence, and section 41 Rule 3 requires no answer to be trusted without it.
    Evidence is therefore produced eagerly at build time, not on demand.
    """

    id: str
    entity_id: str
    file_id: str
    start_line: int
    end_line: int
    retrieval_source: str
    score: float
    model_version: str

    def problems(self) -> list[str]:
        issues: list[str] = []
        if not self.entity_id:
            issues.append("entity_id is empty")
        if not self.file_id:
            issues.append("file_id is empty")
        if self.start_line < 1:
            issues.append(f"start_line must be >= 1, got {self.start_line}")
        if self.end_line < self.start_line:
            issues.append(
                f"end_line {self.end_line} precedes start_line {self.start_line}"
            )
        if not 0.0 <= self.score <= 1.0:
            issues.append(f"score must be within [0,1], got {self.score}")
        if not self.model_version:
            issues.append("model_version is empty")
        return issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "file_id": self.file_id,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "retrieval_source": self.retrieval_source,
            "score": self.score,
            "model_version": self.model_version,
        }


# ---------------------------------------------------------------------------
# Semantic chunks
# ---------------------------------------------------------------------------


@dataclass
class SemanticChunk:
    """A retrievable unit of text (spec section 12, "Semantic Chunk").

    ``embedding_id`` is ``None`` in the offline parser stage: embeddings belong
    to the vector projection. The field exists now so the schema does not have
    to change later.
    """

    id: str
    symbol_id: str
    text: str
    chunk_type: str
    embedding_id: str | None
    token_count: int
    model_version: str

    def problems(self) -> list[str]:
        issues: list[str] = []
        if not self.symbol_id:
            issues.append("symbol_id is empty")
        if not self.text:
            issues.append("text is empty")
        if not self.chunk_type:
            issues.append("chunk_type is empty")
        if self.token_count < 0:
            issues.append(f"token_count must be >= 0, got {self.token_count}")
        if not self.model_version:
            issues.append("model_version is empty")
        return issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol_id": self.symbol_id,
            "text": self.text,
            "chunk_type": self.chunk_type,
            "embedding_id": self.embedding_id,
            "token_count": self.token_count,
            "model_version": self.model_version,
        }


# ---------------------------------------------------------------------------
# Versions and containers
# ---------------------------------------------------------------------------


@dataclass
class ModelVersion:
    """A published, immutable snapshot of the semantic model (section 19).

    Section 19 AC3 requires every published index to reference the same model
    version, and section 15 requires model versions to be immutable after
    publication. Immutability is enforced by convention: nothing in the
    pipeline mutates a ModelVersion once its status is PUBLISHED.
    """

    id: str
    created_at: str
    parent_id: str | None
    file_count: int
    symbol_count: int
    relationship_count: int
    status: VersionStatus
    degraded_file_count: int = 0
    diagnostics_count: int = 0
    binding_count: int = 0
    pipeline_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "parent_id": self.parent_id,
            "file_count": self.file_count,
            "symbol_count": self.symbol_count,
            "relationship_count": self.relationship_count,
            "status": str(self.status),
            "degraded_file_count": self.degraded_file_count,
            "diagnostics_count": self.diagnostics_count,
            "binding_count": self.binding_count,
            "pipeline_fingerprint": self.pipeline_fingerprint,
        }


@dataclass
class RepositorySnapshot:
    """A stable representation of the repository at one point in time (section 8)."""

    root: str
    model_version: str
    files: list[FileRecord] = field(default_factory=list)
    excluded: list[ExcludedFile] = field(default_factory=list)
    taken_at: str = ""

    @property
    def source_files(self) -> list[FileRecord]:
        return [f for f in self.files if f.is_source]

    @property
    def degraded_files(self) -> list[FileRecord]:
        return [f for f in self.files if f.is_degraded]

    def exclusion_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.excluded:
            key = str(record.reason)
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    def language_histogram(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.files:
            if record.language:
                counts[record.language] = counts.get(record.language, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "model_version": self.model_version,
            "taken_at": self.taken_at,
            "file_count": len(self.files),
            "excluded_count": len(self.excluded),
            "exclusion_counts": self.exclusion_counts(),
            "language_histogram": self.language_histogram(),
            "files": [f.to_dict() for f in self.files],
            "excluded": [e.to_dict() for e in self.excluded],
        }


@dataclass
class ChangeSet:
    """The difference between two snapshots (spec section 9).

    ``renamed`` holds ``(old_path, new_path)`` pairs. A rename is detected by
    content hash, so it is only claimed when the bytes are identical -- section
    9 AC5 asks that a rename "does not unnecessarily trigger semantic
    recomputation", which is only safe to assert for byte-identical files.
    """

    previous_version: str | None
    current_version: str
    new: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def scheduled_for_parse(self) -> list[str]:
        """Files that must be (re)parsed.

        Renamed files are included, and that is deliberate rather than an
        oversight. Section 9 AC5 asks that a rename "does not unnecessarily
        trigger semantic recomputation when content is unchanged and cache
        policy allows reuse". Our cache policy does *not* allow reuse: symbol
        IDs are derived from the file path (see ``core.ids``), so moving a file
        changes the identity of every symbol inside it. Reusing the old parse
        would leave the model keyed to a path that no longer exists. The
        recomputation is therefore necessary, not unnecessary, and the rename
        is still reported separately so callers can see what happened.
        """
        scheduled = set(self.new) | set(self.changed)
        scheduled.update(new_path for _, new_path in self.renamed)
        return sorted(scheduled)

    @property
    def is_empty(self) -> bool:
        return not (self.new or self.changed or self.deleted)

    def statistics(self) -> dict[str, int]:
        return {
            "new": len(self.new),
            "changed": len(self.changed),
            "deleted": len(self.deleted),
            "unchanged": len(self.unchanged),
            "renamed": len(self.renamed),
            "scheduled": len(self.scheduled_for_parse),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_version": self.previous_version,
            "current_version": self.current_version,
            "new": self.new,
            "changed": self.changed,
            "deleted": self.deleted,
            "unchanged": self.unchanged,
            "renamed": [list(pair) for pair in self.renamed],
            "statistics": self.statistics(),
        }


@dataclass
class SemanticIR:
    """The complete offline output: everything the indexes will be built from.

    Section 4.1 makes this the source of truth and the graph / FTS5 / vector
    stores mere projections, so this object must be sufficient on its own to
    reconstruct them.
    """

    model_version: str
    files: list[FileRecord] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    chunks: list[SemanticChunk] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def symbol_by_id(self, symbol_id: str) -> Symbol | None:
        for symbol in self.symbols:
            if symbol.id == symbol_id:
                return symbol
        return None

    def file_by_path(self, path: str) -> FileRecord | None:
        for record in self.files:
            if record.path == path:
                return record
        return None

    def relationships_from(self, symbol_id: str) -> list[Relationship]:
        return [r for r in self.relationships if r.source_symbol_id == symbol_id]

    def relationships_to(self, symbol_id: str) -> list[Relationship]:
        return [r for r in self.relationships if r.target_symbol_id == symbol_id]

    def problems(self) -> list[str]:
        """Whole-model validation, including referential integrity (section 14).

        Runs in one pass over indexed sets rather than nested loops, so it stays
        linear on a large repository.
        """
        issues: list[str] = []
        file_ids = {f.id for f in self.files}
        symbol_ids = {s.id for s in self.symbols}

        for record in self.files:
            issues.extend(f"{record.path}: {p}" for p in record.problems())
        for symbol in self.symbols:
            issues.extend(f"{symbol.qualified_name}: {p}" for p in symbol.problems())
            if symbol.file_id not in file_ids:
                issues.append(
                    f"{symbol.qualified_name}: file_id {symbol.file_id} does not exist"
                )
        for rel in self.relationships:
            issues.extend(f"{rel.id}: {p}" for p in rel.problems())
            if rel.source_symbol_id not in symbol_ids:
                issues.append(f"{rel.id}: source {rel.source_symbol_id} does not exist")
            if (
                not idgen.is_unresolved_target(rel.target_symbol_id)
                and rel.target_symbol_id not in symbol_ids
            ):
                issues.append(f"{rel.id}: target {rel.target_symbol_id} does not exist")
        for binding in self.bindings:
            issues.extend(f"{binding.id}: {p}" for p in binding.problems())
            if binding.file_id not in file_ids:
                issues.append(
                    f"{binding.id}: file_id {binding.file_id} does not exist"
                )
            if (
                binding.enclosing_symbol_id is not None
                and binding.enclosing_symbol_id not in symbol_ids
            ):
                issues.append(
                    f"{binding.id}: enclosing_symbol_id "
                    f"{binding.enclosing_symbol_id} does not exist"
                )
        for ev in self.evidence:
            issues.extend(f"{ev.id}: {p}" for p in ev.problems())
            if ev.file_id not in file_ids:
                issues.append(f"{ev.id}: file_id {ev.file_id} does not exist")
        for chunk in self.chunks:
            issues.extend(f"{chunk.id}: {p}" for p in chunk.problems())
            if chunk.symbol_id not in symbol_ids:
                issues.append(f"{chunk.id}: symbol_id {chunk.symbol_id} does not exist")

        # Duplicate detection (section 14: "duplicate detection").
        if len(symbol_ids) != len(self.symbols):
            issues.append("duplicate symbol IDs detected")
        rel_ids = [r.id for r in self.relationships]
        if len(set(rel_ids)) != len(rel_ids):
            issues.append("duplicate relationship IDs detected")
        return issues

    def is_valid(self) -> bool:
        return not self.problems()

    def counts(self) -> dict[str, int]:
        return {
            "files": len(self.files),
            "symbols": len(self.symbols),
            "relationships": len(self.relationships),
            "bindings": len(self.bindings),
            "evidence": len(self.evidence),
            "chunks": len(self.chunks),
            "diagnostics": len(self.diagnostics),
            "degraded_files": sum(1 for f in self.files if f.is_degraded),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "counts": self.counts(),
            "files": [f.to_dict() for f in self.files],
            "symbols": [s.to_dict() for s in self.symbols],
            "relationships": [r.to_dict() for r in self.relationships],
            "bindings": [b.to_dict() for b in self.bindings],
            "evidence": [e.to_dict() for e in self.evidence],
            "chunks": [c.to_dict() for c in self.chunks],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }
