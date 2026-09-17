"""Entity contracts in ``maat/core/contracts.py``.

Two rules hold across every entity and are asserted here rather than assumed:
validation **never raises** (it returns human-readable problems), and the root
``SemanticIR.problems()`` enforces referential integrity across collections.
"""

from __future__ import annotations

import unittest

from maat.core.contracts import (
    Binding,
    ChangeSet,
    Evidence,
    FileRecord,
    Relationship,
    SemanticChunk,
    SemanticIR,
    Symbol,
)
from maat.core.enums import (
    BindingScope,
    FileKind,
    ParseStatus,
    RelationshipType,
    ResolutionStatus,
    SymbolType,
)
from maat.core.locations import SourceSpan

SPAN = SourceSpan(1, 0, 4, 12)


def make_file(**overrides: object) -> FileRecord:
    values: dict[str, object] = {
        "path": "services/payment_service.py",
        "language": "python",
        "content_hash": "sha256:abc",
        "size": 120,
        "parse_status": ParseStatus.OK,
        "parse_error": None,
        "model_version": "mv_1",
    }
    values.update(overrides)
    return FileRecord(**values)  # type: ignore[arg-type]


def make_symbol(**overrides: object) -> Symbol:
    values: dict[str, object] = {
        "id": "sym_1",
        "file_id": "file_1",
        "name": "PaymentService",
        "qualified_name": "services.payment_service:PaymentService",
        "symbol_type": SymbolType.CLASS,
        "signature": "class PaymentService:",
        "location": SPAN,
        "documentation": None,
        "content_hash": "sha256:def",
        "model_version": "mv_1",
    }
    values.update(overrides)
    return Symbol(**values)  # type: ignore[arg-type]


def make_relationship(**overrides: object) -> Relationship:
    values: dict[str, object] = {
        "id": "rel_1",
        "source_symbol_id": "sym_1",
        "target_symbol_id": "unresolved:call:process",
        "relationship_type": RelationshipType.CALLS,
        "resolution_status": ResolutionStatus.UNRESOLVED,
        "confidence": 0.0,
        "source_location": SPAN,
        "model_version": "mv_1",
        "target_name": "process",
    }
    values.update(overrides)
    return Relationship(**values)  # type: ignore[arg-type]


class FileRecordTests(unittest.TestCase):
    def test_a_well_formed_record_has_no_problems(self) -> None:
        record = make_file()
        self.assertEqual(record.problems(), [])
        self.assertTrue(record.is_source)

    def test_id_is_derived_from_the_path_and_prefixed(self) -> None:
        """Path-only identity is what lets change detection see "same file, changed"."""
        record = make_file()
        self.assertTrue(record.id.startswith("file_"))
        self.assertEqual(record.id, make_file().id)
        self.assertNotEqual(record.id, make_file(path="other.py").id)

    def test_an_explicit_id_is_not_overwritten(self) -> None:
        self.assertEqual(make_file(id="file_explicit").id, "file_explicit")

    def test_an_empty_path_is_rejected(self) -> None:
        self.assertTrue(any("path is empty" in p for p in make_file(path="").problems()))

    def test_absolute_posix_paths_are_rejected(self) -> None:
        """Paths must be repository-relative or the model is not portable."""
        problems = make_file(path="/etc/passwd").problems()
        self.assertTrue(any("repository-relative" in p for p in problems))

    def test_windows_drive_paths_are_rejected(self) -> None:
        problems = make_file(path="C:/repo/a.py").problems()
        self.assertTrue(any("repository-relative" in p for p in problems))

    def test_backslash_separators_are_rejected(self) -> None:
        """This project is developed on Windows, so the guard has to be exercised."""
        problems = make_file(path="services\\payment_service.py").problems()
        self.assertTrue(any("POSIX separators" in p for p in problems))

    def test_an_empty_content_hash_is_rejected(self) -> None:
        self.assertTrue(make_file(content_hash="").problems())

    def test_a_negative_size_is_rejected(self) -> None:
        self.assertTrue(any("size must be" in p for p in make_file(size=-1).problems()))

    def test_an_empty_model_version_is_rejected(self) -> None:
        self.assertTrue(
            any("model_version is empty" in p for p in make_file(model_version="").problems())
        )

    def test_failed_requires_a_recorded_reason(self) -> None:
        """Section 30 AC3 — a degraded file with no reason is indistinguishable from a healthy one."""
        problems = make_file(
            parse_status=ParseStatus.FAILED, parse_error=None
        ).problems()
        self.assertTrue(any("parse_error must be set" in p for p in problems))

    def test_failed_with_a_reason_is_accepted(self) -> None:
        record = make_file(
            parse_status=ParseStatus.FAILED, parse_error="unexpected token"
        )
        self.assertEqual(record.problems(), [])
        self.assertTrue(record.is_degraded)

    def test_a_source_file_must_declare_a_language(self) -> None:
        problems = make_file(language=None).problems()
        self.assertTrue(any("must have a language" in p for p in problems))

    def test_a_non_source_file_may_have_no_language(self) -> None:
        record = make_file(language=None, file_kind=FileKind.BINARY)
        self.assertFalse(record.is_source)
        self.assertEqual(record.problems(), [])

    def test_is_degraded_mirrors_the_parse_status(self) -> None:
        for status in ParseStatus:
            with self.subTest(status=status.name):
                self.assertEqual(make_file(parse_status=status).is_degraded, status.is_degraded)

    def test_to_dict_is_complete_and_serialisable(self) -> None:
        payload = make_file().to_dict()
        for key in (
            "id", "path", "language", "content_hash", "size", "parse_status",
            "parse_error", "model_version", "file_kind", "is_binary",
            "is_generated", "line_count", "node_count", "max_depth",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["parse_status"], "OK")


class SymbolTests(unittest.TestCase):
    def test_a_well_formed_symbol_has_no_problems(self) -> None:
        self.assertEqual(make_symbol().problems(), [])

    def test_qualified_name_must_separate_module_from_symbol(self) -> None:
        problems = make_symbol(qualified_name="PaymentService").problems()
        self.assertTrue(any("module.path:Symbol" in p for p in problems))

    def test_a_module_symbol_is_exempt_from_the_colon_rule(self) -> None:
        record = make_symbol(
            name="payment_service",
            qualified_name="services.payment_service",
            symbol_type=SymbolType.MODULE,
        )
        self.assertEqual(record.problems(), [])

    def test_empty_name_and_qualified_name_are_rejected(self) -> None:
        self.assertTrue(make_symbol(name="").problems())
        self.assertTrue(make_symbol(qualified_name="").problems())

    def test_an_invalid_location_is_reported_through_the_symbol(self) -> None:
        problems = make_symbol(location=SourceSpan(0, 0, 0, 0)).problems()
        self.assertTrue(any(p.startswith("location:") for p in problems))

    def test_to_dict_serialises_the_enum_to_its_bare_value(self) -> None:
        self.assertEqual(make_symbol().to_dict()["symbol_type"], "CLASS")


class RelationshipTests(unittest.TestCase):
    def test_an_unresolved_edge_is_valid_and_carries_its_raw_text(self) -> None:
        """Section 4.2 — an explicit unresolved edge is a correct answer."""
        edge = make_relationship()
        self.assertEqual(edge.problems(), [])
        self.assertFalse(edge.is_resolved)
        self.assertEqual(edge.target_name, "process")

    def test_confidence_must_lie_within_the_unit_interval(self) -> None:
        for bad in (-0.1, 1.1):
            with self.subTest(confidence=bad):
                problems = make_relationship(
                    confidence=bad,
                    resolution_status=ResolutionStatus.AMBIGUOUS,
                ).problems()
                self.assertTrue(any("confidence must be" in p for p in problems))

    def test_resolved_exact_requires_full_confidence(self) -> None:
        """Otherwise section 14's confidence policy has nothing to enforce."""
        problems = make_relationship(
            resolution_status=ResolutionStatus.RESOLVED_EXACT, confidence=0.9
        ).problems()
        self.assertTrue(any("RESOLVED_EXACT requires confidence 1.0" in p for p in problems))

        good = make_relationship(
            resolution_status=ResolutionStatus.RESOLVED_EXACT, confidence=1.0
        )
        self.assertEqual(good.problems(), [])
        self.assertTrue(good.is_resolved)

    def test_unresolved_requires_zero_confidence(self) -> None:
        problems = make_relationship(
            resolution_status=ResolutionStatus.UNRESOLVED, confidence=0.5
        ).problems()
        self.assertTrue(any("UNRESOLVED requires confidence 0.0" in p for p in problems))

    def test_an_unresolved_target_must_record_the_raw_name(self) -> None:
        """Without it a later resolver has nothing to work with."""
        problems = make_relationship(target_name=None).problems()
        self.assertTrue(any("must record target_name" in p for p in problems))

    def test_a_resolved_target_does_not_need_a_raw_name(self) -> None:
        edge = make_relationship(
            target_symbol_id="sym_2",
            resolution_status=ResolutionStatus.RESOLVED_EXACT,
            confidence=1.0,
            target_name=None,
        )
        self.assertEqual(edge.problems(), [])

    def test_empty_endpoints_are_rejected(self) -> None:
        self.assertTrue(make_relationship(source_symbol_id="").problems())
        self.assertTrue(make_relationship(target_symbol_id="").problems())

    def test_to_dict_reports_the_resolution_status_as_a_bare_value(self) -> None:
        self.assertEqual(make_relationship().to_dict()["resolution_status"], "UNRESOLVED")


class EvidenceAndChunkTests(unittest.TestCase):
    def test_a_well_formed_evidence_row_has_no_problems(self) -> None:
        row = Evidence(
            id="ev_1",
            entity_id="sym_1",
            file_id="file_1",
            start_line=1,
            end_line=4,
            retrieval_source="offline.ast",
            score=1.0,
            model_version="mv_1",
        )
        self.assertEqual(row.problems(), [])

    def test_evidence_line_bounds_are_validated(self) -> None:
        base = dict(
            id="ev_1", entity_id="sym_1", file_id="file_1",
            retrieval_source="offline.ast", score=1.0, model_version="mv_1",
        )
        self.assertTrue(Evidence(start_line=0, end_line=1, **base).problems())
        self.assertTrue(Evidence(start_line=5, end_line=2, **base).problems())

    def test_evidence_score_is_bounded(self) -> None:
        row = Evidence(
            id="ev_1", entity_id="sym_1", file_id="file_1", start_line=1, end_line=1,
            retrieval_source="offline.ast", score=1.5, model_version="mv_1",
        )
        self.assertTrue(any("score must be" in p for p in row.problems()))

    def test_a_well_formed_chunk_has_no_problems(self) -> None:
        chunk = SemanticChunk(
            id="chunk_1", symbol_id="sym_1", text="class PaymentService: ...",
            chunk_type="class", embedding_id=None, token_count=7, model_version="mv_1",
        )
        self.assertEqual(chunk.problems(), [])

    def test_chunk_requires_text_and_a_type(self) -> None:
        chunk = SemanticChunk(
            id="chunk_1", symbol_id="sym_1", text="", chunk_type="",
            embedding_id=None, token_count=0, model_version="mv_1",
        )
        problems = chunk.problems()
        self.assertTrue(any("text is empty" in p for p in problems))
        self.assertTrue(any("chunk_type is empty" in p for p in problems))

    def test_a_negative_token_count_is_rejected(self) -> None:
        chunk = SemanticChunk(
            id="chunk_1", symbol_id="sym_1", text="x", chunk_type="class",
            embedding_id=None, token_count=-1, model_version="mv_1",
        )
        self.assertTrue(any("token_count" in p for p in chunk.problems()))


class SemanticIRIntegrityTests(unittest.TestCase):
    def _ir_with_one_file_and_symbol(self) -> SemanticIR:
        ir = SemanticIR(model_version="mv_1")
        record = make_file()
        ir.files.append(record)
        ir.symbols.append(make_symbol(id="sym_1", file_id=record.id))
        return ir

    def test_a_minimal_consistent_model_has_no_problems(self) -> None:
        self.assertEqual(self._ir_with_one_file_and_symbol().problems(), [])

    def test_a_symbol_pointing_at_a_missing_file_is_rejected(self) -> None:
        ir = self._ir_with_one_file_and_symbol()
        ir.symbols.append(make_symbol(id="sym_2", file_id="file_missing", qualified_name="m:Other"))
        problems = ir.problems()
        self.assertTrue(any("does not exist" in p for p in problems))

    def test_a_relationship_with_a_missing_source_is_rejected(self) -> None:
        ir = self._ir_with_one_file_and_symbol()
        ir.relationships.append(make_relationship(source_symbol_id="sym_missing"))
        problems = ir.problems()
        self.assertTrue(any("source sym_missing does not exist" in p for p in problems))

    def test_an_unresolved_target_is_exempt_from_the_existence_check(self) -> None:
        """Section 4.2 — every M1 reference is unresolved, and that is not an error."""
        ir = self._ir_with_one_file_and_symbol()
        ir.relationships.append(make_relationship(target_symbol_id="unresolved:call:process"))
        self.assertEqual(ir.problems(), [])

    def test_a_resolved_target_that_does_not_exist_is_rejected(self) -> None:
        ir = self._ir_with_one_file_and_symbol()
        ir.relationships.append(
            make_relationship(
                target_symbol_id="sym_missing",
                resolution_status=ResolutionStatus.RESOLVED_EXACT,
                confidence=1.0,
            )
        )
        problems = ir.problems()
        self.assertTrue(any("target sym_missing does not exist" in p for p in problems))

    def test_duplicate_symbol_ids_are_detected(self) -> None:
        ir = self._ir_with_one_file_and_symbol()
        ir.symbols.append(make_symbol(id="sym_1", qualified_name="m:Other"))
        self.assertIn("duplicate symbol IDs detected", ir.problems())

    def test_duplicate_relationship_ids_are_detected(self) -> None:
        ir = self._ir_with_one_file_and_symbol()
        edge = make_relationship()
        ir.relationships.extend([edge, make_relationship(id=edge.id)])
        self.assertIn("duplicate relationship IDs detected", ir.problems())

    def test_evidence_for_a_missing_file_is_rejected(self) -> None:
        ir = self._ir_with_one_file_and_symbol()
        ir.evidence.append(
            Evidence(
                id="ev_1", entity_id="sym_1", file_id="file_missing",
                start_line=1, end_line=1, retrieval_source="offline.ast",
                score=1.0, model_version="mv_1",
            )
        )
        self.assertTrue(any("file_id file_missing does not exist" in p for p in ir.problems()))

    def test_a_chunk_for_a_missing_symbol_is_rejected(self) -> None:
        ir = self._ir_with_one_file_and_symbol()
        ir.chunks.append(
            SemanticChunk(
                id="chunk_1", symbol_id="sym_missing", text="x", chunk_type="class",
                embedding_id=None, token_count=1, model_version="mv_1",
            )
        )
        self.assertTrue(any("symbol_id sym_missing does not exist" in p for p in ir.problems()))

    def test_validation_never_raises_on_a_broken_model(self) -> None:
        ir = SemanticIR(model_version="")
        ir.symbols.append(make_symbol(file_id="file_gone", location=SourceSpan(0, -1, 0, -1)))
        ir.relationships.append(make_relationship(source_symbol_id="nope", confidence=9.0))
        self.assertIsInstance(ir.problems(), list)
        self.assertFalse(ir.is_valid())

    def test_counts_reports_every_collection(self) -> None:
        counts = self._ir_with_one_file_and_symbol().counts()
        self.assertEqual(
            set(counts),
            {
                "files", "symbols", "relationships", "bindings", "evidence",
                "chunks", "diagnostics", "degraded_files",
            },
        )
        self.assertEqual(counts["files"], 1)
        self.assertEqual(counts["symbols"], 1)


def make_binding(**overrides: object) -> Binding:
    values: dict[str, object] = {
        "id": "bind_1",
        "file_id": "file_1",
        "bound_name": "repository",
        "type_name": "PaymentRepository",
        "scope": BindingScope.INSTANCE,
        "location": SPAN,
        "model_version": "mv_1",
        "enclosing_symbol_id": None,
    }
    values.update(overrides)
    return Binding(**values)  # type: ignore[arg-type]


class BindingTests(unittest.TestCase):
    def test_a_well_formed_binding_has_no_problems(self) -> None:
        self.assertEqual(make_binding().problems(), [])

    def test_names_and_types_are_required(self) -> None:
        self.assertTrue(
            any("bound_name is empty" in p for p in make_binding(bound_name="").problems())
        )
        self.assertTrue(
            any("type_name is empty" in p for p in make_binding(type_name="").problems())
        )

    def test_ownership_fields_are_required(self) -> None:
        self.assertTrue(
            any("file_id is empty" in p for p in make_binding(file_id="").problems())
        )
        self.assertTrue(
            any(
                "model_version is empty" in p
                for p in make_binding(model_version="").problems()
            )
        )

    def test_an_invalid_location_is_reported_through_the_binding(self) -> None:
        problems = make_binding(location=SourceSpan(0, 0, 0, 0)).problems()
        self.assertTrue(any(p.startswith("location:") for p in problems))

    def test_scope_serialises_to_its_bare_value(self) -> None:
        self.assertEqual(make_binding().to_dict()["scope"], "INSTANCE")

    def test_an_enclosing_symbol_is_optional(self) -> None:
        """A binding outside any declaration is still a valid observation."""
        self.assertIsNone(make_binding().to_dict()["enclosing_symbol_id"])

    def test_validation_never_raises(self) -> None:
        broken = make_binding(
            bound_name="", type_name="", file_id="", model_version="",
            location=SourceSpan(0, -1, 0, -1),
        )
        self.assertIsInstance(broken.problems(), list)
        self.assertGreaterEqual(len(broken.problems()), 4)


class BindingIntegrityTests(unittest.TestCase):
    """A binding must reference entities that exist in the same model."""

    def _ir(self) -> SemanticIR:
        ir = SemanticIR(model_version="mv_1")
        record = make_file()
        ir.files.append(record)
        ir.symbols.append(make_symbol(id="sym_1", file_id=record.id))
        return ir

    def test_a_binding_for_a_missing_file_is_rejected(self) -> None:
        ir = self._ir()
        ir.bindings.append(make_binding(file_id="file_missing"))
        self.assertTrue(
            any("file_id file_missing does not exist" in p for p in ir.problems())
        )

    def test_a_binding_naming_a_missing_enclosing_symbol_is_rejected(self) -> None:
        ir = self._ir()
        ir.bindings.append(
            make_binding(file_id=ir.files[0].id, enclosing_symbol_id="sym_gone")
        )
        self.assertTrue(
            any("enclosing_symbol_id sym_gone does not exist" in p for p in ir.problems())
        )

    def test_a_consistent_binding_is_accepted(self) -> None:
        ir = self._ir()
        ir.bindings.append(
            make_binding(file_id=ir.files[0].id, enclosing_symbol_id="sym_1")
        )
        self.assertEqual(ir.problems(), [])

    def test_bindings_are_serialised_into_the_model(self) -> None:
        ir = self._ir()
        ir.bindings.append(
            make_binding(file_id=ir.files[0].id, enclosing_symbol_id="sym_1")
        )
        payload = ir.to_dict()
        self.assertEqual(len(payload["bindings"]), 1)
        self.assertEqual(payload["counts"]["bindings"], 1)
        self.assertEqual(payload["bindings"][0]["bound_name"], "repository")


class ChangeSetTests(unittest.TestCase):
    def test_scheduled_for_parse_covers_new_changed_and_renamed(self) -> None:
        changes = ChangeSet(
            previous_version="mv_1",
            current_version="mv_2",
            new=["c.py"],
            changed=["a.py"],
            deleted=["gone.py"],
            unchanged=["b.py"],
            renamed=[("old.py", "new.py")],
        )
        self.assertEqual(
            changes.scheduled_for_parse, ["a.py", "c.py", "new.py"]
        )

    def test_a_deletion_alone_does_not_schedule_any_parse(self) -> None:
        changes = ChangeSet(
            previous_version="mv_1", current_version="mv_2", deleted=["gone.py"]
        )
        self.assertEqual(changes.scheduled_for_parse, [])
        self.assertFalse(changes.is_empty)

    def test_an_empty_change_set_reports_itself_empty(self) -> None:
        changes = ChangeSet(
            previous_version="mv_1", current_version="mv_1", unchanged=["a.py"]
        )
        self.assertTrue(changes.is_empty)
        self.assertEqual(changes.scheduled_for_parse, [])

    def test_statistics_include_the_scheduled_count(self) -> None:
        changes = ChangeSet(
            previous_version=None,
            current_version="mv_1",
            new=["a.py", "b.py"],
            unchanged=["c.py"],
        )
        stats = changes.statistics()
        self.assertEqual(stats["new"], 2)
        self.assertEqual(stats["unchanged"], 1)
        self.assertEqual(stats["scheduled"], 2)

    def test_renames_serialise_as_pairs(self) -> None:
        changes = ChangeSet(
            previous_version="mv_1", current_version="mv_2", renamed=[("a.py", "b.py")]
        )
        self.assertEqual(changes.to_dict()["renamed"], [["a.py", "b.py"]])


if __name__ == "__main__":
    unittest.main()
