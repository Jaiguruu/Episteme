"""Canonical serialisation.

Determinism is a testable property (section 8 AC5, section 12 AC1), and JSON is
where it is easiest to lose. Everything here exists to make byte-identical
output the path of least resistance:

* keys sorted, so dict insertion order never leaks into the output
* separators fixed, so no incidental whitespace differences
* ``ensure_ascii=False`` with explicit UTF-8 encoding, so unicode identifiers
  round-trip instead of being escaped differently on different runs
* no timestamps, no ``repr`` of objects, no sets anywhere in the output
* writes go to a temporary file and are then renamed over the target, so an
  interrupted run can never leave a half-written manifest behind
  (section 9 AC6)

The one deliberate exception is ``ModelVersion.created_at``, which is metadata
*about* a build rather than part of the model. It is excluded from equality
comparisons via :func:`model_digest`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from .contracts import (
    Binding,
    Diagnostic,
    Evidence,
    FileRecord,
    Relationship,
    SemanticChunk,
    SemanticIR,
    Symbol,
)
from .enums import (
    RECOVERY_NONE,
    BindingScope,
    DiagnosticSeverity,
    FileKind,
    ParseStatus,
    RelationshipType,
    ResolutionStatus,
    SymbolType,
)
from .locations import SourceSpan


def canonical_json(payload: Any) -> str:
    """Serialise to deterministic JSON text."""
    return json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        separators=(",", ": "),
        default=_json_default,
    )


def _json_default(value: Any) -> Any:
    """Fallback for objects that are not natively JSON serialisable.

    Enums are the only expected case; ``str()`` on our ``_StrEnum`` returns the
    bare value. Anything else is a programming error and should be loud rather
    than silently stringified into the model.
    """
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return str(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"cannot serialise {type(value).__name__} to canonical JSON")


def write_json(path: str | Path, payload: Any) -> None:
    """Write ``payload`` atomically as canonical JSON.

    Atomic because section 9 AC6 and section 19 AC2 both require that an
    interrupted or failed run leaves the previous good state untouched. A
    partial write is impossible: the reader sees either the old file or the
    complete new one.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_json(payload)
    handle, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=".tmp-", suffix=".json"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        # Never leave a stray temp file behind on failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def model_digest(ir: SemanticIR) -> str:
    """Content digest of a semantic model, ignoring build metadata.

    Used by the determinism test: two runs over an unchanged repository must
    produce the same digest even though ``created_at`` differs.
    """
    payload = ir.to_dict()
    payload.pop("counts", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def combine_hashes(hashes: list[str]) -> str:
    """Order-independent digest of a set of file content hashes.

    Sorted before hashing so that discovery order cannot influence the result,
    which is what lets an unchanged repository hash to an unchanged model
    version (see :func:`maat.core.ids.model_version_id`).
    """
    joined = "\n".join(sorted(hashes))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Index layout
# ---------------------------------------------------------------------------
#
# The artifact names live here rather than in the pipeline because more than one
# tier writes and reads them: the pipeline publishes, and the canonical store
# (``maat/semantic/store.py``) reads the model and appends to the version log. A
# duplicated string literal would be a silent drift waiting to happen.

#: Default index directory, relative to the repository root.
DEFAULT_INDEX_DIRNAME: Final[str] = ".maat"
#: The snapshot manifest.
MANIFEST_FILENAME: Final[str] = "manifest.json"
#: The canonical semantic model.
IR_FILENAME: Final[str] = "ir.json"
#: The Stage 7 validation report.
VALIDATION_FILENAME: Final[str] = "validation.json"
#: The append-only version history (Stage 8).
VERSIONS_FILENAME: Final[str] = "versions.jsonl"


# ---------------------------------------------------------------------------
# Model rehydration
# ---------------------------------------------------------------------------
#
# These live in ``core`` rather than in ``maat/offline/pipeline.py`` because more
# than one tier needs them. The canonical store (``maat/semantic/store.py``) must
# read a model back from JSON, and ``semantic`` may import only ``core`` -- so
# leaving rehydration in ``offline`` would either force a tier violation or
# produce a second copy that could drift from this one. Reading a stored model is
# a property of the model's serialised contract, which is what this module is.

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


def ir_to_payload(ir: SemanticIR) -> dict[str, Any]:
    """The canonical JSON form of a model. Thin wrapper, for symmetry."""
    return ir.to_dict()


def ir_from_payload(payload: dict[str, Any]) -> SemanticIR:
    """Rehydrate a model from its canonical JSON form.

    Hand-written rather than ``**payload`` because the serialised shape is a
    contract: it must stay readable and stable, and a silent field rename should
    break loudly here rather than corrupt a model.

    Raises ``KeyError``, ``TypeError`` or ``ValueError`` on a payload that does not
    match the contract; callers treat that as "absent" and rebuild, which is the
    safe direction.
    """

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
                candidate_symbol_ids=list(raw.get("candidate_symbol_ids", [])),
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
                recovery_action=raw.get("recovery_action", RECOVERY_NONE),
            )
        )

    return ir
