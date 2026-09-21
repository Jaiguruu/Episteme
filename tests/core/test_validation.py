"""The validator in ``maat/core/validation.py``.

Covers section 14 (relationship validation, AC1-AC6) and decision D29. Validation is
a pure function of the model, so these tests build models in memory and touch no disk.

The important property under test is not just that defects are found, but that the
*right* things are treated as defects: an unresolved edge is correct behaviour, and a
validator that rejected it would make M1's own output unpublishable.
"""

from __future__ import annotations

import json
import unittest

from maat.core.contracts import (
    Binding,
    Evidence,
    FileRecord,
    Relationship,
    SemanticChunk,
    SemanticIR,
    Symbol,
)
from maat.core.enums import (
    BindingScope,
    DiagnosticSeverity,
    ParseStatus,
    RelationshipType,
    ResolutionStatus,
    SymbolType,
)
from maat.core.locations import SourceSpan
from maat.core.validation import (
    CODE_AMBIGUOUS_EDGES,
    CODE_DUPLICATE_EDGE,
    CODE_HEURISTIC_EDGE,
    CODE_HEURISTIC_LOW,
    CODE_MODEL_PROBLEM,
    CODE_ORPHAN_EVIDENCE,
    CODE_REPEATED_EDGE,
    CODE_UNRESOLVED_EDGES,
    CODE_VERSION_MISMATCH,
    HEURISTIC_MIN,
    deduplicate_edges,
    validate_ir,
)

VERSION = "mv_test"


def point(line: int = 1, col: int = 0) -> SourceSpan:
    return SourceSpan.point(line, col)


def inverted_span() -> SourceSpan:
    """A span whose end precedes its start. Invalid by construction."""
    return SourceSpan(start_line=10, start_col=0, end_line=2, end_col=0)


def make_file(path: str = "a.py", model_version: str = VERSION) -> FileRecord:
    return FileRecord(
        path=path,
        language="python",
        content_hash=f"hash_{path}",
        size=0,
        parse_status=ParseStatus.OK,
        parse_error=None,
        model_version=model_version,
        id=f"file_{path}",
    )


def make_symbol(
    file_id: str,
    qualified_name: str,
    name: str | None = None,
    symbol_type: SymbolType = SymbolType.CLASS,
    model_version: str = VERSION,
) -> Symbol:
    local = qualified_name.partition(":")[2] or qualified_name
    return Symbol(
        id="sym_" + qualified_name.replace(".", "_").replace(":", "_"),
        file_id=file_id,
        name=name or local.rsplit(".", 1)[-1],
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        signature=None,
        location=point(),
        documentation=None,
        content_hash="hash",
        model_version=model_version,
    )


def make_relationship(
    source_id: str,
    target_id: str,
    relationship_id: str = "rel_1",
    relationship_type: RelationshipType = RelationshipType.CONTAINS,
    resolution_status: ResolutionStatus = ResolutionStatus.RESOLVED_EXACT,
    confidence: float = 1.0,
    location: SourceSpan | None = None,
    target_name: str | None = None,
    candidate_symbol_ids: list[str] | None = None,
    model_version: str = VERSION,
) -> Relationship:
    return Relationship(
        id=relationship_id,
        source_symbol_id=source_id,
        target_symbol_id=target_id,
        relationship_type=relationship_type,
        resolution_status=resolution_status,
        confidence=confidence,
        source_location=location or point(),
        model_version=model_version,
        target_name=target_name,
        candidate_symbol_ids=candidate_symbol_ids or [],
    )


def make_evidence(
    entity_id: str, file_id: str, evidence_id: str = "ev_1"
) -> Evidence:
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


def make_chunk(symbol_id: str, chunk_id: str = "chunk_1") -> SemanticChunk:
    return SemanticChunk(
        id=chunk_id,
        symbol_id=symbol_id,
        text="def run(): pass",
        chunk_type="function",
        embedding_id=None,
        token_count=4,
        model_version=VERSION,
    )


class _Model:
    """A clean model that tests then damage in one specific way.

    Starting from a valid model matters: a defect test proves nothing if the model
    was already failing for an unrelated reason.
    """

    def __init__(self) -> None:
        self.ir = SemanticIR(model_version=VERSION)
        self.record = make_file()
        self.ir.files.append(self.record)
        self.module = make_symbol(
            self.record.id, "a.py", "a", SymbolType.MODULE
        )
        self.thing = make_symbol(self.record.id, "a.py:Thing", "Thing")
        self.ir.symbols.extend([self.module, self.thing])
        self.ir.relationships.append(
            make_relationship(self.module.id, self.thing.id, "rel_contains")
        )
        self.ir.evidence.append(make_evidence(self.thing.id, self.record.id))
        self.ir.chunks.append(make_chunk(self.thing.id))

    def add_edge(self, **kwargs) -> Relationship:
        kwargs.setdefault("source_id", self.thing.id)
        kwargs.setdefault("target_id", self.thing.id)
        relationship = make_relationship(**kwargs)
        self.ir.relationships.append(relationship)
        return relationship

    def validate(self):
        return validate_ir(self.ir)

    def codes(self, report) -> set[str]:
        return {finding.code for finding in report.findings}


class DuplicateEdgeTests(unittest.TestCase):
    """Section 14 AC1 -- duplicate relationships are removed or rejected."""

    def test_an_exact_duplicate_is_an_error(self) -> None:
        model = _Model()
        model.add_edge(relationship_id="rel_a")
        model.add_edge(relationship_id="rel_b")

        report = model.validate()

        self.assertFalse(report.is_valid)
        self.assertTrue(report.blocks_publication)
        self.assertEqual(report.duplicate_edges, 1)
        self.assertIn(CODE_DUPLICATE_EDGE, model.codes(report))

    def test_the_duplicate_names_the_edge_it_repeats(self) -> None:
        model = _Model()
        model.add_edge(relationship_id="rel_a")
        model.add_edge(relationship_id="rel_b")

        report = model.validate()
        finding = next(
            f for f in report.findings if f.code == CODE_DUPLICATE_EDGE
        )

        self.assertEqual(finding.details["duplicate_of"], "rel_a")
        self.assertEqual(finding.entity_id, "rel_b")

    def test_the_same_edge_at_a_different_location_is_not_a_duplicate(self) -> None:
        """D14: two call sites on different lines are two distinct relationships."""
        model = _Model()
        model.add_edge(relationship_id="rel_a", location=point(5, 0))
        model.add_edge(relationship_id="rel_b", location=point(9, 0))

        report = model.validate()

        self.assertTrue(report.is_valid)
        self.assertNotIn(CODE_DUPLICATE_EDGE, model.codes(report))
        self.assertIn(CODE_REPEATED_EDGE, model.codes(report))

    def test_a_repeat_is_reported_as_info_not_an_error(self) -> None:
        model = _Model()
        model.add_edge(relationship_id="rel_a", location=point(5, 0))
        model.add_edge(relationship_id="rel_b", location=point(9, 0))

        report = model.validate()
        finding = next(f for f in report.findings if f.code == CODE_REPEATED_EDGE)

        self.assertIs(finding.severity, DiagnosticSeverity.INFO)
        self.assertEqual(finding.details["relationship_ids"], ["rel_a", "rel_b"])

    def test_deduplicate_edges_removes_exact_duplicates(self) -> None:
        model = _Model()
        model.add_edge(relationship_id="rel_a")
        model.add_edge(relationship_id="rel_b")
        before = len(model.ir.relationships)

        removed = deduplicate_edges(model.ir)

        self.assertEqual(removed, ["rel_b"])
        self.assertEqual(len(model.ir.relationships), before - 1)
        self.assertTrue(model.validate().is_valid)

    def test_deduplicate_edges_keeps_distinct_call_sites(self) -> None:
        model = _Model()
        model.add_edge(relationship_id="rel_a", location=point(5, 0))
        model.add_edge(relationship_id="rel_b", location=point(9, 0))
        before = len(model.ir.relationships)

        removed = deduplicate_edges(model.ir)

        self.assertEqual(removed, [])
        self.assertEqual(len(model.ir.relationships), before)

    def test_duplicate_ids_are_still_caught_by_problems(self) -> None:
        """Delegation: the existing duplicate-ID check must keep working."""
        model = _Model()
        model.add_edge(relationship_id="rel_contains")

        report = model.validate()

        self.assertFalse(report.is_valid)
        self.assertIn(CODE_MODEL_PROBLEM, model.codes(report))
        self.assertTrue(
            any("duplicate relationship IDs" in p for p in report.problems)
        )


class MissingEntityTests(unittest.TestCase):
    """Section 14 AC2 -- relationships referencing missing entities are rejected."""

    def test_a_dangling_source_symbol_is_an_error(self) -> None:
        model = _Model()
        model.add_edge(source_id="sym_missing", target_id=model.thing.id)

        report = model.validate()

        self.assertFalse(report.is_valid)
        self.assertIn(CODE_MODEL_PROBLEM, model.codes(report))

    def test_a_dangling_target_symbol_is_an_error(self) -> None:
        model = _Model()
        model.add_edge(source_id=model.thing.id, target_id="sym_missing")

        report = model.validate()

        self.assertFalse(report.is_valid)
        self.assertIn(CODE_MODEL_PROBLEM, model.codes(report))

    def test_a_placeholder_target_is_not_treated_as_missing(self) -> None:
        """An unresolved edge names a placeholder, and that is not a defect."""
        model = _Model()
        model.add_edge(
            source_id=model.thing.id,
            target_id="unresolved:call:ghost",
            relationship_type=RelationshipType.CALLS,
            resolution_status=ResolutionStatus.UNRESOLVED,
            confidence=0.0,
            target_name="ghost",
        )

        report = model.validate()

        self.assertTrue(report.is_valid)
        self.assertNotIn(CODE_MODEL_PROBLEM, model.codes(report))

    def test_orphan_evidence_is_an_error(self) -> None:
        """The gap this module fills: problems() checks file_id, not entity_id."""
        model = _Model()
        model.ir.evidence.append(
            make_evidence("sym_nowhere", model.record.id, "ev_orphan")
        )

        report = model.validate()

        self.assertFalse(report.is_valid)
        self.assertEqual(report.orphan_entities, 1)
        finding = next(f for f in report.findings if f.code == CODE_ORPHAN_EVIDENCE)
        self.assertEqual(finding.details["missing_entity_id"], "sym_nowhere")

    def test_evidence_pointing_at_a_relationship_is_not_orphan(self) -> None:
        model = _Model()
        edge = model.ir.relationships[0]
        model.ir.evidence.append(make_evidence(edge.id, model.record.id, "ev_edge"))

        report = model.validate()

        self.assertTrue(report.is_valid)
        self.assertEqual(report.orphan_entities, 0)


class SourceLocationTests(unittest.TestCase):
    """Section 14 AC3 -- invalid source locations are rejected."""

    def test_an_inverted_span_is_an_error(self) -> None:
        model = _Model()
        model.add_edge(
            source_id=model.thing.id,
            target_id=model.thing.id,
            relationship_id="rel_bad_span",
            location=inverted_span(),
        )

        report = model.validate()

        self.assertFalse(report.is_valid)
        self.assertIn(CODE_MODEL_PROBLEM, model.codes(report))
        self.assertTrue(any("precedes start" in p for p in report.problems))

    def test_a_valid_span_produces_no_finding(self) -> None:
        model = _Model()
        model.add_edge(
            source_id=model.thing.id,
            target_id=model.thing.id,
            relationship_id="rel_ok",
            location=SourceSpan(start_line=1, start_col=0, end_line=3, end_col=8),
        )

        report = model.validate()

        self.assertTrue(report.is_valid)
        self.assertEqual(report.problems, [])


class ResolutionSeverityTests(unittest.TestCase):
    """Section 14 AC4 and D29 -- unresolved is reported, never failed."""

    def test_an_all_unresolved_model_is_valid(self) -> None:
        """The M1 regression guard: M1 emits every edge unresolved by design."""
        model = _Model()
        for index in range(3):
            model.add_edge(
                source_id=model.thing.id,
                target_id=f"unresolved:call:ghost{index}",
                relationship_id=f"rel_u{index}",
                relationship_type=RelationshipType.CALLS,
                resolution_status=ResolutionStatus.UNRESOLVED,
                confidence=0.0,
                target_name=f"ghost{index}",
            )

        report = model.validate()

        self.assertTrue(report.is_valid)
        self.assertFalse(report.blocks_publication)
        self.assertEqual(report.counts()[DiagnosticSeverity.ERROR.value], 0)

    def test_unresolved_edges_are_reported_as_one_info_finding(self) -> None:
        model = _Model()
        for index in range(3):
            model.add_edge(
                source_id=model.thing.id,
                target_id=f"unresolved:call:ghost{index}",
                relationship_id=f"rel_u{index}",
                relationship_type=RelationshipType.CALLS,
                resolution_status=ResolutionStatus.UNRESOLVED,
                confidence=0.0,
                target_name=f"ghost{index}",
            )

        report = model.validate()
        findings = [f for f in report.findings if f.code == CODE_UNRESOLVED_EDGES]

        self.assertEqual(len(findings), 1)
        self.assertIs(findings[0].severity, DiagnosticSeverity.INFO)
        self.assertEqual(findings[0].details["count"], 3)
        self.assertEqual(report.unresolved_relationships, 3)

    def test_ambiguous_edges_are_reported_and_do_not_block(self) -> None:
        model = _Model()
        model.add_edge(
            source_id=model.thing.id,
            target_id="unresolved:call:shared",
            relationship_id="rel_amb",
            relationship_type=RelationshipType.CALLS,
            resolution_status=ResolutionStatus.AMBIGUOUS,
            confidence=0.0,
            target_name="shared",
            candidate_symbol_ids=[model.thing.id, model.module.id],
        )

        report = model.validate()

        self.assertTrue(report.is_valid)
        self.assertIn(CODE_AMBIGUOUS_EDGES, model.codes(report))
        self.assertEqual(report.ambiguous_relationships, 1)

    def test_ambiguous_without_candidates_is_an_error(self) -> None:
        """That rule already lives in Relationship.problems(); it must still fire."""
        model = _Model()
        model.add_edge(
            source_id=model.thing.id,
            target_id="unresolved:call:shared",
            relationship_id="rel_amb_bad",
            relationship_type=RelationshipType.CALLS,
            resolution_status=ResolutionStatus.AMBIGUOUS,
            confidence=0.0,
            target_name="shared",
        )

        report = model.validate()

        self.assertFalse(report.is_valid)
        self.assertIn(CODE_MODEL_PROBLEM, model.codes(report))


class ConfidencePolicyTests(unittest.TestCase):
    """Section 14 -- the confidence policy."""

    def _heuristic(self, confidence: float) -> _Model:
        model = _Model()
        model.add_edge(
            source_id=model.thing.id,
            target_id=model.thing.id,
            relationship_id="rel_h",
            relationship_type=RelationshipType.CALLS,
            resolution_status=ResolutionStatus.RESOLVED_HEURISTIC,
            confidence=confidence,
        )
        return model

    def test_a_heuristic_edge_below_the_threshold_is_a_warning(self) -> None:
        model = self._heuristic(HEURISTIC_MIN - 0.1)

        report = model.validate()
        finding = next(f for f in report.findings if f.code == CODE_HEURISTIC_LOW)

        self.assertIs(finding.severity, DiagnosticSeverity.WARNING)
        self.assertTrue(report.is_valid, "a warning must not block publication")

    def test_a_heuristic_edge_at_the_threshold_is_info(self) -> None:
        model = self._heuristic(HEURISTIC_MIN)

        report = model.validate()
        finding = next(f for f in report.findings if f.code == CODE_HEURISTIC_EDGE)

        self.assertIs(finding.severity, DiagnosticSeverity.INFO)
        self.assertTrue(report.is_valid)

    def test_no_heuristic_edges_means_no_confidence_finding(self) -> None:
        model = _Model()

        report = model.validate()

        self.assertNotIn(CODE_HEURISTIC_LOW, model.codes(report))
        self.assertNotIn(CODE_HEURISTIC_EDGE, model.codes(report))


class VersionConsistencyTests(unittest.TestCase):
    """Section 14 -- version consistency."""

    def test_a_mismatched_entity_version_is_an_error(self) -> None:
        model = _Model()
        model.ir.symbols.append(
            make_symbol(
                model.record.id,
                "a.py:Stale",
                "Stale",
                model_version="mv_other",
            )
        )

        report = model.validate()

        self.assertFalse(report.is_valid)
        finding = next(f for f in report.findings if f.code == CODE_VERSION_MISMATCH)
        self.assertEqual(finding.details["expected"], VERSION)
        self.assertEqual(finding.details["found"], "mv_other")

    def test_a_consistent_model_has_no_version_finding(self) -> None:
        model = _Model()

        report = model.validate()

        self.assertNotIn(CODE_VERSION_MISMATCH, model.codes(report))


class ReportShapeTests(unittest.TestCase):
    """Section 14 AC5 -- validation produces a machine-readable report."""

    def test_the_report_is_json_serialisable(self) -> None:
        model = _Model()
        model.add_edge(
            source_id=model.thing.id,
            target_id="unresolved:call:ghost",
            relationship_id="rel_u",
            relationship_type=RelationshipType.CALLS,
            resolution_status=ResolutionStatus.UNRESOLVED,
            confidence=0.0,
            target_name="ghost",
        )

        payload = json.dumps(model.validate().to_dict())

        self.assertIn(CODE_UNRESOLVED_EDGES, payload)

    def test_counts_sum_to_the_number_of_findings(self) -> None:
        model = _Model()
        model.add_edge(relationship_id="rel_a")
        model.add_edge(relationship_id="rel_b")

        report = model.validate()
        counts = report.counts()

        self.assertEqual(sum(counts.values()), len(report.findings))

    def test_the_report_is_deterministic(self) -> None:
        def once():
            model = _Model()
            model.add_edge(relationship_id="rel_a")
            model.add_edge(relationship_id="rel_b")
            return json.dumps(model.validate().to_dict())

        self.assertEqual(once(), once())

    def test_blocks_publication_exactly_when_an_error_exists(self) -> None:
        clean = _Model()
        self.assertFalse(clean.validate().blocks_publication)

        broken = _Model()
        broken.add_edge(relationship_id="rel_a")
        broken.add_edge(relationship_id="rel_b")
        report = broken.validate()

        self.assertTrue(report.blocks_publication)
        self.assertEqual(report.blocks_publication, bool(report.errors))

    def test_an_empty_model_is_valid(self) -> None:
        report = validate_ir(SemanticIR(model_version=VERSION))

        self.assertTrue(report.is_valid)
        self.assertEqual(report.findings, [])
        self.assertEqual(report.checked_relationships, 0)

    def test_the_raw_problems_are_preserved(self) -> None:
        model = _Model()
        model.add_edge(source_id="sym_missing", target_id=model.thing.id)

        report = model.validate()

        self.assertTrue(report.problems)
        self.assertEqual(
            report.problems,
            [f.message for f in report.findings if f.code == CODE_MODEL_PROBLEM],
        )

    def test_checked_relationships_counts_every_edge(self) -> None:
        model = _Model()
        model.add_edge(relationship_id="rel_a")

        report = model.validate()

        self.assertEqual(report.checked_relationships, 2)


class BindingAndChunkTests(unittest.TestCase):
    """The two collections with their own referential rules."""

    def test_a_valid_binding_and_chunk_produce_no_finding(self) -> None:
        model = _Model()
        model.ir.bindings.append(
            Binding(
                id="bind_1",
                file_id=model.record.id,
                bound_name="thing",
                type_name="Thing",
                scope=BindingScope.PARAMETER,
                location=point(),
                model_version=VERSION,
                enclosing_symbol_id=model.thing.id,
            )
        )

        report = model.validate()

        self.assertTrue(report.is_valid)

    def test_a_dangling_chunk_symbol_is_an_error(self) -> None:
        model = _Model()
        model.ir.chunks.append(make_chunk("sym_nowhere", "chunk_orphan"))

        report = model.validate()

        self.assertFalse(report.is_valid)
        self.assertIn(CODE_MODEL_PROBLEM, model.codes(report))


if __name__ == "__main__":
    unittest.main()
