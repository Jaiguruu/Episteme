"""Stage 2 — change detection tests.

Covers section 9 AC1-AC6: initial indexing, no-change runs, single
modification, deletion, rename, interrupted update.
"""

from __future__ import annotations

import json
import unittest

from maat.offline.changes import diff_snapshot, load_manifest, manifest_version
from maat.offline.snapshot import manifest_payload, scan_repository

from ..support import TempRepository, empty_temp_dir, temp_repo

BASE_FILES = {
    "a.py": "value = 1\n",
    "b.py": "value = 2\n",
    "c.py": "value = 3\n",
}


class ChangeDetectionTests(unittest.TestCase):
    def _snapshot(self, root, version="mv_1"):
        return scan_repository(root, model_version=version)

    def test_ac1_initial_index_schedules_everything(self) -> None:
        with temp_repo(BASE_FILES) as root:
            change_set = diff_snapshot(None, self._snapshot(root))
        self.assertEqual(len(change_set.new), 3)
        self.assertEqual(len(change_set.scheduled_for_parse), 3)
        self.assertEqual(change_set.changed, [])

    def test_ac2_no_change_schedules_nothing(self) -> None:
        with temp_repo(BASE_FILES) as root:
            first = self._snapshot(root)
            previous = {r.path: r.content_hash for r in first.files}
            second = self._snapshot(root)
            change_set = diff_snapshot(previous, second)
        self.assertTrue(change_set.is_empty)
        self.assertEqual(change_set.scheduled_for_parse, [])
        self.assertEqual(len(change_set.unchanged), 3)

    def test_ac3_single_modification_schedules_one(self) -> None:
        with temp_repo(BASE_FILES) as root:
            previous = {r.path: r.content_hash for r in self._snapshot(root).files}
            (root / "b.py").write_text("value = 99\n", encoding="utf-8")
            change_set = diff_snapshot(previous, self._snapshot(root, "mv_2"))
        self.assertEqual(change_set.changed, ["b.py"])
        self.assertEqual(change_set.scheduled_for_parse, ["b.py"])
        self.assertEqual(len(change_set.unchanged), 2)

    def test_ac4_deletion_is_detected(self) -> None:
        with temp_repo(BASE_FILES) as root:
            previous = {r.path: r.content_hash for r in self._snapshot(root).files}
            (root / "c.py").unlink()
            change_set = diff_snapshot(previous, self._snapshot(root, "mv_2"))
        self.assertEqual(change_set.deleted, ["c.py"])
        self.assertEqual(change_set.scheduled_for_parse, [])

    def test_ac5_rename_detected_by_content(self) -> None:
        with temp_repo(BASE_FILES) as root:
            previous = {r.path: r.content_hash for r in self._snapshot(root).files}
            (root / "c.py").rename(root / "renamed.py")
            change_set = diff_snapshot(previous, self._snapshot(root, "mv_2"))
        self.assertEqual(change_set.renamed, [("c.py", "renamed.py")])
        # Not double-counted as a delete plus an add.
        self.assertNotIn("c.py", change_set.deleted)
        self.assertNotIn("renamed.py", change_set.new)
        # A rename *is* scheduled: symbol IDs are path-derived, so the entities
        # must be rebuilt against the new path.
        self.assertIn("renamed.py", change_set.scheduled_for_parse)

    def test_rename_with_edited_content_is_not_a_rename(self) -> None:
        """Only byte-identical moves count. A similarity heuristic would lie."""
        with temp_repo(BASE_FILES) as root:
            previous = {r.path: r.content_hash for r in self._snapshot(root).files}
            (root / "c.py").write_text("value = 300\n", encoding="utf-8")
            (root / "c.py").rename(root / "renamed.py")
            change_set = diff_snapshot(previous, self._snapshot(root, "mv_2"))
        self.assertEqual(change_set.renamed, [])
        self.assertEqual(change_set.deleted, ["c.py"])
        self.assertEqual(change_set.new, ["renamed.py"])

    def test_rename_pairing_is_deterministic_with_duplicate_content(self) -> None:
        files = {"a.py": "same\n", "b.py": "same\n", "c.py": "other\n"}
        with temp_repo(files) as root:
            previous = {r.path: r.content_hash for r in self._snapshot(root).files}
            (root / "a.py").rename(root / "z1.py")
            (root / "b.py").rename(root / "z2.py")
            first = diff_snapshot(previous, self._snapshot(root, "mv_2"))
            second = diff_snapshot(previous, self._snapshot(root, "mv_2"))
        self.assertEqual(first.renamed, second.renamed)
        self.assertEqual(len(first.renamed), 2)

    def test_statistics_are_reported(self) -> None:
        with temp_repo(BASE_FILES) as root:
            previous = {r.path: r.content_hash for r in self._snapshot(root).files}
            (root / "b.py").write_text("value = 99\n", encoding="utf-8")
            (root / "d.py").write_text("value = 4\n", encoding="utf-8")
            change_set = diff_snapshot(previous, self._snapshot(root, "mv_2"))
        stats = change_set.statistics()
        self.assertEqual(stats["new"], 1)
        self.assertEqual(stats["changed"], 1)
        self.assertEqual(stats["unchanged"], 2)
        self.assertEqual(stats["scheduled"], 2)


class ManifestPersistenceTests(unittest.TestCase):
    """AC6 — interrupted update must not corrupt the next run."""

    def test_round_trip(self) -> None:
        with temp_repo(BASE_FILES) as root:
            snapshot = scan_repository(root, model_version="mv_1")
            index = empty_temp_dir()
            target = index / "manifest.json"
            target.write_text(
                json.dumps(manifest_payload(snapshot)), encoding="utf-8"
            )
            manifest = load_manifest(target)
            self.assertEqual(len(manifest or {}), 3)
            self.assertEqual(manifest_version(target), "mv_1")

    def test_missing_manifest_is_treated_as_initial_index(self) -> None:
        self.assertIsNone(load_manifest(empty_temp_dir() / "manifest.json"))

    def test_truncated_manifest_is_treated_as_absent(self) -> None:
        """A half-written file must not be parsed into a wrong baseline."""
        index = empty_temp_dir()
        target = index / "manifest.json"
        target.write_text('{"entries": [{"path": "a.py", "conte', encoding="utf-8")
        self.assertIsNone(load_manifest(target))
        self.assertIsNone(manifest_version(target))

    def test_wrong_shape_is_treated_as_absent(self) -> None:
        index = empty_temp_dir()
        target = index / "manifest.json"
        target.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertIsNone(load_manifest(target))

    def test_corrupt_manifest_makes_everything_new(self) -> None:
        with temp_repo(BASE_FILES) as root:
            index = empty_temp_dir()
            (index / "manifest.json").write_text("not json", encoding="utf-8")
            previous = load_manifest(index / "manifest.json")
            change_set = diff_snapshot(previous, scan_repository(root, "mv_1"))
        self.assertEqual(len(change_set.new), 3)


class PipelineChangeIntegrationTests(unittest.TestCase):
    """The counters section 39 Step 3 expects to see."""

    def test_first_run_parses_everything(self) -> None:
        from maat.offline.pipeline import OfflinePipeline

        with TempRepository() as repo:
            result = OfflinePipeline().index(repo.root, index_dir=repo.index_dir)
        self.assertEqual(result.stats.files_parsed, 7)
        self.assertEqual(result.stats.files_reused, 0)

    def test_second_run_reparses_nothing(self) -> None:
        from maat.offline.pipeline import OfflinePipeline

        with TempRepository() as repo:
            pipeline = OfflinePipeline()
            pipeline.index(repo.root, index_dir=repo.index_dir)
            second = pipeline.index(repo.root, index_dir=repo.index_dir)
        self.assertEqual(second.stats.files_parsed, 0)
        self.assertEqual(second.stats.files_reused, 7)
        self.assertTrue(second.changes.is_empty)

    def test_single_file_edit_reparses_exactly_one(self) -> None:
        from maat.offline.pipeline import OfflinePipeline

        with TempRepository() as repo:
            pipeline = OfflinePipeline()
            first = pipeline.index(repo.root, index_dir=repo.index_dir)
            repo.append("services/payment_service.py", "\n\n# touched\n")
            second = pipeline.index(repo.root, index_dir=repo.index_dir)

        self.assertEqual(second.stats.files_parsed, 1)
        self.assertEqual(second.stats.files_reused, 6)
        self.assertEqual(second.changes.changed, ["services/payment_service.py"])
        self.assertNotEqual(first.version.id, second.version.id)
        self.assertEqual(second.version.parent_id, first.version.id)

    def test_unchanged_repository_keeps_the_same_version(self) -> None:
        """An idempotent reindex must not manufacture a new version."""
        from maat.offline.pipeline import OfflinePipeline

        with TempRepository() as repo:
            pipeline = OfflinePipeline()
            first = pipeline.index(repo.root, index_dir=repo.index_dir)
            second = pipeline.index(repo.root, index_dir=repo.index_dir)
        self.assertEqual(first.version.id, second.version.id)

    def test_reused_entities_are_restamped_to_the_new_version(self) -> None:
        """Section 19 AC3: no entity may reference an inactive version."""
        from maat.offline.pipeline import OfflinePipeline

        with TempRepository() as repo:
            pipeline = OfflinePipeline()
            pipeline.index(repo.root, index_dir=repo.index_dir)
            repo.append("services/payment_service.py", "\n\n# touched\n")
            second = pipeline.index(repo.root, index_dir=repo.index_dir)

        stale = [
            entity
            for collection in (
                second.ir.symbols,
                second.ir.relationships,
                second.ir.evidence,
                second.ir.chunks,
            )
            for entity in collection
            if entity.model_version != second.version.id
        ]
        self.assertEqual(stale, [])

    def test_deleted_file_entities_disappear(self) -> None:
        from maat.offline.pipeline import OfflinePipeline

        with TempRepository() as repo:
            pipeline = OfflinePipeline()
            pipeline.index(repo.root, index_dir=repo.index_dir)
            repo.delete("services/refund_service.py")
            second = pipeline.index(repo.root, index_dir=repo.index_dir)

        paths = {record.path for record in second.ir.files}
        self.assertNotIn("services/refund_service.py", paths)
        remaining = {s.qualified_name for s in second.ir.symbols}
        self.assertFalse(any("RefundService" in name for name in remaining))


if __name__ == "__main__":
    unittest.main()
