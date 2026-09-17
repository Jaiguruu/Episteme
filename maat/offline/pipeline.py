"""The offline pipeline: repository in, semantic model out.

Orchestrates the five stages and owns the two things no individual stage can
own: the model version, and the decision about what to reuse.

**Why reuse matters here.** Section 9 AC3 expects a single-file change to
reparse exactly one file. That is only possible if the entities from every
*unchanged* file survive into the new model without being recomputed. So the
previous model is loaded, entities for unchanged files are carried forward, and
only scheduled files are parsed. Section 39 Step 3's expected output --
"Changed files: 1, Reparsed files: 1" -- is a direct consequence of this.

**Why carried-forward entities are re-stamped.** A symbol reused from V1 is
re-emitted as belonging to V2. This looks like a contradiction and is not: the
symbol's *identity* (its ID) deliberately excludes the version, so re-stamping
does not change who it is, while section 19 AC3 requires every published entity
to reference the same active version. Carrying V1 entities into a V2 model
unmodified would produce exactly the mixed-version state section 19 AC1 forbids.

**Why nothing is published on failure.** The manifest and IR are written only
after the model validates and only via atomic writes. A crash mid-build leaves
the previous version's files untouched, so section 34's "Failed indexing -> keep
previous valid version active" holds without any explicit rollback logic.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core import ids as idgen
from ..core.contracts import (
    Binding,
    ChangeSet,
    Diagnostic,
    Evidence,
    FileRecord,
    ModelVersion,
    Relationship,
    RepositorySnapshot,
    SemanticChunk,
    SemanticIR,
    Symbol,
)
from ..core.enums import (
    DiagnosticSeverity,
    ParseStatus,
    VersionStatus,
)
from ..core.serialization import combine_hashes, write_json
from . import changes as change_detection
from . import languages
from .extractors.base import ExtractionFacts
from .extractors.query_extractor import QueryExtractor
from .ir_builder import build_file_ir
from .parser import TreeSitterParser
from .snapshot import SnapshotOptions, manifest_payload, scan_repository
#: Default index directory, relative to the repository root.
DEFAULT_INDEX_DIRNAME = ".maat"

MANIFEST_FILENAME = "manifest.json"
IR_FILENAME = "ir.json"

#: Every collection the current schema writes into ``ir.json``.
#:
#: A payload missing one of these was written by an older schema, and must not be
#: reused. The collection it lacks would be silently absent from the new model
#: while the manifest reported every file unchanged -- so the result would look
#: complete and not be, and ``problems()`` would not catch it because a model that
#: never had the entities has no dangling references either. Treating such a
#: payload as absent forces a rebuild, which is the same safe direction a corrupt
#: payload takes.
EXPECTED_COLLECTIONS: frozenset[str] = frozenset(
    {
        "files",
        "symbols",
        "relationships",
        "bindings",
        "evidence",
        "chunks",
        "diagnostics",
    }
)


@dataclass
class PipelineStats:
    """Counters for one indexing run."""

    files_scanned: int = 0
    files_parsed: int = 0
    files_reused: int = 0
    files_degraded: int = 0
    files_failed: int = 0
    files_unsupported: int = 0
    symbols: int = 0
    relationships: int = 0
    evidence: int = 0
    chunks: int = 0
    diagnostics: int = 0
    duration_ms: int = 0

    def to_dict(self) -> dict[str, int]:
        return dict(vars(self))


@dataclass
class PipelineResult:
    """Everything one indexing run produced."""

    snapshot: RepositorySnapshot
    changes: ChangeSet
    ir: SemanticIR
    version: ModelVersion
    stats: PipelineStats = field(default_factory=PipelineStats)
    index_dir: str = ""
    validation_problems: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.validation_problems

    def summary(self) -> dict[str, Any]:
        return {
            "model_version": self.version.id,
            "root": self.snapshot.root,
            "stats": self.stats.to_dict(),
            "changes": self.changes.statistics(),
            "counts": self.ir.counts(),
            "exclusions": self.snapshot.exclusion_counts(),
            "valid": self.is_valid,
            "validation_problems": self.validation_problems[:20],
        }


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def resolve_index_dir(root: str | Path, index_dir: str | Path | None) -> Path:
    if index_dir is not None:
        return Path(index_dir)
    return Path(root) / DEFAULT_INDEX_DIRNAME


def load_previous_ir(index_dir: Path) -> SemanticIR | None:
    """Load a previously written model, or ``None`` if there is not one.

    A corrupt file is treated as absent, matching the manifest policy: the safe
    direction to fail is to rebuild from scratch rather than to abort.

    **"Corrupt" covers structural damage, not only invalid JSON.** Rehydration
    reads required fields and constructs enums, so a payload that parses but does
    not match the persisted shape raises ``KeyError`` (missing field),
    ``ValueError`` (unknown enum value) or ``TypeError`` / ``AttributeError``
    (wrong type). The guard below therefore wraps the rehydration as well as the
    parse. Leaving it outside meant those four escaped into the caller and aborted
    the index run, which is precisely the outcome this function promises not to
    produce.

    The realistic trigger is **schema drift across versions**, not a truncated
    write: publication is atomic, so a half-written ``ir.json`` cannot be
    observed. See ``SECURITY.md``.

    **A payload from an older schema is treated as absent too.** See
    :data:`EXPECTED_COLLECTIONS`: reusing it would produce a model missing a whole
    collection while every file was reported unchanged.
    """
    path = index_dir / IR_FILENAME
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if not EXPECTED_COLLECTIONS.issubset(payload):
        return None
    try:
        return _ir_from_payload(payload)
    except (AttributeError, KeyError, TypeError, ValueError):
        # Structurally invalid for this schema version. Rebuilding from scratch is
        # the safe direction: a drifted model must never be reused, and the
        # previous version's files on disk are left untouched, so the reader sees
        # either the old complete model or the new one.
        return None


def _ir_from_payload(payload: dict[str, Any]) -> SemanticIR:
    """Rehydrate a model from its canonical JSON form.

    Hand-written rather than ``**payload`` because the serialised shape is a
    contract: it must stay readable and stable, and a silent field rename should
    break loudly here rather than corrupt a model.
    """
    from ..core.enums import (
        BindingScope,
        FileKind,
        RelationshipType,
        ResolutionStatus,
        SymbolType,
    )
    from ..core.locations import SourceSpan

    def span(raw: Any) -> SourceSpan:
        return SourceSpan(
            start_line=raw["start_line"],
            start_col=raw["start_col"],
            end_line=raw["end_line"],
            end_col=raw["end_col"],
        )

    ir = SemanticIR(model_version=str(payload.get("model_version", "")))

    for raw in payload.get("files", []):
        ir.files.append(
            FileRecord(
                path=raw["path"],
                language=raw.get("language"),
                content_hash=raw["content_hash"],
                size=raw["size"],
                parse_status=ParseStatus(raw["parse_status"]),
                parse_error=raw.get("parse_error"),
                model_version=raw["model_version"],
                file_kind=FileKind(raw.get("file_kind", "SOURCE")),
                id=raw.get("id", ""),
                is_binary=raw.get("is_binary", False),
                is_generated=raw.get("is_generated", False),
                line_count=raw.get("line_count", 0),
                node_count=raw.get("node_count", 0),
                max_depth=raw.get("max_depth", 0),
            )
        )

    for raw in payload.get("symbols", []):
        ir.symbols.append(
            Symbol(
                id=raw["id"],
                file_id=raw["file_id"],
                name=raw["name"],
                qualified_name=raw["qualified_name"],
                symbol_type=SymbolType(raw["symbol_type"]),
                signature=raw.get("signature"),
                location=span(raw["location"]),
                documentation=raw.get("documentation"),
                content_hash=raw["content_hash"],
                model_version=raw["model_version"],
                language=raw.get("language"),
            )
        )

    for raw in payload.get("relationships", []):
        ir.relationships.append(
            Relationship(
                id=raw["id"],
                source_symbol_id=raw["source_symbol_id"],
                target_symbol_id=raw["target_symbol_id"],
                relationship_type=RelationshipType(raw["relationship_type"]),
                resolution_status=ResolutionStatus(raw["resolution_status"]),
                confidence=raw["confidence"],
                source_location=span(raw["source_location"]),
                model_version=raw["model_version"],
                target_name=raw.get("target_name"),
            )
        )

    # ``.get(..., [])`` rather than indexing: an ``ir.json`` written before
    # bindings were persisted has no "bindings" key, and it must still load.
    for raw in payload.get("bindings", []):
        ir.bindings.append(
            Binding(
                id=raw["id"],
                file_id=raw["file_id"],
                bound_name=raw["bound_name"],
                type_name=raw["type_name"],
                scope=BindingScope(raw["scope"]),
                location=span(raw["location"]),
                model_version=raw["model_version"],
                enclosing_symbol_id=raw.get("enclosing_symbol_id"),
            )
        )

    for raw in payload.get("evidence", []):
        ir.evidence.append(
            Evidence(
                id=raw["id"],
                entity_id=raw["entity_id"],
                file_id=raw["file_id"],
                start_line=raw["start_line"],
                end_line=raw["end_line"],
                retrieval_source=raw["retrieval_source"],
                score=raw["score"],
                model_version=raw["model_version"],
            )
        )

    for raw in payload.get("chunks", []):
        ir.chunks.append(
            SemanticChunk(
                id=raw["id"],
                symbol_id=raw["symbol_id"],
                text=raw["text"],
                chunk_type=raw["chunk_type"],
                embedding_id=raw.get("embedding_id"),
                token_count=raw["token_count"],
                model_version=raw["model_version"],
            )
        )

    for raw in payload.get("diagnostics", []):
        ir.diagnostics.append(
            Diagnostic(
                severity=DiagnosticSeverity(raw["severity"]),
                code=raw["code"],
                message=raw["message"],
                file_path=raw.get("file_path"),
                language=raw.get("language"),
                span=span(raw["span"]) if raw.get("span") else None,
                recovery_action=raw.get("recovery_action", "none"),
            )
        )

    return ir


def _group_by_file(ir: SemanticIR) -> dict[str, dict[str, list[Any]]]:
    """Index a previous model by file path for reuse."""
    file_id_to_path = {record.id: record.path for record in ir.files}
    grouped: dict[str, dict[str, list[Any]]] = {}

    def bucket(path: str) -> dict[str, list[Any]]:
        return grouped.setdefault(
            path,
            {
                "symbols": [],
                "relationships": [],
                "bindings": [],
                "evidence": [],
                "chunks": [],
                "diagnostics": [],
            },
        )

    for diagnostic in ir.diagnostics:
        if diagnostic.file_path:
            bucket(diagnostic.file_path)["diagnostics"].append(diagnostic)

    for symbol in ir.symbols:
        path = file_id_to_path.get(symbol.file_id)
        if path:
            bucket(path)["symbols"].append(symbol)
    # Bindings carry their own file_id, so they are grouped directly rather than
    # through an enclosing symbol.
    for binding in ir.bindings:
        path = file_id_to_path.get(binding.file_id)
        if path:
            bucket(path)["bindings"].append(binding)
    for evidence in ir.evidence:
        path = file_id_to_path.get(evidence.file_id)
        if path:
            bucket(path)["evidence"].append(evidence)
    # Relationships and chunks are attached to the file of their source symbol.
    symbol_to_path = {
        symbol.id: file_id_to_path.get(symbol.file_id) for symbol in ir.symbols
    }
    for relationship in ir.relationships:
        path = symbol_to_path.get(relationship.source_symbol_id)
        if path:
            bucket(path)["relationships"].append(relationship)
    for chunk in ir.chunks:
        path = symbol_to_path.get(chunk.symbol_id)
        if path:
            bucket(path)["chunks"].append(chunk)

    return grouped


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


class OfflinePipeline:
    """Runs stages 1-5 and publishes a versioned semantic model."""

    def __init__(
        self,
        parser: TreeSitterParser | None = None,
        extractor: QueryExtractor | None = None,
        options: SnapshotOptions | None = None,
    ) -> None:
        self.parser = parser or TreeSitterParser()
        self.extractor = extractor or QueryExtractor()
        self.options = options or SnapshotOptions()

    def index(
        self,
        root: str | Path,
        index_dir: str | Path | None = None,
        persist: bool = True,
    ) -> PipelineResult:
        started = time.perf_counter()
        root_path = Path(root).resolve()
        index_path = resolve_index_dir(root_path, index_dir)

        previous_manifest = change_detection.load_manifest(
            index_path / MANIFEST_FILENAME
        )
        previous_version = change_detection.manifest_version(
            index_path / MANIFEST_FILENAME
        )

        # --- stage 1: snapshot -------------------------------------------
        snapshot = scan_repository(root_path, model_version="", options=self.options)
        version_id = idgen.model_version_id(
            combine_hashes([record.content_hash for record in snapshot.files])
        )
        # Stamp the resolved version onto every record. Done here rather than
        # inside the scanner because the version is derived *from* the scan.
        snapshot.model_version = version_id
        for record in snapshot.files:
            record.model_version = version_id

        # --- stage 2: change detection -----------------------------------
        change_set = change_detection.diff_snapshot(
            previous_manifest, snapshot, previous_version
        )
        scheduled = set(change_set.scheduled_for_parse)

        # --- stages 3-5: parse, extract, build ---------------------------
        previous_ir = load_previous_ir(index_path) if previous_manifest else None
        reusable = _group_by_file(previous_ir) if previous_ir else {}
        previous_files = (
            {record.path: record for record in previous_ir.files} if previous_ir else {}
        )

        ir = SemanticIR(model_version=version_id)
        stats = PipelineStats(files_scanned=len(snapshot.files))

        for record in snapshot.files:
            ir.files.append(record)

            if not record.is_source:
                stats.files_unsupported += 1
                continue

            language = record.language or ""

            if record.path in scheduled:
                self._parse_and_build(root_path, record, language, version_id, ir, stats)
            elif record.path in reusable:
                self._reuse(
                    record,
                    reusable[record.path],
                    previous_files.get(record.path),
                    version_id,
                    ir,
                )
                stats.files_reused += 1
            else:
                # Not scheduled and nothing to reuse: a language with no query
                # file, or a file that appeared in a manifest but not the model.
                if languages.extraction_query_path(language) is None:
                    stats.files_unsupported += 1
                else:
                    self._parse_and_build(
                        root_path, record, language, version_id, ir, stats
                    )

        # --- deterministic ordering ---------------------------------------
        _sort_ir(ir)

        validation = ir.problems()
        version = ModelVersion(
            id=version_id,
            created_at=snapshot.taken_at,
            parent_id=previous_version,
            file_count=len(ir.files),
            symbol_count=len(ir.symbols),
            relationship_count=len(ir.relationships),
            status=VersionStatus.PUBLISHED if not validation else VersionStatus.FAILED,
            degraded_file_count=sum(1 for f in ir.files if f.is_degraded),
            diagnostics_count=len(ir.diagnostics),
            binding_count=len(ir.bindings),
        )

        stats.symbols = len(ir.symbols)
        stats.relationships = len(ir.relationships)
        stats.evidence = len(ir.evidence)
        stats.chunks = len(ir.chunks)
        stats.diagnostics = len(ir.diagnostics)
        stats.duration_ms = int((time.perf_counter() - started) * 1000)

        result = PipelineResult(
            snapshot=snapshot,
            changes=change_set,
            ir=ir,
            version=version,
            stats=stats,
            index_dir=str(index_path),
            validation_problems=validation,
        )

        # --- publish ------------------------------------------------------
        # Only a valid model is written, and every write is atomic, so an
        # invalid or interrupted build leaves the previous version serving.
        if persist and result.is_valid:
            write_json(index_path / MANIFEST_FILENAME, manifest_payload(snapshot))
            write_json(index_path / IR_FILENAME, ir.to_dict())

        return result

    # -- internals --------------------------------------------------------

    def _parse_and_build(
        self,
        root: Path,
        record: FileRecord,
        language: str,
        version_id: str,
        ir: SemanticIR,
        stats: PipelineStats,
    ) -> None:
        try:
            source = (root / record.path).read_bytes()
        except OSError as error:
            record.parse_status = ParseStatus.FAILED
            record.parse_error = f"unreadable during parse: {error}"
            ir.diagnostics.append(
                Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="pipeline.unreadable",
                    message=record.parse_error,
                    file_path=record.path,
                    language=language,
                )
            )
            stats.files_failed += 1
            return

        outcome = self.parser.parse(source, language, record.path)
        record.parse_status = outcome.status
        record.node_count = outcome.node_count
        record.max_depth = outcome.max_depth

        # Parser diagnostics must reach the model. Section 30 AC3 requires the
        # error to be *persisted*: a degraded file whose reason was dropped on
        # the floor is indistinguishable from a healthy one at query time.
        ir.diagnostics.extend(outcome.diagnostics)

        if outcome.status.is_degraded:
            first_error = next(
                (
                    d
                    for d in outcome.diagnostics
                    if d.severity is DiagnosticSeverity.ERROR
                ),
                None,
            )
            record.parse_error = (
                first_error.message if first_error else f"parse status {outcome.status}"
            )

        stats.files_parsed += 1
        if outcome.status.is_degraded:
            stats.files_degraded += 1
        if outcome.status is ParseStatus.FAILED:
            stats.files_failed += 1

        facts = self.extractor.extract(outcome, record.path)
        file_ir = build_file_ir(facts, record, source, version_id)
        ir.symbols.extend(file_ir.symbols)
        ir.relationships.extend(file_ir.relationships)
        ir.bindings.extend(file_ir.bindings)
        ir.evidence.extend(file_ir.evidence)
        ir.chunks.extend(file_ir.chunks)
        ir.diagnostics.extend(file_ir.diagnostics)

    def _reuse(
        self,
        record: FileRecord,
        bucket: dict[str, list[Any]],
        previous_record: FileRecord | None,
        version_id: str,
        ir: SemanticIR,
    ) -> None:
        """Carry an unchanged file's entities into the new model.

        Every carried entity is re-stamped with the new model version. See the
        module docstring for why that is correct rather than a contradiction.

        The file's *parse outcome* is carried across too. The fresh snapshot can
        only guess a provisional status for a source file -- it does not parse
        anything -- so without this an unchanged file that was PARTIAL or FAILED
        would silently be reported as OK on the next run, and the degradation
        would vanish from ``maat status`` while the broken code was still there.
        """
        if previous_record is not None:
            record.parse_status = previous_record.parse_status
            record.parse_error = previous_record.parse_error
            record.node_count = previous_record.node_count
            record.max_depth = previous_record.max_depth

        for symbol in bucket["symbols"]:
            symbol.model_version = version_id
            symbol.file_id = record.id
            ir.symbols.append(symbol)
        for relationship in bucket["relationships"]:
            relationship.model_version = version_id
            ir.relationships.append(relationship)
        for binding in bucket["bindings"]:
            binding.model_version = version_id
            binding.file_id = record.id
            ir.bindings.append(binding)
        for evidence in bucket["evidence"]:
            evidence.model_version = version_id
            evidence.file_id = record.id
            ir.evidence.append(evidence)
        for chunk in bucket["chunks"]:
            chunk.model_version = version_id
            ir.chunks.append(chunk)
        # A degraded file's explanation is part of the model, not a transient
        # log line, so it is carried forward with the entities it explains.
        ir.diagnostics.extend(bucket["diagnostics"])


def _sort_ir(ir: SemanticIR) -> None:
    """Put every collection in a defined order.

    Determinism has to be enforced somewhere, and doing it once at the end is
    simpler and more reliable than expecting every stage to emit sorted output.
    """
    ir.files.sort(key=lambda f: f.path)
    ir.symbols.sort(key=lambda s: (s.qualified_name, s.location.start_line, s.id))
    ir.relationships.sort(
        key=lambda r: (
            r.relationship_type.value,
            r.source_symbol_id,
            r.target_name or r.target_symbol_id,
            r.source_location.start_line,
            r.source_location.start_col,
        )
    )
    ir.bindings.sort(
        key=lambda b: (
            b.enclosing_symbol_id or "",
            b.bound_name,
            b.scope.value,
            b.location.start_line,
            b.location.start_col,
        )
    )
    ir.evidence.sort(key=lambda e: (e.entity_id, e.start_line, e.id))
    ir.chunks.sort(key=lambda c: (c.symbol_id, c.chunk_type))
    ir.diagnostics.sort(
        key=lambda d: (d.file_path or "", d.code, d.span.start_line if d.span else 0)
    )


def index_repository(
    root: str | Path,
    index_dir: str | Path | None = None,
    persist: bool = True,
) -> PipelineResult:
    """Convenience wrapper around :class:`OfflinePipeline`."""
    return OfflinePipeline().index(root, index_dir=index_dir, persist=persist)
