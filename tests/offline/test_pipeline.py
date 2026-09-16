"""End-to-end offline pipeline tests.

Covers section 7 (the fixture's expected graph), section 30 (fault isolation),
and the determinism guarantees the model depends on.
"""

from __future__ import annotations

import unittest
from collections import defaultdict

from maat.core.enums import ParseStatus, RelationshipType, SymbolType
from maat.core.serialization import canonical_json, model_digest
from maat.offline.pipeline import OfflinePipeline

from ..support import DEMO_REPO, EDGECASE_REPO, TempRepository, empty_temp_dir

#: Section 7's expected graph, expressed as module-level edges. The fixture's
#: imports are the module-level statement of exactly the chain the spec names.
EXPECTED_MODULE_EDGES = {
    ("api.checkout_controller", "services.checkout_service"),
    ("services.checkout_service", "services.payment_service"),
    ("services.checkout_service", "repositories.payment_repository"),
    ("services.payment_service", "repositories.payment_repository"),
    ("services.refund_service", "services.payment_service"),
    ("services.refund_service", "repositories.payment_repository"),
}

#: The chain the spec requires, as a reachability assertion.
EXPECTED_CHAIN = [
    "api.checkout_controller",
    "services.checkout_service",
    "services.payment_service",
    "repositories.payment_repository",
]


def module_import_edges(result) -> set[tuple[str, str]]:
    symbols = {s.id: s for s in result.ir.symbols}
    edges: set[tuple[str, str]] = set()
    for relationship in result.ir.relationships:
        if relationship.relationship_type is not RelationshipType.IMPORTS:
            continue
        source = symbols.get(relationship.source_symbol_id)
        if source is not None and source.symbol_type is SymbolType.MODULE:
            edges.add((source.qualified_name, relationship.target_name or ""))
    return edges


class DemoRepositoryTests(unittest.TestCase):
    """The fixture in section 7."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = OfflinePipeline().index(
            DEMO_REPO, index_dir=empty_temp_dir(), persist=False
        )

    def test_every_file_is_indexed(self) -> None:
        self.assertEqual(len(self.result.ir.files), 7)

    def test_model_validates(self) -> None:
        self.assertEqual(self.result.validation_problems, [])
        self.assertTrue(self.result.is_valid)

    def test_expected_module_dependency_graph_is_present(self) -> None:
        edges = module_import_edges(self.result)
        missing = EXPECTED_MODULE_EDGES - edges
        self.assertEqual(missing, set(), f"missing edges: {sorted(missing)}")

    def test_expected_chain_is_reachable(self) -> None:
        """api -> services -> services -> repositories, following imports."""
        graph: dict[str, set[str]] = defaultdict(set)
        for source, target in module_import_edges(self.result):
            graph[source].add(target)

        reached = {EXPECTED_CHAIN[0]}
        frontier = [EXPECTED_CHAIN[0]]
        while frontier:
            current = frontier.pop()
            for neighbour in graph.get(current, ()):
                if neighbour not in reached:
                    reached.add(neighbour)
                    frontier.append(neighbour)

        for module in EXPECTED_CHAIN:
            self.assertIn(module, reached)

    def test_both_callers_of_payment_service_are_visible(self) -> None:
        """Section 16 AC1 expects CheckoutService and RefundService.

        M1 does not resolve the edges, but both call sites must already be
        present as facts or the resolver would have nothing to work with.
        """
        symbols = {s.id: s for s in self.result.ir.symbols}
        callers = {
            symbols[r.source_symbol_id].qualified_name
            for r in self.result.ir.relationships
            if r.relationship_type is RelationshipType.CALLS
            and r.target_name == "self.payment_service.process"
        }
        self.assertIn(
            "services.checkout_service:CheckoutService.checkout", callers
        )
        self.assertIn("services.refund_service:RefundService.refund", callers)

    def test_payment_service_is_a_symbol_with_methods(self) -> None:
        by_name = {s.qualified_name: s for s in self.result.ir.symbols}
        self.assertIn("services.payment_service:PaymentService", by_name)
        self.assertEqual(
            by_name["services.payment_service:PaymentService"].symbol_type,
            SymbolType.CLASS,
        )
        for method in ("process", "validate"):
            key = f"services.payment_service:PaymentService.{method}"
            self.assertIn(key, by_name)
            self.assertEqual(by_name[key].symbol_type, SymbolType.METHOD)

    def test_every_symbol_has_evidence(self) -> None:
        covered = {e.entity_id for e in self.result.ir.evidence}
        for symbol in self.result.ir.symbols:
            self.assertIn(symbol.id, covered, symbol.qualified_name)

    def test_no_entity_references_another_version(self) -> None:
        version = self.result.version.id
        for collection in (
            self.result.ir.symbols,
            self.result.ir.relationships,
            self.result.ir.evidence,
            self.result.ir.chunks,
            self.result.ir.files,
        ):
            for entity in collection:
                self.assertEqual(entity.model_version, version)


class FaultIsolationTests(unittest.TestCase):
    """Section 30 — one bad file must not take the repository down."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = OfflinePipeline().index(
            DEMO_REPO, index_dir=empty_temp_dir(), persist=False
        )

    def test_broken_file_is_degraded_not_fatal(self) -> None:
        by_path = {f.path: f for f in self.result.ir.files}
        broken = by_path["broken/broken_service.py"]
        self.assertTrue(broken.is_degraded)
        self.assertIn(
            broken.parse_status, (ParseStatus.PARTIAL, ParseStatus.FAILED)
        )

    def test_broken_file_error_is_persisted(self) -> None:
        """Section 30 AC3 — the error must survive into the model."""
        by_path = {f.path: f for f in self.result.ir.files}
        diagnostics = [
            d for d in self.result.ir.diagnostics
            if d.file_path == "broken/broken_service.py"
        ]
        self.assertTrue(
            diagnostics or by_path["broken/broken_service.py"].parse_error
        )

    def test_other_files_remain_healthy_and_queryable(self) -> None:
        """Section 30 AC1 and AC4."""
        healthy = [
            f for f in self.result.ir.files if not f.is_degraded
        ]
        self.assertEqual(len(healthy), 6)
        for record in healthy:
            self.assertEqual(record.parse_status, ParseStatus.OK)

    def test_valid_regions_of_the_broken_file_are_kept(self) -> None:
        """Section 10 AC6 — a usable partial tree is retained, not discarded."""
        qualified = {s.qualified_name for s in self.result.ir.symbols}
        self.assertIn("broken.broken_service:BrokenService", qualified)

    def test_fixing_the_file_clears_the_degradation(self) -> None:
        """Section 30 AC5 — recovery on reindex."""
        with TempRepository() as repo:
            pipeline = OfflinePipeline()
            first = pipeline.index(repo.root, index_dir=repo.index_dir)
            self.assertTrue(
                first.ir.file_by_path("broken/broken_service.py").is_degraded
            )

            repo.write(
                "broken/broken_service.py",
                '"""Now valid."""\n\n\nclass BrokenService:\n'
                "    def run(self, payment):\n        return True\n",
            )
            second = pipeline.index(repo.root, index_dir=repo.index_dir)

        self.assertEqual(
            second.ir.file_by_path("broken/broken_service.py").parse_status,
            ParseStatus.OK,
        )
        self.assertEqual(second.stats.files_parsed, 1)


class DeterminismTests(unittest.TestCase):
    def test_two_runs_produce_an_identical_model(self) -> None:
        """The whole point of content-addressed IDs and sorted output."""
        first = OfflinePipeline().index(
            DEMO_REPO, index_dir=empty_temp_dir(), persist=False
        )
        second = OfflinePipeline().index(
            DEMO_REPO, index_dir=empty_temp_dir(), persist=False
        )
        self.assertEqual(model_digest(first.ir), model_digest(second.ir))

    def test_two_runs_produce_identical_json(self) -> None:
        first = OfflinePipeline().index(
            DEMO_REPO, index_dir=empty_temp_dir(), persist=False
        )
        second = OfflinePipeline().index(
            DEMO_REPO, index_dir=empty_temp_dir(), persist=False
        )
        self.assertEqual(canonical_json(first.ir.to_dict()), canonical_json(second.ir.to_dict()))

    def test_serialised_model_contains_no_timestamps(self) -> None:
        result = OfflinePipeline().index(
            DEMO_REPO, index_dir=empty_temp_dir(), persist=False
        )
        text = canonical_json(result.ir.to_dict())
        for forbidden in ("created_at", "taken_at", "2026-", "T00:"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_edgecase_repository_is_deterministic(self) -> None:
        first = OfflinePipeline().index(
            EDGECASE_REPO, index_dir=empty_temp_dir(), persist=False
        )
        second = OfflinePipeline().index(
            EDGECASE_REPO, index_dir=empty_temp_dir(), persist=False
        )
        self.assertEqual(model_digest(first.ir), model_digest(second.ir))


class EdgeCaseRepositoryTests(unittest.TestCase):
    """The larger generated repository."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = OfflinePipeline().index(
            EDGECASE_REPO, index_dir=empty_temp_dir(), persist=False
        )

    def test_repository_indexes_and_validates(self) -> None:
        self.assertEqual(self.result.validation_problems, [])
        self.assertGreater(len(self.result.ir.files), 100)
        self.assertGreater(len(self.result.ir.symbols), 1000)

    def test_many_languages_are_represented(self) -> None:
        histogram = self.result.snapshot.language_histogram()
        self.assertGreaterEqual(len(histogram), 15)

    def test_ignored_and_generated_files_are_excluded(self) -> None:
        excluded = {e.path for e in self.result.snapshot.excluded}
        self.assertIn("node_modules", excluded)
        self.assertIn("build", excluded)
        self.assertIn("_edge/generated_pb2.py", excluded)
        self.assertIn("_edge/bundle.min.js", excluded)
        self.assertIn("_edge/binary_payload", excluded)

    def test_malformed_files_are_isolated(self) -> None:
        degraded = [f for f in self.result.ir.files if f.is_degraded]
        self.assertGreaterEqual(len(degraded), 5)
        # And they are a small minority.
        self.assertLess(len(degraded), len(self.result.ir.files) * 0.2)

    def test_deep_nesting_file_does_not_crash_the_pipeline(self) -> None:
        record = self.result.ir.file_by_path("_edge/deep_nesting.py")
        self.assertIsNotNone(record)
        self.assertGreater(record.max_depth, 300)

    def test_large_file_is_indexed(self) -> None:
        record = self.result.ir.file_by_path("_edge/large_file.py")
        self.assertIsNotNone(record)
        self.assertEqual(record.parse_status, ParseStatus.OK)
        self.assertGreater(record.node_count, 10000)

    def test_unicode_file_yields_symbols(self) -> None:
        names = {
            s.qualified_name for s in self.result.ir.symbols
            if "_edge.unicode_identifiers" in s.qualified_name
        }
        self.assertTrue(any("Donn" in name for name in names), names)

    def test_duplicate_class_names_across_files_stay_distinct(self) -> None:
        shared = [s for s in self.result.ir.symbols if s.name == "Shared"]
        self.assertEqual(len(shared), 2)
        self.assertEqual(len({s.id for s in shared}), 2)

    def test_empty_files_are_empty_not_failed(self) -> None:
        record = self.result.ir.file_by_path("_edge/empty.py")
        self.assertEqual(record.parse_status, ParseStatus.EMPTY)

    def test_unsupported_files_do_not_break_indexing(self) -> None:
        record = self.result.ir.file_by_path("_edge/unknown.xyzzy")
        self.assertEqual(record.parse_status, ParseStatus.UNSUPPORTED)

    def test_cyclic_imports_are_represented_without_hanging(self) -> None:
        edges = module_import_edges(self.result)
        self.assertIn(("_edge.cyclic_a", "_edge.cyclic_b"), edges)
        self.assertIn(("_edge.cyclic_b", "_edge.cyclic_a"), edges)

    def test_overloaded_methods_get_distinct_ids(self) -> None:
        overloaded = [
            s for s in self.result.ir.symbols
            if s.qualified_name.startswith("_edge.overloads:Overloaded.process")
        ]
        self.assertEqual(len(overloaded), 3)
        self.assertEqual(len({s.id for s in overloaded}), 3)

    def test_every_degraded_file_is_reported_with_a_reason(self) -> None:
        for record in self.result.ir.files:
            if record.is_degraded:
                self.assertTrue(
                    record.parse_error or record.parse_status is ParseStatus.PARTIAL,
                    record.path,
                )


class PersistenceTests(unittest.TestCase):
    def test_index_files_are_written_and_reloaded(self) -> None:
        with TempRepository() as repo:
            pipeline = OfflinePipeline()
            first = pipeline.index(repo.root, index_dir=repo.index_dir)
            self.assertTrue((repo.index_dir / "manifest.json").is_file())
            self.assertTrue((repo.index_dir / "ir.json").is_file())

            second = pipeline.index(repo.root, index_dir=repo.index_dir)

        self.assertEqual(first.ir.counts(), second.ir.counts())

    def test_index_directory_is_not_scanned(self) -> None:
        """Otherwise the index would grow every time it indexed."""
        with TempRepository() as repo:
            pipeline = OfflinePipeline()
            pipeline.index(repo.root, index_dir=repo.root / ".maat")
            second = pipeline.index(repo.root, index_dir=repo.root / ".maat")
        self.assertEqual(second.stats.files_scanned, 7)

    def test_published_artifacts_agree_on_the_version(self) -> None:
        """Section 19 AC3 — every published artifact references one version."""
        import json

        with TempRepository() as repo:
            OfflinePipeline().index(repo.root, index_dir=repo.index_dir)
            manifest = json.loads(
                (repo.index_dir / "manifest.json").read_text(encoding="utf-8")
            )
            model = json.loads(
                (repo.index_dir / "ir.json").read_text(encoding="utf-8")
            )

        self.assertEqual(manifest["model_version"], model["model_version"])
        for record in model["files"]:
            self.assertEqual(record["model_version"], model["model_version"])

    def test_atomic_write_leaves_no_temporary_files(self) -> None:
        """A crashed write must not litter the index directory."""
        with TempRepository() as repo:
            OfflinePipeline().index(repo.root, index_dir=repo.index_dir)
            leftovers = [
                p.name for p in repo.index_dir.iterdir() if p.name.startswith(".tmp-")
            ]
        self.assertEqual(leftovers, [])

    def test_reindexing_a_binary_corrupted_file_keeps_the_model_valid(self) -> None:
        """A file that turns binary mid-project must be excluded, not crash."""
        with TempRepository() as repo:
            pipeline = OfflinePipeline()
            pipeline.index(repo.root, index_dir=repo.index_dir)
            repo.write("models/payment.py", b"\x00\x01\x02binary\x00")
            second = pipeline.index(repo.root, index_dir=repo.index_dir)

        self.assertEqual(second.validation_problems, [])
        self.assertIsNone(second.ir.file_by_path("models/payment.py"))
        excluded = {e.path: str(e.reason) for e in second.snapshot.excluded}
        self.assertEqual(excluded.get("models/payment.py"), "BINARY")


if __name__ == "__main__":
    unittest.main()
