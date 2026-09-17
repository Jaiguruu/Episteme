"""Stage 5 — semantic IR tests.

Covers section 12 acceptance: stable entity IDs, no collisions, valid
references, evidence pointing at real source, every entity versioned, and
invalid objects rejected before indexing.
"""

from __future__ import annotations

import unittest

from maat.core import ids as idgen
from maat.core.contracts import FileRecord, Relationship, SemanticIR, Symbol
from maat.core.enums import (
    BindingScope,
    FileKind,
    ParseStatus,
    RelationshipType,
    ResolutionStatus,
    SymbolType,
)
from maat.core.locations import SourceSpan
from maat.offline.ir_builder import build_file_ir
from maat.offline.extractors.query_extractor import QueryExtractor
from maat.offline.parser import TreeSitterParser

SOURCE = b'''"""Module docstring."""

from models.payment import Payment


class PaymentService:
    """Handles payments."""

    def process(self, payment):
        self.validate(payment)
        return True

    def validate(self, payment):
        return True


class Other:
    def process(self, payment):
        return False
'''


def build(source: bytes = SOURCE, path: str = "services/payment_service.py", version: str = "mv_1"):
    outcome = TreeSitterParser().parse(source, "python", path)
    facts = QueryExtractor().extract(outcome, path)
    record = FileRecord(
        path=path,
        language="python",
        content_hash="sha256:test",
        size=len(source),
        parse_status=outcome.status,
        parse_error=None,
        model_version=version,
        file_kind=FileKind.SOURCE,
    )
    return build_file_ir(facts, record, source, version)


class IdentityTests(unittest.TestCase):
    def test_identical_source_produces_identical_ids(self) -> None:
        first = {s.qualified_name: s.id for s in build().symbols}
        second = {s.qualified_name: s.id for s in build().symbols}
        self.assertEqual(first, second)

    def test_ids_are_independent_of_model_version(self) -> None:
        """Version is an attribute, not part of identity.

        Otherwise an unchanged symbol would get a new ID on every reindex and
        incremental reuse would be impossible.
        """
        first = {s.qualified_name: s.id for s in build(version="mv_1").symbols}
        second = {s.qualified_name: s.id for s in build(version="mv_2").symbols}
        self.assertEqual(first, second)

    def test_different_symbols_do_not_collide(self) -> None:
        symbols = build().symbols
        self.assertEqual(len({s.id for s in symbols}), len(symbols))

    def test_same_name_in_different_files_does_not_collide(self) -> None:
        first = idgen.symbol_id("a.py", "CLASS", "a:Shared")
        second = idgen.symbol_id("b.py", "CLASS", "b:Shared")
        self.assertNotEqual(first, second)

    def test_same_name_different_kind_does_not_collide(self) -> None:
        first = idgen.symbol_id("a.py", "CLASS", "a:Thing")
        second = idgen.symbol_id("a.py", "FUNCTION", "a:Thing")
        self.assertNotEqual(first, second)

    def test_qualified_names_are_well_formed(self) -> None:
        for symbol in build().symbols:
            self.assertTrue(symbol.qualified_name)
            if symbol.symbol_type is not SymbolType.MODULE:
                self.assertIn(":", symbol.qualified_name)

    def test_overloads_are_disambiguated(self) -> None:
        """Two same-named methods must not share an ID."""
        source = (
            b"class Overloaded:\n"
            b"    def process(self, a):\n        return 1\n\n"
            b"    def process(self, a, b):\n        return 2\n"
        )
        result = build(source, "overloaded.py")
        process_ids = [
            s.id for s in result.symbols if s.name == "process"
        ]
        self.assertEqual(len(process_ids), 2)
        self.assertEqual(len(set(process_ids)), 2)

    def test_overload_disambiguation_is_stable(self) -> None:
        source = (
            b"class Overloaded:\n"
            b"    def process(self, a):\n        return 1\n\n"
            b"    def process(self, a, b):\n        return 2\n"
        )
        first = {s.qualified_name: s.id for s in build(source, "o.py").symbols}
        second = {s.qualified_name: s.id for s in build(source, "o.py").symbols}
        self.assertEqual(first, second)


class VersionIdentityTests(unittest.TestCase):
    """D27: version identity gains a pipeline fingerprint.

    Before M2 a version ID was a pure function of file content, which was correct
    while the pipeline only observed. Resolution rewrites relationship targets
    without touching a file, so without a second dimension two different models
    built from the same bytes would share a version ID -- and incremental reuse
    keys off that ID.
    """

    CONTENT = "0123456789abcdef"  # synthetic digest, never a real model version

    def test_same_content_and_pipeline_is_stable(self) -> None:
        first = idgen.model_version_id(self.CONTENT)
        second = idgen.model_version_id(self.CONTENT)
        self.assertEqual(first, second)

    def test_same_content_different_pipeline_differs(self) -> None:
        offline = idgen.model_version_id(self.CONTENT, "offline;semantic=absent")
        resolved = idgen.model_version_id(self.CONTENT, "offline;semantic=6-8")
        self.assertNotEqual(offline, resolved)

    def test_fingerprint_change_does_not_disturb_entity_ids(self) -> None:
        """Only the version ID moves. Symbols must stay recognisable.

        If bumping the fingerprint renamed every symbol, incremental reuse would
        be destroyed by the very change meant to protect it.
        """
        before = idgen.symbol_id("a.py", "CLASS", "a:Thing")
        after = idgen.symbol_id("a.py", "CLASS", "a:Thing")
        self.assertEqual(before, after)

    def test_fingerprint_is_a_source_constant(self) -> None:
        """It must not be read from the environment or a clock.

        Section 9 AC2 requires a no-change run to reuse everything; a fingerprint
        that varied per run would mint a new version every time.
        """
        self.assertIsInstance(idgen.PIPELINE_FINGERPRINT, str)
        self.assertTrue(idgen.PIPELINE_FINGERPRINT)


class RelationshipTests(unittest.TestCase):
    def test_contains_is_resolved_exactly(self) -> None:
        """Containment is structural, so it is known with certainty."""
        result = build()
        contains = [
            r for r in result.relationships
            if r.relationship_type is RelationshipType.CONTAINS
        ]
        self.assertTrue(contains)
        for relationship in contains:
            self.assertEqual(
                relationship.resolution_status, ResolutionStatus.RESOLVED_EXACT
            )
            self.assertEqual(relationship.confidence, 1.0)

    def test_references_are_unresolved(self) -> None:
        """Section 4.2: never guess a target. M1 does not resolve references."""
        result = build()
        for relationship in result.relationships:
            if relationship.relationship_type is RelationshipType.CONTAINS:
                continue
            self.assertEqual(
                relationship.resolution_status, ResolutionStatus.UNRESOLVED
            )
            self.assertEqual(relationship.confidence, 0.0)
            self.assertTrue(relationship.target_name)

    def test_unresolved_targets_use_the_placeholder_scheme(self) -> None:
        result = build()
        for relationship in result.relationships:
            if relationship.relationship_type is RelationshipType.CONTAINS:
                continue
            self.assertTrue(
                idgen.is_unresolved_target(relationship.target_symbol_id),
                relationship.target_symbol_id,
            )

    def test_calls_are_recorded_with_their_site(self) -> None:
        result = build()
        calls = [
            r for r in result.relationships
            if r.relationship_type is RelationshipType.CALLS
        ]
        self.assertTrue(calls)
        self.assertIn("self.validate", {r.target_name for r in calls})

    def test_two_calls_on_one_line_get_distinct_ids(self) -> None:
        """Line alone is not enough to identify a call site."""
        source = b"def f():\n    return g(); g()\n"
        result = build(source, "calls.py")
        ids = [r.id for r in result.relationships if r.relationship_type is RelationshipType.CALLS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_relationship_ids_are_unique(self) -> None:
        result = build()
        ids = [r.id for r in result.relationships]
        self.assertEqual(len(ids), len(set(ids)))


class EvidenceTests(unittest.TestCase):
    def test_every_symbol_has_evidence(self) -> None:
        result = build()
        covered = {e.entity_id for e in result.evidence}
        for symbol in result.symbols:
            self.assertIn(symbol.id, covered, symbol.qualified_name)

    def test_evidence_points_at_real_lines(self) -> None:
        result = build()
        line_count = SOURCE.decode().count("\n") + 1
        for evidence in result.evidence:
            self.assertGreaterEqual(evidence.start_line, 1)
            self.assertLessEqual(evidence.end_line, line_count)
            self.assertLessEqual(evidence.start_line, evidence.end_line)

    def test_evidence_is_labelled_as_offline_provenance(self) -> None:
        result = build()
        self.assertTrue(result.evidence)
        for evidence in result.evidence:
            self.assertEqual(evidence.retrieval_source, "offline.ast")

    def test_evidence_belongs_to_the_model_version(self) -> None:
        result = build(version="mv_7")
        for evidence in result.evidence:
            self.assertEqual(evidence.model_version, "mv_7")


class ChunkTests(unittest.TestCase):
    def test_symbols_produce_chunks(self) -> None:
        result = build()
        symbol_ids = {s.id for s in result.symbols}
        for chunk in result.chunks:
            self.assertIn(chunk.symbol_id, symbol_ids)

    def test_imports_chunk_is_always_present(self) -> None:
        result = build()
        self.assertIn("imports", {c.chunk_type for c in result.chunks})

    def test_imports_chunk_says_when_there_are_none(self) -> None:
        result = build(b"value = 1\n", "plain.py")
        imports = [c for c in result.chunks if c.chunk_type == "imports"]
        self.assertEqual(len(imports), 1)
        self.assertIn("no imports", imports[0].text)

    def test_parse_error_chunk_appears_for_degraded_files(self) -> None:
        result = build(b"def broken(:\n    pass\n", "broken.py")
        self.assertIn("parse_error", {c.chunk_type for c in result.chunks})

    def test_chunk_text_is_the_symbol_source(self) -> None:
        result = build()
        by_id = {s.id: s for s in result.symbols}
        target = next(
            s for s in result.symbols if s.name == "PaymentService"
        )
        chunk = next(
            c for c in result.chunks
            if c.symbol_id == target.id and c.chunk_type == "class"
        )
        self.assertIn("class PaymentService", chunk.text)
        self.assertEqual(by_id[target.id].id, target.id)

    def test_token_counts_are_positive(self) -> None:
        result = build()
        for chunk in result.chunks:
            if chunk.text:
                self.assertGreater(chunk.token_count, 0)


class ValidationTests(unittest.TestCase):
    def test_built_model_has_no_problems(self) -> None:
        result = build()
        ir = SemanticIR(
            model_version="mv_1",
            files=[_file_record()],
            symbols=result.symbols,
            relationships=result.relationships,
            evidence=result.evidence,
            chunks=result.chunks,
            diagnostics=result.diagnostics,
        )
        self.assertEqual(ir.problems(), [])

    def test_relationship_pointing_at_a_missing_symbol_is_rejected(self) -> None:
        result = build()
        ir = SemanticIR(
            model_version="mv_1",
            files=[_file_record()],
            symbols=result.symbols,
            relationships=[
                Relationship(
                    id="rel_bogus",
                    source_symbol_id="sym_missing",
                    target_symbol_id=result.symbols[0].id,
                    relationship_type=RelationshipType.CALLS,
                    resolution_status=ResolutionStatus.RESOLVED_EXACT,
                    confidence=1.0,
                    source_location=SourceSpan.point(1, 0),
                    model_version="mv_1",
                )
            ],
        )
        problems = ir.problems()
        self.assertTrue(any("does not exist" in p for p in problems), problems)

    def test_invalid_symbol_is_rejected_before_indexing(self) -> None:
        bad = Symbol(
            id="sym_x",
            file_id="file_x",
            name="",
            qualified_name="bad",
            symbol_type=SymbolType.CLASS,
            signature=None,
            location=SourceSpan(1, 0, 1, 0),
            documentation=None,
            content_hash="sha256:x",
            model_version="mv_1",
        )
        problems = bad.problems()
        self.assertTrue(any("name is empty" in p for p in problems))
        self.assertTrue(any("qualified_name" in p for p in problems))

    def test_symbol_referencing_a_missing_file_is_rejected(self) -> None:
        result = build()
        ir = SemanticIR(model_version="mv_1", files=[], symbols=result.symbols)
        problems = ir.problems()
        self.assertTrue(any("does not exist" in p for p in problems))

    def test_invalid_location_is_reported(self) -> None:
        span = SourceSpan(start_line=5, start_col=0, end_line=2, end_col=0)
        self.assertFalse(span.is_valid())
        self.assertTrue(any("precedes" in p for p in span.problems()))

    def test_duplicate_ids_are_detected(self) -> None:
        result = build()
        duplicated = result.symbols[0]
        ir = SemanticIR(
            model_version="mv_1",
            files=[_file_record()],
            symbols=[duplicated, duplicated],
        )
        self.assertTrue(any("duplicate" in p for p in ir.problems()))

    def test_confidence_must_match_resolution_status(self) -> None:
        relationship = Relationship(
            id="rel_x",
            source_symbol_id="a",
            target_symbol_id="b",
            relationship_type=RelationshipType.CALLS,
            resolution_status=ResolutionStatus.UNRESOLVED,
            confidence=0.8,
            source_location=SourceSpan.point(1, 0),
            model_version="mv_1",
            target_name="b",
        )
        self.assertTrue(
            any("UNRESOLVED requires" in p for p in relationship.problems())
        )


def _file_record() -> FileRecord:
    return FileRecord(
        path="services/payment_service.py",
        language="python",
        content_hash="sha256:test",
        size=len(SOURCE),
        parse_status=ParseStatus.OK,
        parse_error=None,
        model_version="mv_1",
        file_kind=FileKind.SOURCE,
    )


BINDING_SOURCE = b'''from repositories.payment_repository import PaymentRepository


class CheckoutService:
    def __init__(self, repository: PaymentRepository):
        self.repository = repository

    def checkout(self, amount: float):
        local = CheckoutService(repository=self.repository)
        return self.repository.save(local)
'''

REBINDING_SOURCE = b'''class A:
    pass


class B:
    pass


def f():
    x = A()
    x = B()
'''


class BindingTests(unittest.TestCase):
    """Bindings must survive the Tier 2 -> Tier 3 boundary (D34).

    A call site records ``receiver="self.repository"`` as raw text, and nothing in
    the tree says what type ``repository`` holds. Until bindings reached the model
    they were extracted and then dropped, so Stage 6 had nothing to resolve a
    member call with.
    """

    def test_bindings_reach_the_model(self) -> None:
        result = build(BINDING_SOURCE, "services/checkout_service.py")
        self.assertEqual(len(result.bindings), 4)

    def test_binding_ids_are_stable_across_runs(self) -> None:
        first = sorted(b.id for b in build(BINDING_SOURCE).bindings)
        second = sorted(b.id for b in build(BINDING_SOURCE).bindings)
        self.assertEqual(first, second)

    def test_binding_ids_are_independent_of_model_version(self) -> None:
        """Version is an attribute, not part of identity — the same rule as symbols."""
        first = sorted(b.id for b in build(BINDING_SOURCE, version="mv_1").bindings)
        second = sorted(b.id for b in build(BINDING_SOURCE, version="mv_2").bindings)
        self.assertEqual(first, second)

    def test_binding_ids_are_self_describing(self) -> None:
        for binding in build(BINDING_SOURCE).bindings:
            self.assertTrue(binding.id.startswith("bind_"), binding.id)

    def test_type_name_is_carried_through_raw(self) -> None:
        """Resolution is Stage 6's job; the model records what the source said."""
        names = {b.type_name for b in build(BINDING_SOURCE).bindings}
        self.assertIn("PaymentRepository", names)
        self.assertIn("CheckoutService", names)

    def test_every_scope_is_preserved(self) -> None:
        scopes = {b.scope for b in build(BINDING_SOURCE).bindings}
        self.assertEqual(
            scopes,
            {BindingScope.PARAMETER, BindingScope.INSTANCE, BindingScope.LOCAL},
        )

    def test_a_binding_records_its_enclosing_symbol(self) -> None:
        result = build(BINDING_SOURCE)
        symbol_ids = {s.id for s in result.symbols}
        for binding in result.bindings:
            with self.subTest(binding=binding.bound_name, scope=str(binding.scope)):
                self.assertIsNotNone(binding.enclosing_symbol_id)
                self.assertIn(binding.enclosing_symbol_id, symbol_ids)

    def test_rebinding_produces_two_distinct_bindings(self) -> None:
        """``x = A(); x = B()`` is two genuine bindings, not one.

        Collapsing them would move the resolver's "last write wins" decision out
        of Stage 6 and into the extractor.
        """
        bindings = [
            b
            for b in build(REBINDING_SOURCE, "mod.py").bindings
            if b.bound_name == "x"
        ]
        self.assertEqual(len(bindings), 2)
        self.assertEqual(len({b.id for b in bindings}), 2)

    def test_every_binding_carries_the_model_version(self) -> None:
        for binding in build(BINDING_SOURCE, version="mv_9").bindings:
            self.assertEqual(binding.model_version, "mv_9")

    def test_bindings_are_validated(self) -> None:
        for binding in build(BINDING_SOURCE).bindings:
            self.assertEqual(binding.problems(), [], binding.id)


if __name__ == "__main__":
    unittest.main()
