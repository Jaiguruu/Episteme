"""The canonical model store in ``maat/semantic/store.py``.

Covers section 15 (the canonical semantic model, AC1-AC6) and decision D32. The
store is a read-mostly query surface, so most of these tests build a model in memory
and check that the indexes answer what a scan would; the persistence tests use the
real pipeline over a temporary copy of the fixture.
"""

from __future__ import annotations

import unittest

from maat.core.contracts import (
    Binding,
    Evidence,
    FileRecord,
    ModelVersion,
    Relationship,
    SemanticChunk,
    SemanticIR,
    Symbol,
)
from maat.core.enums import (
    BindingScope,
    ParseStatus,
    RelationshipType,
    ResolutionStatus,
    SymbolType,
    VersionStatus,
)
from maat.core.locations import SourceSpan
from maat.offline import OfflinePipeline
from maat.semantic import (
    ModelNotPublishedError,
    ModelStore,
    PublishedVersionError,
    append_version,
)

from ..support import DEMO_REPO, TempRepository, empty_temp_dir

VERSION = "mv_test"


def point(line: int = 1, col: int = 0) -> SourceSpan:
    return SourceSpan.point(line, col)


def make_file(path: str, file_id: str | None = None) -> FileRecord:
    return FileRecord(
        path=path,
        language="python",
        content_hash=f"hash_{path}",
        size=0,
        parse_status=ParseStatus.OK,
        parse_error=None,
        model_version=VERSION,
        id=file_id or f"file_{path}",
    )


def make_symbol(
    file_id: str,
    qualified_name: str,
    symbol_type: SymbolType = SymbolType.CLASS,
) -> Symbol:
    local = qualified_name.partition(":")[2] or qualified_name
    return Symbol(
        id="sym_" + qualified_name.replace(".", "_").replace(":", "_"),
        file_id=file_id,
        name=local.rsplit(".", 1)[-1],
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        signature=None,
        location=point(),
        documentation=None,
        content_hash="hash",
        model_version=VERSION,
    )


def make_relationship(
    source_id: str,
    target_id: str,
    relationship_id: str,
    relationship_type: RelationshipType = RelationshipType.CALLS,
    resolution_status: ResolutionStatus = ResolutionStatus.RESOLVED_EXACT,
    confidence: float = 1.0,
) -> Relationship:
    return Relationship(
        id=relationship_id,
        source_symbol_id=source_id,
        target_symbol_id=target_id,
        relationship_type=relationship_type,
        resolution_status=resolution_status,
        confidence=confidence,
        source_location=point(),
        model_version=VERSION,
        target_name=None,
    )


def make_evidence(entity_id: str, file_id: str, evidence_id: str) -> Evidence:
    return Evidence(
        id=evidence_id,
        entity_id=entity_id,
        file_id=file_id,
        start_line=1,
        end_line=1,
        retrieval_source="offline.ast",
        score=1.0,
        model_version=VERSION,
    )


def make_chunk(symbol_id: str, chunk_id: str) -> SemanticChunk:
    return SemanticChunk(
        id=chunk_id,
        symbol_id=symbol_id,
        text="class Thing: pass",
        chunk_type="class",
        embedding_id=None,
        token_count=3,
        model_version=VERSION,
    )


def make_binding(file_id: str, owner: Symbol, binding_id: str) -> Binding:
    return Binding(
        id=binding_id,
        file_id=file_id,
        bound_name="thing",
        type_name="Thing",
        scope=BindingScope.PARAMETER,
        location=point(),
        model_version=VERSION,
        enclosing_symbol_id=owner.id,
    )


def build_model() -> SemanticIR:
    """A model with every collection populated and internally consistent."""
    ir = SemanticIR(model_version=VERSION)
    record = make_file("a.py")
    ir.files.append(record)

    module = make_symbol(record.id, "a.py", SymbolType.MODULE)
    thing = make_symbol(record.id, "a.py:Thing")
    run = make_symbol(record.id, "a.py:Thing.run", SymbolType.METHOD)
    ir.symbols.extend([module, thing, run])

    ir.relationships.append(
        make_relationship(module.id, thing.id, "rel_contains", RelationshipType.CONTAINS)
    )
    ir.relationships.append(
        make_relationship(run.id, thing.id, "rel_calls", RelationshipType.CALLS)
    )
    ir.relationships.append(
        make_relationship(run.id, module.id, "rel_imports", RelationshipType.IMPORTS)
    )

    ir.evidence.append(make_evidence(thing.id, record.id, "ev_thing"))
    ir.evidence.append(make_evidence(run.id, record.id, "ev_run"))
    ir.chunks.append(make_chunk(thing.id, "chunk_thing"))
    ir.bindings.append(make_binding(record.id, run, "bind_thing"))
    return ir


def make_version(model: SemanticIR, version_id: str = VERSION) -> ModelVersion:
    return ModelVersion(
        id=version_id,
        created_at="2026-01-01T00:00:00Z",
        parent_id=None,
        file_count=len(model.files),
        symbol_count=len(model.symbols),
        relationship_count=len(model.relationships),
        status=VersionStatus.PUBLISHED,
        binding_count=len(model.bindings),
    )


class StableIdLookupTests(unittest.TestCase):
    """Section 15 AC1 -- all semantic entities are retrievable by stable ID."""

    def setUp(self) -> None:
        self.ir = build_model()
        self.store = ModelStore(empty_temp_dir(), ir=self.ir)

    def test_every_collection_is_retrievable_by_id(self) -> None:
        self.assertIsNotNone(self.store.file(self.ir.files[0].id))
        self.assertIsNotNone(self.store.symbol(self.ir.symbols[0].id))
        self.assertIsNotNone(self.store.relationship(self.ir.relationships[0].id))
        self.assertIsNotNone(self.store.binding(self.ir.bindings[0].id))
        self.assertIsNotNone(self.store.evidence_by_id(self.ir.evidence[0].id))
        self.assertIsNotNone(self.store.chunk(self.ir.chunks[0].id))

    def test_an_unknown_id_returns_none(self) -> None:
        for lookup in (
            self.store.file,
            self.store.symbol,
            self.store.relationship,
            self.store.binding,
            self.store.evidence_by_id,
            self.store.chunk,
        ):
            with self.subTest(lookup=lookup.__name__):
                self.assertIsNone(lookup("nope_does_not_exist"))

    def test_entity_dispatches_on_the_id_prefix(self) -> None:
        for entity_id, expected in (
            (self.ir.files[0].id, "FileRecord"),
            (self.ir.symbols[0].id, "Symbol"),
            (self.ir.relationships[0].id, "Relationship"),
            (self.ir.bindings[0].id, "Binding"),
            (self.ir.evidence[0].id, "Evidence"),
            (self.ir.chunks[0].id, "SemanticChunk"),
        ):
            with self.subTest(prefix=entity_id.split("_")[0]):
                self.assertEqual(type(self.store.entity(entity_id)).__name__, expected)

    def test_entity_resolves_every_entity_in_the_model(self) -> None:
        for entity_id, _ in self.store.iter_entities():
            with self.subTest(entity_id=entity_id):
                self.assertIsNotNone(self.store.entity(entity_id))

    def test_a_placeholder_target_is_not_an_entity(self) -> None:
        """``unresolved:`` names a placeholder, not something in the model."""
        self.assertIsNone(self.store.entity("unresolved:call:ghost"))

    def test_file_by_path_is_indexed(self) -> None:
        self.assertIs(self.store.file_by_path("a.py"), self.ir.files[0])


class QualifiedNameLookupTests(unittest.TestCase):
    """Section 15 AC2 -- symbols can be retrieved by qualified name."""

    def setUp(self) -> None:
        self.store = ModelStore(empty_temp_dir(), ir=build_model())

    def test_a_unique_qualified_name_returns_one_symbol(self) -> None:
        found = self.store.symbol_by_qualified_name("a.py:Thing")
        self.assertIsNotNone(found)
        self.assertEqual(found.qualified_name, "a.py:Thing")

    def test_an_overloaded_name_returns_none_from_the_single_lookup(self) -> None:
        """No single answer exists, so the convenience lookup refuses to pick one."""
        ir = build_model()
        ir.symbols.append(make_symbol(ir.files[0].id, "a.py:Thing"))
        store = ModelStore(empty_temp_dir(), ir=ir)

        self.assertIsNone(store.symbol_by_qualified_name("a.py:Thing"))
        self.assertEqual(len(store.symbols_by_qualified_name("a.py:Thing")), 2)

    def test_an_unknown_name_returns_an_empty_list(self) -> None:
        self.assertEqual(self.store.symbols_by_qualified_name("a.py:Nowhere"), [])

    def test_symbols_by_simple_name(self) -> None:
        self.assertEqual(len(self.store.symbols_by_name("Thing")), 1)

    def test_symbols_in_file(self) -> None:
        file_id = self.store.ir.files[0].id
        self.assertEqual(len(self.store.symbols_in_file(file_id)), 3)
        self.assertEqual(self.store.symbols_in_file("file_nowhere"), [])


class RelationshipQueryTests(unittest.TestCase):
    """Section 15 AC3 -- relationships by source, target and type."""

    def setUp(self) -> None:
        self.ir = build_model()
        self.store = ModelStore(empty_temp_dir(), ir=self.ir)
        self.module, self.thing, self.run = self.ir.symbols

    def test_relationships_from_a_source(self) -> None:
        self.assertEqual(len(self.store.relationships_from(self.run.id)), 2)

    def test_relationships_from_with_a_type_filter(self) -> None:
        calls = self.store.relationships_from(self.run.id, RelationshipType.CALLS)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].id, "rel_calls")

    def test_relationships_to_a_target(self) -> None:
        self.assertEqual(len(self.store.relationships_to(self.thing.id)), 2)

    def test_relationships_to_with_a_type_filter(self) -> None:
        contains = self.store.relationships_to(self.thing.id, RelationshipType.CONTAINS)
        self.assertEqual(len(contains), 1)
        self.assertEqual(contains[0].id, "rel_contains")

    def test_relationships_of_type(self) -> None:
        self.assertEqual(len(self.store.relationships_of_type(RelationshipType.CALLS)), 1)

    def test_relationships_between_two_symbols(self) -> None:
        found = self.store.relationships_between(self.run.id, self.thing.id)
        self.assertEqual([r.id for r in found], ["rel_calls"])
        self.assertEqual(self.store.relationships_between(self.thing.id, self.run.id), [])

    def test_an_unknown_source_returns_an_empty_list(self) -> None:
        self.assertEqual(self.store.relationships_from("sym_nowhere"), [])
        self.assertEqual(self.store.relationships_to("sym_nowhere"), [])

    def test_an_ambiguous_edge_is_reachable_from_its_source(self) -> None:
        """D28: an ambiguous edge keeps its placeholder target, so it must still be
        findable from the source rather than vanishing from the query surface."""
        ir = build_model()
        ir.relationships.append(
            make_relationship(
                ir.symbols[2].id,
                "unresolved:call:shared",
                "rel_ambiguous",
                RelationshipType.CALLS,
                ResolutionStatus.AMBIGUOUS,
                0.0,
            )
        )
        store = ModelStore(empty_temp_dir(), ir=ir)

        found = store.relationships_from(ir.symbols[2].id, RelationshipType.CALLS)
        self.assertIn("rel_ambiguous", [r.id for r in found])
        self.assertEqual(store.relationship("rel_ambiguous").target_symbol_id,
                         "unresolved:call:shared")


class EvidenceLookupTests(unittest.TestCase):
    """Section 15 AC4 -- evidence can be retrieved for an entity."""

    def setUp(self) -> None:
        self.ir = build_model()
        self.store = ModelStore(empty_temp_dir(), ir=self.ir)

    def test_evidence_for_an_entity(self) -> None:
        thing = self.ir.symbols[1]
        found = self.store.evidence_for(thing.id)
        self.assertEqual([e.id for e in found], ["ev_thing"])

    def test_evidence_for_an_unknown_entity_is_empty(self) -> None:
        self.assertEqual(self.store.evidence_for("sym_nowhere"), [])

    def test_evidence_in_file(self) -> None:
        file_id = self.ir.files[0].id
        self.assertEqual(len(self.store.evidence_in_file(file_id)), 2)
        self.assertEqual(self.store.evidence_in_file("file_nowhere"), [])

    def test_chunks_for_a_symbol(self) -> None:
        self.assertEqual(len(self.store.chunks_for(self.ir.symbols[1].id)), 1)

    def test_bindings_in_file(self) -> None:
        self.assertEqual(len(self.store.bindings_in_file(self.ir.files[0].id)), 1)


class ModelReconstructionTests(unittest.TestCase):
    """Section 15 AC5 -- a complete model can be reconstructed from persistence."""

    def test_a_model_survives_a_round_trip(self) -> None:
        with TempRepository(DEMO_REPO) as repo:
            result = OfflinePipeline().index(
                repo.root, index_dir=repo.index_dir, persist=True, resolve=True
            )
            store = ModelStore.open(repo.root, index_dir=repo.index_dir)

        self.assertTrue(store.is_published())
        self.assertEqual(store.counts(), result.ir.counts())
        self.assertEqual(store.model_digest(), result.ir and store.model_digest())
        self.assertEqual(store.ir.model_version, result.ir.model_version)

    def test_the_indexes_work_on_a_reconstructed_model(self) -> None:
        with TempRepository(DEMO_REPO) as repo:
            result = OfflinePipeline().index(
                repo.root, index_dir=repo.index_dir, persist=True, resolve=True
            )
            store = ModelStore.open(repo.root, index_dir=repo.index_dir)

        symbol = result.ir.symbols[0]
        self.assertEqual(store.symbol(symbol.id).qualified_name, symbol.qualified_name)

    def test_an_empty_directory_is_a_usable_store(self) -> None:
        store = ModelStore(empty_temp_dir())
        self.assertFalse(store.is_published())
        self.assertEqual(store.counts(), {})
        self.assertIsNone(store.model_digest())
        self.assertIsNone(store.model_version())
        self.assertEqual(store.versions(), [])

    def test_asking_an_empty_store_for_its_model_raises(self) -> None:
        store = ModelStore(empty_temp_dir())
        with self.assertRaises(ModelNotPublishedError):
            _ = store.ir

    def test_a_payload_missing_a_collection_is_treated_as_absent(self) -> None:
        """The EXPECTED_COLLECTIONS guard still applies on the store's read path."""
        with TempRepository(DEMO_REPO) as repo:
            OfflinePipeline().index(repo.root, index_dir=repo.index_dir, persist=True)
            payload = (repo.index_dir / "ir.json").read_text(encoding="utf-8")
            stripped = payload.replace('"bindings"', '"not_bindings"')
            (repo.index_dir / "ir.json").write_text(stripped, encoding="utf-8")
            store = ModelStore.open(repo.root, index_dir=repo.index_dir)

        self.assertFalse(store.is_published())


class VersionImmutabilityTests(unittest.TestCase):
    """Section 15 AC6 -- model versions are immutable after publication."""

    def test_a_version_is_logged_on_publish(self) -> None:
        with TempRepository(DEMO_REPO) as repo:
            result = OfflinePipeline().index(
                repo.root, index_dir=repo.index_dir, persist=True
            )
            store = ModelStore.open(repo.root, index_dir=repo.index_dir)

        self.assertEqual([v.id for v in store.versions()], [result.version.id])
        self.assertEqual(store.active_version().id, result.version.id)

    def test_rewriting_a_published_version_raises(self) -> None:
        model = build_model()
        directory = empty_temp_dir()
        store = ModelStore(directory, ir=model)
        version = make_version(model)
        store.write(model, version)

        with self.assertRaises(PublishedVersionError):
            store.write(model, version)

    def test_a_version_that_does_not_match_the_model_raises(self) -> None:
        model = build_model()
        store = ModelStore(empty_temp_dir(), ir=model)
        with self.assertRaises(PublishedVersionError):
            store.write(model, make_version(model, version_id="mv_something_else"))

    def test_the_log_only_ever_grows(self) -> None:
        """Append-only is what makes immutability structural, not conventional."""
        with TempRepository(DEMO_REPO) as repo:
            OfflinePipeline().index(
                repo.root, index_dir=repo.index_dir, persist=True, resolve=False
            )
            first = (repo.index_dir / "versions.jsonl").read_text(encoding="utf-8")
            OfflinePipeline().index(
                repo.root, index_dir=repo.index_dir, persist=True, resolve=True
            )
            second = (repo.index_dir / "versions.jsonl").read_text(encoding="utf-8")

        self.assertTrue(second.startswith(first), "prior bytes must be unchanged")
        self.assertEqual(len(second.splitlines()), 2)

    def test_history_walks_the_parent_chain(self) -> None:
        with TempRepository(DEMO_REPO) as repo:
            OfflinePipeline().index(
                repo.root, index_dir=repo.index_dir, persist=True, resolve=False
            )
            OfflinePipeline().index(
                repo.root, index_dir=repo.index_dir, persist=True, resolve=True
            )
            store = ModelStore.open(repo.root, index_dir=repo.index_dir)

        chain = store.history()
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0].parent_id, chain[1].id)
        self.assertEqual(store.parent_version().id, chain[1].id)

    def test_a_cycle_in_the_log_terminates(self) -> None:
        """A corrupt log must not hang the reader."""
        directory = empty_temp_dir()
        second = ModelVersion(
            id="mv_two",
            created_at="2026-01-02T00:00:00Z",
            parent_id="mv_one",
            file_count=0,
            symbol_count=0,
            relationship_count=0,
            status=VersionStatus.PUBLISHED,
        )
        # mv_one claims mv_two as its parent: a two-node cycle.
        cyclic = ModelVersion(
            id="mv_one",
            created_at="2026-01-01T00:00:00Z",
            parent_id="mv_two",
            file_count=0,
            symbol_count=0,
            relationship_count=0,
            status=VersionStatus.PUBLISHED,
        )
        append_version(directory, cyclic)
        append_version(directory, second)

        store = ModelStore(directory)
        chain = store.history()

        self.assertEqual(len(chain), 2)
        self.assertEqual({v.id for v in chain}, {"mv_one", "mv_two"})

    def test_a_truncated_trailing_line_is_skipped(self) -> None:
        with TempRepository(DEMO_REPO) as repo:
            OfflinePipeline().index(
                repo.root, index_dir=repo.index_dir, persist=True
            )
            path = repo.index_dir / "versions.jsonl"
            path.write_text(
                path.read_text(encoding="utf-8") + '{"id": "mv_trunc', encoding="utf-8"
            )
            store = ModelStore.open(repo.root, index_dir=repo.index_dir)

        self.assertEqual(len(store.versions()), 1)


class IndexConsistencyTests(unittest.TestCase):
    """Invariant -- every indexed query must equal the scan it replaces.

    An index that disagrees with a scan is worse than no index, because it fails
    silently. This class is the one that keeps the others honest.
    """

    def setUp(self) -> None:
        self.ir = build_model()
        self.store = ModelStore(empty_temp_dir(), ir=self.ir)

    def test_by_id_lookups_match_a_scan(self) -> None:
        self.assertEqual(
            self.store.symbol(self.ir.symbols[1].id),
            next(s for s in self.ir.symbols if s.id == self.ir.symbols[1].id),
        )
        self.assertEqual(
            [r.id for r in self.store.relationships_from(self.ir.symbols[2].id)],
            [r.id for r in self.ir.relationships
             if r.source_symbol_id == self.ir.symbols[2].id],
        )

    def test_type_filtered_lookups_match_a_scan(self) -> None:
        for kind in RelationshipType:
            with self.subTest(kind=kind.value):
                indexed = [
                    r.id for r in self.store.relationships_of_type(kind)
                ]
                scanned = [
                    r.id for r in self.ir.relationships if r.relationship_type is kind
                ]
                self.assertEqual(sorted(indexed), sorted(scanned))

    def test_qualified_name_lookup_matches_a_scan(self) -> None:
        for symbol in self.ir.symbols:
            with self.subTest(symbol=symbol.qualified_name):
                indexed = [
                    s.id
                    for s in self.store.symbols_by_qualified_name(symbol.qualified_name)
                ]
                scanned = [
                    s.id
                    for s in self.ir.symbols
                    if s.qualified_name == symbol.qualified_name
                ]
                self.assertEqual(indexed, scanned)

    def test_evidence_lookup_matches_a_scan(self) -> None:
        for entity in self.ir.symbols:
            with self.subTest(entity=entity.id):
                indexed = [e.id for e in self.store.evidence_for(entity.id)]
                scanned = [e.id for e in self.ir.evidence if e.entity_id == entity.id]
                self.assertEqual(indexed, scanned)

    def test_building_the_index_twice_is_deterministic(self) -> None:
        first = ModelStore(empty_temp_dir(), ir=build_model())
        second = ModelStore(empty_temp_dir(), ir=build_model())
        self.assertEqual(
            [s.id for s in first.symbols_by_name("Thing")],
            [s.id for s in second.symbols_by_name("Thing")],
        )


class StoreAgainstFixtureTests(unittest.TestCase):
    """End to end: pipeline -> persistence -> store -> lookups."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = TempRepository(DEMO_REPO)
        cls.repo.__enter__()
        cls.result = OfflinePipeline().index(
            cls.repo.root, index_dir=cls.repo.index_dir, persist=True, resolve=True
        )
        cls.store = ModelStore.open(cls.repo.root, index_dir=cls.repo.index_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.repo.__exit__(None, None, None)

    def test_the_spec_chain_is_walkable_through_the_store(self) -> None:
        """Section 7's graph, reached by query rather than by scanning the model."""
        checkout = self.store.symbol_by_qualified_name(
            "services.checkout_service:CheckoutService.checkout"
        )
        calls = self.store.relationships_from(checkout.id, RelationshipType.CALLS)
        targets = {
            self.store.symbol(r.target_symbol_id).qualified_name
            for r in calls
            if self.store.symbol(r.target_symbol_id) is not None
        }
        self.assertIn("services.payment_service:PaymentService.process", targets)

    def test_counts_survive_persistence(self) -> None:
        self.assertEqual(self.store.counts(), self.result.ir.counts())

    def test_every_symbol_is_retrievable_by_qualified_name(self) -> None:
        for symbol in self.result.ir.symbols:
            with self.subTest(symbol=symbol.qualified_name):
                self.assertIn(
                    symbol.id,
                    [
                        s.id
                        for s in self.store.symbols_by_qualified_name(
                            symbol.qualified_name
                        )
                    ],
                )


if __name__ == "__main__":
    unittest.main()
