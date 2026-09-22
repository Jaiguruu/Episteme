"""Stage 8: the canonical semantic model store (section 15).

The store is the query surface over a persisted model. Everything the pipeline
writes -- ``ir.json`` and the version log -- is read back through here, and every
lookup the acceptance criteria name is answered from an index built once at open
rather than by scanning a list.

Why an index at all: ``SemanticIR`` already offers ``symbol_by_id``,
``relationships_from`` and friends, and every one of them is a linear scan. That is
fine for a model built in memory and thrown away, and wrong for a canonical store
that a projection will query repeatedly. On ``edgecase_repo`` the difference is
between O(1) and 5,398 comparisons per lookup.

Why it lives in the semantic tier: the spec groups the canonical model with
resolution under M2, and a store that a later projection reads should not require
importing the syntax tier to do it. This module depends only on ``maat.core`` --
which is why rehydration and the artifact names were promoted into
``maat.core.serialization`` first.

Spec references (section numbers refer to SPEC.md):
    section 15  -- the canonical semantic model (the acceptance criteria)
    section 19  -- model versions are immutable once published
    D32         -- Stage 8 stops short of the atomic active-version pointer
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from ..core import ids as idgen
from ..core.contracts import (
    Binding,
    Evidence,
    FileRecord,
    ModelVersion,
    Relationship,
    SemanticChunk,
    SemanticIR,
    Symbol,
)
from ..core.enums import RelationshipType, VersionStatus
from ..core.serialization import (
    EXPECTED_COLLECTIONS,
    IR_FILENAME,
    VERSIONS_FILENAME,
    DEFAULT_INDEX_DIRNAME,
    ir_from_payload,
    ir_to_payload,
    model_digest,
    read_json,
    write_json,
)


class ModelNotPublishedError(RuntimeError):
    """Raised when a model is asked for and the directory holds none.

    A caller error rather than a data condition: the store is usable without a
    model (``is_published()`` says so), and asking for one that does not exist is a
    mistake in the calling code, not a fact about the repository.
    """


class PublishedVersionError(RuntimeError):
    """Raised on an attempt to overwrite a version that is already published.

    Section 19 requires published versions to be immutable. The append-only log is
    what actually guarantees that; this exception only catches a caller who tries to
    write the same version twice, which is a programmer error.
    """


def _read_model(index_dir: Path) -> SemanticIR | None:
    """Read ``ir.json``, or ``None`` when it is absent or does not fit the schema.

    The same defensive posture as ``load_previous_ir``: a payload missing a
    collection, or one this schema cannot rehydrate, is treated as absent rather
    than half-loaded.
    """
    path = index_dir / IR_FILENAME
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if not EXPECTED_COLLECTIONS.issubset(payload):
        return None
    try:
        return ir_from_payload(payload)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _read_versions(index_dir: Path) -> list[ModelVersion]:
    """Read the append-only version log, skipping an unreadable trailing line.

    A crash mid-append can leave a partial final line. Skipping it rather than
    failing means the history stays readable up to the last complete record, which
    is the same direction ``load_previous_ir`` takes for a corrupt model.
    """
    path = index_dir / VERSIONS_FILENAME
    if not path.is_file():
        return []
    versions: list[ModelVersion] = []
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
            except ValueError:
                continue
            try:
                versions.append(
                    ModelVersion(
                        id=raw["id"],
                        created_at=raw["created_at"],
                        parent_id=raw.get("parent_id"),
                        file_count=raw["file_count"],
                        symbol_count=raw["symbol_count"],
                        relationship_count=raw["relationship_count"],
                        status=VersionStatus(raw["status"]),
                        degraded_file_count=raw.get("degraded_file_count", 0),
                        diagnostics_count=raw.get("diagnostics_count", 0),
                        binding_count=raw.get("binding_count", 0),
                        pipeline_fingerprint=raw.get("pipeline_fingerprint", ""),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return versions


def append_version(index_dir: str | Path, version: ModelVersion) -> None:
    """Append one version record to the log.

    Appending rather than rewriting is what makes immutability a property of the
    *file format*: a published version's bytes are never touched again, so a reader
    cannot observe a version that has changed underneath it (section 19).

    Exposed separately from :meth:`ModelStore.write` so a publisher that already
    holds the model in memory does not pay to build the query indexes just to log a
    version.
    """
    directory = Path(index_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with open(
        directory / VERSIONS_FILENAME, "a", encoding="utf-8", newline="\n"
    ) as stream:
        stream.write(json.dumps(version.to_dict(), sort_keys=True) + "\n")


class ModelStore:
    """Indexed, read-mostly access to one canonical model (section 15)."""

    def __init__(self, index_dir: str | Path, ir: SemanticIR | None = None) -> None:
        self.index_dir = Path(index_dir)
        self._ir = ir if ir is not None else _read_model(self.index_dir)
        self._versions = _read_versions(self.index_dir)
        self._versions_by_id = {version.id: version for version in self._versions}
        self._build_indexes()

    # -- construction -----------------------------------------------------

    @classmethod
    def open(
        cls, root: str | Path, index_dir: str | Path | None = None
    ) -> "ModelStore":
        """Open the store for a repository, read-only.

        ``index_dir`` overrides the default ``<root>/.maat``. A directory with no
        model is still a usable store: ``is_published()`` reports ``False``.
        """
        directory = (
            Path(index_dir)
            if index_dir is not None
            else Path(root) / DEFAULT_INDEX_DIRNAME
        )
        return cls(directory)

    @classmethod
    def create(
        cls,
        index_dir: str | Path,
        ir: SemanticIR,
        version: ModelVersion,
        *,
        persist: bool = True,
    ) -> "ModelStore":
        """Build a store around ``ir``, optionally publishing it."""
        store = cls(index_dir, ir=ir)
        store.write(ir, version, persist=persist)
        return store

    # -- indexes ----------------------------------------------------------

    def _build_indexes(self) -> None:
        """One pass per collection. Order follows the model, so it is deterministic."""
        ir = self._ir
        if ir is None:
            self._files_by_id = {}
            self._files_by_path = {}
            self._symbols_by_id = {}
            self._symbols_by_qname = {}
            self._symbols_by_name = {}
            self._symbols_by_file = {}
            self._rels_by_id = {}
            self._rels_from = {}
            self._rels_to = {}
            self._rels_from_type = {}
            self._rels_to_type = {}
            self._evidence_by_id = {}
            self._evidence_by_entity = {}
            self._chunks_by_id = {}
            self._chunks_by_symbol = {}
            self._bindings_by_id = {}
            self._bindings_by_file = {}
            self._entity_ids = frozenset()
            return

        self._files_by_id = {record.id: record for record in ir.files}
        self._files_by_path = {record.path: record for record in ir.files}

        self._symbols_by_id = {symbol.id: symbol for symbol in ir.symbols}
        self._symbols_by_qname = {}
        self._symbols_by_name = {}
        self._symbols_by_file = {}
        for symbol in ir.symbols:
            self._symbols_by_qname.setdefault(symbol.qualified_name, []).append(symbol)
            self._symbols_by_name.setdefault(symbol.name, []).append(symbol)
            self._symbols_by_file.setdefault(symbol.file_id, []).append(symbol)

        self._rels_by_id = {}
        self._rels_from = {}
        self._rels_to = {}
        self._rels_from_type = {}
        self._rels_to_type = {}
        for relationship in ir.relationships:
            self._rels_by_id[relationship.id] = relationship
            kind = relationship.relationship_type.value
            self._rels_from.setdefault(relationship.source_symbol_id, []).append(
                relationship
            )
            self._rels_to.setdefault(relationship.target_symbol_id, []).append(
                relationship
            )
            self._rels_from_type.setdefault(
                (relationship.source_symbol_id, kind), []
            ).append(relationship)
            self._rels_to_type.setdefault(
                (relationship.target_symbol_id, kind), []
            ).append(relationship)

        self._evidence_by_id = {item.id: item for item in ir.evidence}
        self._evidence_by_entity = {}
        for item in ir.evidence:
            self._evidence_by_entity.setdefault(item.entity_id, []).append(item)

        self._chunks_by_id = {chunk.id: chunk for chunk in ir.chunks}
        self._chunks_by_symbol = {}
        for chunk in ir.chunks:
            self._chunks_by_symbol.setdefault(chunk.symbol_id, []).append(chunk)

        self._bindings_by_id = {binding.id: binding for binding in ir.bindings}
        self._bindings_by_file = {}
        for binding in ir.bindings:
            self._bindings_by_file.setdefault(binding.file_id, []).append(binding)

        self._entity_ids = frozenset(
            set(self._files_by_id)
            | set(self._symbols_by_id)
            | set(self._rels_by_id)
            | set(self._evidence_by_id)
            | set(self._chunks_by_id)
            | set(self._bindings_by_id)
        )

    # -- section 15 AC1: retrieval by stable ID ---------------------------

    def file(self, file_id: str) -> FileRecord | None:
        return self._files_by_id.get(file_id)

    def file_by_path(self, path: str) -> FileRecord | None:
        return self._files_by_path.get(path)

    def symbol(self, symbol_id: str) -> Symbol | None:
        return self._symbols_by_id.get(symbol_id)

    def relationship(self, relationship_id: str) -> Relationship | None:
        return self._rels_by_id.get(relationship_id)

    def evidence_by_id(self, evidence_id: str) -> Evidence | None:
        return self._evidence_by_id.get(evidence_id)

    def chunk(self, chunk_id: str) -> SemanticChunk | None:
        return self._chunks_by_id.get(chunk_id)

    def binding(self, binding_id: str) -> Binding | None:
        return self._bindings_by_id.get(binding_id)

    def entity(self, entity_id: str) -> Any | None:
        """Retrieve any entity by its stable ID, dispatching on the ID prefix.

        The prefixes are the ones :mod:`maat.core.ids` assigns, so an ID is
        self-describing and no registry is needed. A placeholder target such as
        ``unresolved:call:foo`` is not an entity and returns ``None``.
        """
        if entity_id.startswith(idgen.FILE_PREFIX):
            return self.file(entity_id)
        if entity_id.startswith(idgen.SYMBOL_PREFIX):
            return self.symbol(entity_id)
        if entity_id.startswith(idgen.RELATIONSHIP_PREFIX):
            return self.relationship(entity_id)
        if entity_id.startswith(idgen.EVIDENCE_PREFIX):
            return self.evidence_by_id(entity_id)
        if entity_id.startswith(idgen.CHUNK_PREFIX):
            return self.chunk(entity_id)
        if entity_id.startswith(idgen.BINDING_PREFIX):
            return self.binding(entity_id)
        return None

    def has_entity(self, entity_id: str) -> bool:
        return entity_id in self._entity_ids

    # -- section 15 AC2: symbols by name ----------------------------------

    def symbols_by_qualified_name(self, qualified_name: str) -> list[Symbol]:
        """Every symbol with this qualified name, in model order.

        A list rather than a single symbol because a qualified name is not
        guaranteed unique across a repository.
        """
        return list(self._symbols_by_qname.get(qualified_name, ()))

    def symbol_by_qualified_name(self, qualified_name: str) -> Symbol | None:
        """The one symbol with this qualified name, or ``None`` if ambiguous.

        Returning ``None`` when several match is deliberate: an overloaded name has
        no single answer, and picking one would be the arbitrary choice this project
        refuses elsewhere.
        """
        matches = self._symbols_by_qname.get(qualified_name, ())
        return matches[0] if len(matches) == 1 else None

    def symbols_by_name(self, name: str) -> list[Symbol]:
        return list(self._symbols_by_name.get(name, ()))

    def symbols_in_file(self, file_id: str) -> list[Symbol]:
        return list(self._symbols_by_file.get(file_id, ()))

    # -- section 15 AC3: relationships by source / target / type ----------

    def relationships_from(
        self, symbol_id: str, relationship_type: RelationshipType | None = None
    ) -> list[Relationship]:
        if relationship_type is None:
            return list(self._rels_from.get(symbol_id, ()))
        return list(self._rels_from_type.get((symbol_id, relationship_type.value), ()))

    def relationships_to(
        self, symbol_id: str, relationship_type: RelationshipType | None = None
    ) -> list[Relationship]:
        if relationship_type is None:
            return list(self._rels_to.get(symbol_id, ()))
        return list(self._rels_to_type.get((symbol_id, relationship_type.value), ()))

    def relationships_of_type(
        self, relationship_type: RelationshipType
    ) -> list[Relationship]:
        wanted = relationship_type.value
        return [
            relationship
            for relationship in self._rels_by_id.values()
            if relationship.relationship_type.value == wanted
        ]

    def relationships_between(
        self,
        source_id: str,
        target_id: str,
        relationship_type: RelationshipType | None = None,
    ) -> list[Relationship]:
        return [
            relationship
            for relationship in self.relationships_from(source_id, relationship_type)
            if relationship.target_symbol_id == target_id
        ]

    # -- section 15 AC4: provenance ---------------------------------------

    def evidence_for(self, entity_id: str) -> list[Evidence]:
        """Evidence backing an entity, in model order."""
        return list(self._evidence_by_entity.get(entity_id, ()))

    def evidence_in_file(self, file_id: str) -> list[Evidence]:
        return [item for item in self._evidence_by_id.values() if item.file_id == file_id]

    def chunks_for(self, symbol_id: str) -> list[SemanticChunk]:
        return list(self._chunks_by_symbol.get(symbol_id, ()))

    def bindings_in_file(self, file_id: str) -> list[Binding]:
        return list(self._bindings_by_file.get(file_id, ()))

    # -- section 15 AC5: the whole model ----------------------------------

    @property
    def ir(self) -> SemanticIR:
        if self._ir is None:
            raise ModelNotPublishedError(
                f"no model in {self.index_dir}; check is_published() first"
            )
        return self._ir

    def is_published(self) -> bool:
        return self._ir is not None

    def counts(self) -> dict[str, int]:
        return self.ir.counts() if self._ir is not None else {}

    def model_digest(self) -> str | None:
        """The model's content digest, or ``None`` when there is no model."""
        return model_digest(self._ir) if self._ir is not None else None

    def model_version(self) -> ModelVersion | None:
        """The version record for the model currently on disk, if logged."""
        if self._ir is None:
            return None
        return self._versions_by_id.get(self._ir.model_version)

    # -- section 15 AC6: version management -------------------------------

    def versions(self) -> list[ModelVersion]:
        """Every logged version, oldest first."""
        return list(self._versions)

    def version(self, version_id: str) -> ModelVersion | None:
        return self._versions_by_id.get(version_id)

    def active_version(self) -> ModelVersion | None:
        """The most recently logged PUBLISHED version.

        Under D32 there is no pointer file: the authoritative active version is the
        one recorded inside ``ir.json``, and this is the log's view of the same
        thing.
        """
        for version in reversed(self._versions):
            if version.status is VersionStatus.PUBLISHED:
                return version
        return None

    def parent_version(self) -> ModelVersion | None:
        active = self.active_version()
        if active is None or active.parent_id is None:
            return None
        return self._versions_by_id.get(active.parent_id)

    def history(self) -> list[ModelVersion]:
        """Walk ``parent_id`` from the active version back to the root.

        Bounded by a visited set, so a corrupt log with a cycle terminates rather
        than looping forever.
        """
        chain: list[ModelVersion] = []
        seen: set[str] = set()
        current = self.active_version()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            chain.append(current)
            if current.parent_id is None:
                break
            current = self._versions_by_id.get(current.parent_id)
        return chain

    # -- writing ----------------------------------------------------------

    def write(
        self, ir: SemanticIR, version: ModelVersion, *, persist: bool = True
    ) -> None:
        """Publish ``ir`` and append ``version`` to the log.

        The model is written atomically and the log is appended to, never
        rewritten, so a published version's bytes cannot change (section 19).
        """
        if version.id != ir.model_version:
            raise PublishedVersionError(
                f"version {version.id} does not match the model's "
                f"{ir.model_version}"
            )
        existing = self._versions_by_id.get(version.id)
        if existing is not None and existing.status is VersionStatus.PUBLISHED:
            raise PublishedVersionError(
                f"version {version.id} is already published and cannot be rewritten"
            )

        if not persist:
            self._ir = ir
            self._versions.append(version)
            self._versions_by_id[version.id] = version
            self._build_indexes()
            return

        write_json(self.index_dir / IR_FILENAME, ir_to_payload(ir))
        append_version(self.index_dir, version)

        self._ir = ir
        self._versions.append(version)
        self._versions_by_id[version.id] = version
        self._build_indexes()

    # -- convenience ------------------------------------------------------

    def iter_entities(self) -> Iterator[tuple[str, Any]]:
        """Yield ``(id, entity)`` for every entity in the model, in model order."""
        ir = self.ir
        for collection in (
            ir.files,
            ir.symbols,
            ir.relationships,
            ir.bindings,
            ir.evidence,
            ir.chunks,
        ):
            for entity in collection:
                yield entity.id, entity
