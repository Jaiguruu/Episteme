"""Stage 6 acceptance tests: symbol and relationship resolution.

One class per acceptance criterion in spec section 13, plus a class per rung of
the D24 ladder. The names are the criteria, deliberately, so a failing test says
which part of the spec broke rather than only which function did.

Everything here builds a small model in memory and resolves it, rather than
reading `ir.json` from a checkout. Resolution is a pure function of the model, so
in-memory input keeps these tests about the *algorithm*; the end-to-end path over
`demo_repo` lives in `test_pipeline.py`.
"""

from __future__ import annotations

import unittest

from maat.core.contracts import (
    Binding,
    BindingScope,
    FileRecord,
    Relationship,
    SemanticIR,
    Symbol,
)
from maat.core.enums import ParseStatus, RelationshipType, ResolutionStatus, SymbolType
from maat.core.locations import SourceSpan
from maat.semantic import ResolutionRung, Resolver, resolve_ir
from maat.semantic.resolver import MAX_CANDIDATES, _ModelIndex

VERSION = "mv_test"


def span(line: int = 1) -> SourceSpan:
    return SourceSpan(
        start_line=line, start_col=0, end_line=line, end_col=10
    )


def make_file(path: str) -> FileRecord:
    return FileRecord(
        path=path,
        language="python",
        content_hash="0" * 16,
        size=1,
        parse_status=ParseStatus.OK,
        parse_error=None,
        model_version=VERSION,
        line_count=1,
    )


def make_symbol(
    file_id: str,
    qualified_name: str,
    name: str,
    symbol_type: SymbolType = SymbolType.FUNCTION,
) -> Symbol:
    return Symbol(
        id="sym_" + qualified_name.replace(".", "_").replace(":", "_"),
        file_id=file_id,
        name=name,
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        signature="",
        location=span(),
        documentation="",
        content_hash="1" * 16,
        model_version=VERSION,
    )


def make_call(
    source: Symbol, target_name: str, line: int = 1
) -> Relationship:
    key = f"{source.id}:{target_name}:{line}"
    return Relationship(
        id="rel_" + key.replace(".", "_").replace(":", "_"),
        source_symbol_id=source.id,
        target_symbol_id="unresolved:call:" + target_name,
        relationship_type=RelationshipType.CALLS,
        resolution_status=ResolutionStatus.UNRESOLVED,
        confidence=0.0,
        source_location=span(line),
        model_version=VERSION,
        target_name=target_name,
    )


def make_binding(
    file_id: str, owner: Symbol, bound_name: str, type_name: str, scope: BindingScope
) -> Binding:
    return Binding(
        id="bind_" + f"{owner.id}_{bound_name}".replace(".", "_").replace(":", "_"),
        file_id=file_id,
        bound_name=bound_name,
        type_name=type_name,
        scope=scope,
        location=span(),
        model_version=VERSION,
        enclosing_symbol_id=owner.id,
    )


class _Model:
    """A tiny model builder, so each test states only what it needs."""

    def __init__(self) -> None:
        self.ir = SemanticIR(model_version=VERSION)

    def file(self, path: str) -> FileRecord:
        record = make_file(path)
        self.ir.files.append(record)
        return record

    def symbol(
        self,
        record: FileRecord,
        qualified_name: str,
        name: str | None = None,
        symbol_type: SymbolType = SymbolType.FUNCTION,
    ) -> Symbol:
        symbol = make_symbol(
            record.id, qualified_name, name or qualified_name.rsplit(":", 1)[-1].rsplit(".", 1)[-1], symbol_type
        )
        self.ir.symbols.append(symbol)
        return symbol

    def call(self, source: Symbol, target: str, line: int = 1) -> Relationship:
        relationship = make_call(source, target, line)
        self.ir.relationships.append(relationship)
        return relationship

    def binding(
        self,
        record: FileRecord,
        owner: Symbol,
        bound_name: str,
        type_name: str,
        scope: BindingScope = BindingScope.INSTANCE,
    ) -> Binding:
        binding = make_binding(record.id, owner, bound_name, type_name, scope)
        self.ir.bindings.append(binding)
        return binding

    def resolve(self) -> object:
        return resolve_ir(self.ir)


# ---------------------------------------------------------------------------
# Acceptance criteria (spec section 13)
# ---------------------------------------------------------------------------


class AC1ExactResolutionTests(unittest.TestCase):
    """AC1: a known symbol reference resolves to the correct symbol."""

    def test_local_symbol_resolves_to_itself(self) -> None:
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        callee = m.symbol(f, "a.py:callee", "callee")
        edge = m.call(caller, "callee")
        m.resolve()
        self.assertEqual(edge.target_symbol_id, callee.id)
        self.assertIs(edge.resolution_status, ResolutionStatus.RESOLVED_EXACT)

    def test_bound_receiver_member_resolves_to_the_right_method(self) -> None:
        """The spec's own example: ``self.service.process()``.

        The receiver's type comes from a binding, so the resolver must reach the
        class through it rather than matching the member name globally.
        """
        m = _Model()
        f = m.file("svc.py")
        service = m.symbol(f, "svc.py:Service", "Service", SymbolType.CLASS)
        process = m.symbol(
            f, "svc.py:Service.process", "process", SymbolType.METHOD
        )
        init = m.symbol(f, "svc.py:Service.__init__", "__init__", SymbolType.METHOD)
        other = m.symbol(f, "svc.py:Other", "Other", SymbolType.CLASS)
        other_process = m.symbol(
            f, "svc.py:Other.process", "process", SymbolType.METHOD
        )
        # `self.service` is a Service, declared in the constructor.
        m.binding(f, init, "service", "Service", BindingScope.INSTANCE)
        edge = m.call(process, "self.service.process")
        m.resolve()
        self.assertEqual(edge.target_symbol_id, process.id)
        self.assertNotEqual(edge.target_symbol_id, other_process.id)
        self.assertEqual(service.id, service.id)  # the class itself is untouched

    def test_exact_resolution_implies_full_confidence(self) -> None:
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:callee", "callee")
        edge = m.call(caller, "callee")
        m.resolve()
        self.assertEqual(edge.confidence, 1.0)


class AC2NamespaceSeparationTests(unittest.TestCase):
    """AC2: same name in different modules stays distinct."""

    def test_import_decides_between_two_same_named_classes(self) -> None:
        """The importer's own class must win over the identical distant name."""
        m = _Model()
        a = m.file("a.py")
        b = m.file("b.py")
        local = m.symbol(a, "a.py:Payment", "Payment", SymbolType.CLASS)
        distant = m.symbol(b, "b.py:Payment", "Payment", SymbolType.CLASS)
        caller = m.symbol(a, "a.py:caller", "caller")
        edge = m.call(caller, "Payment")
        report = m.resolve()
        self.assertEqual(edge.target_symbol_id, local.id)
        self.assertNotEqual(edge.target_symbol_id, distant.id)
        self.assertIn(ResolutionRung.SAME_FILE_EXACT, report.counts)

    def test_two_classes_with_the_same_name_keep_distinct_member_edges(self) -> None:
        """The members of two same-named classes must not be interchangeable.

        This is the property that actually matters: if the namespace were not
        separated, an edge into ``A.Payment.save`` could land on ``B.Payment``'s
        method.
        """
        m = _Model()
        a = m.file("a.py")
        b = m.file("b.py")
        cls_a = m.symbol(a, "a.py:Payment", "Payment", SymbolType.CLASS)
        save_a = m.symbol(a, "a.py:Payment.save", "save", SymbolType.METHOD)
        cls_b = m.symbol(b, "b.py:Payment", "Payment", SymbolType.CLASS)
        save_b = m.symbol(b, "b.py:Payment.save", "save", SymbolType.METHOD)
        caller = m.symbol(a, "a.py:Payment.run", "run", SymbolType.METHOD)

        edge = m.call(caller, "self.save")
        m.resolve()
        self.assertEqual(edge.target_symbol_id, save_a.id)
        self.assertNotEqual(edge.target_symbol_id, save_b.id)
        self.assertNotEqual(cls_a.id, cls_b.id)


class AC3AmbiguousResolutionTests(unittest.TestCase):
    """AC3: ambiguity is marked, never assigned an arbitrary target."""

    def test_several_candidates_marks_ambiguous(self) -> None:
        m = _Model()
        a = m.file("a.py")
        b = m.file("b.py")
        c = m.file("c.py")
        m.symbol(a, "a.py:run", "run")
        m.symbol(b, "b.py:run", "run")
        caller = m.symbol(c, "c.py:caller", "caller")
        edge = m.call(caller, "run")
        m.resolve()
        self.assertIs(edge.resolution_status, ResolutionStatus.AMBIGUOUS)

    def test_ambiguous_records_the_candidates(self) -> None:
        m = _Model()
        a = m.file("a.py")
        b = m.file("b.py")
        c = m.file("c.py")
        s1 = m.symbol(a, "a.py:run", "run")
        s2 = m.symbol(b, "b.py:run", "run")
        caller = m.symbol(c, "c.py:caller", "caller")
        edge = m.call(caller, "run")
        m.resolve()
        self.assertEqual(
            set(edge.candidate_symbol_ids), {s1.id, s2.id}
        )

    def test_ambiguous_keeps_the_placeholder_target(self) -> None:
        """D28: an ambiguous edge must not inflate edge counts."""
        m = _Model()
        a = m.file("a.py")
        b = m.file("b.py")
        c = m.file("c.py")
        m.symbol(a, "a.py:run", "run")
        m.symbol(b, "b.py:run", "run")
        caller = m.symbol(c, "c.py:caller", "caller")
        edge = m.call(caller, "run")
        m.resolve()
        self.assertTrue(edge.target_symbol_id.startswith("unresolved:"))

    def test_candidate_list_is_bounded(self) -> None:
        """D26: the list is a diagnostic, not a payload."""
        m = _Model()
        caller_file = m.file("caller.py")
        for index in range(MAX_CANDIDATES * 3):
            f = m.file(f"m{index}.py")
            m.symbol(f, f"m{index}.py:run", "run")
        caller = m.symbol(caller_file, "caller.py:caller", "caller")
        edge = m.call(caller, "run")
        m.resolve()
        self.assertIs(edge.resolution_status, ResolutionStatus.AMBIGUOUS)
        self.assertLessEqual(len(edge.candidate_symbol_ids), MAX_CANDIDATES)

    def test_ambiguous_implies_zero_confidence(self) -> None:
        m = _Model()
        a = m.file("a.py")
        b = m.file("b.py")
        c = m.file("c.py")
        m.symbol(a, "a.py:run", "run")
        m.symbol(b, "b.py:run", "run")
        caller = m.symbol(c, "c.py:caller", "caller")
        edge = m.call(caller, "run")
        m.resolve()
        self.assertEqual(edge.confidence, 0.0)


class AC4UnknownTargetTests(unittest.TestCase):
    """AC4: an unknown symbol stays unresolved."""

    def test_no_match_stays_unresolved(self) -> None:
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        edge = m.call(caller, "never_defined_anywhere")
        m.resolve()
        self.assertIs(edge.resolution_status, ResolutionStatus.UNRESOLVED)

    def test_unresolved_keeps_target_name_for_a_later_pass(self) -> None:
        """D25: the raw text is what a future resolver works from."""
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        edge = m.call(caller, "ghost")
        m.resolve()
        self.assertEqual(edge.target_name, "ghost")

    def test_unresolved_keeps_zero_confidence(self) -> None:
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        edge = m.call(caller, "ghost")
        m.resolve()
        self.assertEqual(edge.confidence, 0.0)


class AC5NoHallucinatedRelationshipTests(unittest.TestCase):
    """AC5: the resolver never invents a target no syntax justified."""

    def test_every_resolved_target_exists_in_the_model(self) -> None:
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:real", "real")
        m.call(caller, "real")
        m.call(caller, "fake_one")
        m.call(caller, "fake_two.nested")
        m.resolve()
        known = {s.id for s in m.ir.symbols}
        for relationship in m.ir.relationships:
            if relationship.is_resolved:
                self.assertIn(relationship.target_symbol_id, known)

    def test_a_resolved_edge_is_never_self_invented(self) -> None:
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:other", "other")
        edge = m.call(caller, "other")
        m.resolve()
        self.assertEqual(edge.target_symbol_id != edge.source_symbol_id, True)

    def test_resolution_does_not_add_or_remove_edges(self) -> None:
        """Resolution upgrades edges; it never manufactures or drops one."""
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:real", "real")
        for name in ("real", "ghost", "other.missing"):
            m.call(caller, name)
        before = len(m.ir.relationships)
        m.resolve()
        self.assertEqual(len(m.ir.relationships), before)


class AC6ProvenanceTests(unittest.TestCase):
    """AC6: every resolved relationship still points back to its evidence."""

    def test_resolution_preserves_source_location(self) -> None:
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:real", "real")
        edge = m.call(caller, "real", line=42)
        before = edge.source_location.start_line
        m.resolve()
        self.assertEqual(edge.source_location.start_line, before)
        self.assertEqual(edge.source_location.start_line, 42)

    def test_resolution_preserves_relationship_id(self) -> None:
        """D25: the ID stays put, so a reindex does not orphan M3's index."""
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:real", "real")
        edge = m.call(caller, "real")
        before = edge.id
        m.resolve()
        self.assertEqual(edge.id, before)


# ---------------------------------------------------------------------------
# The ladder (D24)
# ---------------------------------------------------------------------------


class LadderTests(unittest.TestCase):
    def test_rungs_are_ordered_and_contiguous(self) -> None:
        orders = sorted(rung.order for rung in ResolutionRung)
        self.assertEqual(orders, list(range(1, len(ResolutionRung) + 1)))

    def test_only_ambiguity_and_failure_carry_zero_confidence(self) -> None:
        for rung in ResolutionRung:
            if rung.status is ResolutionStatus.RESOLVED_EXACT:
                self.assertEqual(rung.confidence, 1.0, rung.value)
            else:
                self.assertEqual(rung.confidence, 0.0, rung.value)

    def test_no_rung_claims_heuristic_yet(self) -> None:
        """No rung may fire RESOLVED_HEURISTIC.

        The reviewer's concern about an unfired enum member is answered by making
        it an assertion: if a future rung starts producing heuristics, it must be
        added deliberately along with evidence for it.
        """
        for rung in ResolutionRung:
            self.assertIsNot(rung.status, ResolutionStatus.RESOLVED_HEURISTIC)

    def test_same_file_beats_a_later_rung(self) -> None:
        """A local symbol wins over an identically-named distant one."""
        m = _Model()
        local_file = m.file("a.py")
        other_file = m.file("b.py")
        local = m.symbol(local_file, "a.py:run", "run")
        m.symbol(other_file, "b.py:run", "run")
        caller = m.symbol(local_file, "a.py:caller", "caller")
        edge = m.call(caller, "run")
        report = m.resolve()
        self.assertEqual(edge.target_symbol_id, local.id)
        self.assertIn(ResolutionRung.SAME_FILE_EXACT, report.counts)

    def test_receiver_member_fires_for_self_call(self) -> None:
        m = _Model()
        f = m.file("a.py")
        cls = m.symbol(f, "a.py:Thing", "Thing", SymbolType.CLASS)
        meth = m.symbol(f, "a.py:Thing.run", "run", SymbolType.METHOD)
        caller = m.symbol(f, "a.py:Thing.go", "go", SymbolType.METHOD)
        edge = m.call(caller, "self.run")
        report = m.resolve()
        self.assertEqual(edge.target_symbol_id, meth.id)
        self.assertIn(ResolutionRung.RECEIVER_CLASS_MEMBER, report.counts)

    def test_alias_binding_is_followed_one_hop(self) -> None:
        """``self.repo = repo`` with ``repo: Repo`` must still resolve.

        This is the constructor-injection shape. The extractor records the alias
        as ``repo: repo``, which carries no type, so the resolver has to follow it
        to the annotated parameter of the same name.
        """
        m = _Model()
        f = m.file("a.py")
        repo = m.symbol(f, "a.py:Repo", "Repo", SymbolType.CLASS)
        save = m.symbol(f, "a.py:Repo.save", "save", SymbolType.METHOD)
        service = m.symbol(f, "a.py:Service", "Service", SymbolType.CLASS)
        init = m.symbol(f, "a.py:Service.__init__", "__init__", SymbolType.METHOD)
        process = m.symbol(f, "a.py:Service.process", "process", SymbolType.METHOD)

        m.binding(f, init, "repo", "repo", BindingScope.INSTANCE)
        m.binding(f, init, "repo", "Repo", BindingScope.PARAMETER)

        edge = m.call(process, "self.repo.save")
        report = m.resolve()
        self.assertEqual(edge.target_symbol_id, save.id)
        self.assertIn(ResolutionRung.BOUND_TYPE_MEMBER, report.counts)

    def test_imported_symbol_fires_when_local_and_bound_fail(self) -> None:
        m = _Model()
        a = m.file("a.py")
        b = m.file("b.py")
        module_a = m.symbol(a, "a.py", "a.py", SymbolType.MODULE)
        m.symbol(b, "b.py:Widget", "Widget", SymbolType.CLASS)
        caller = m.symbol(a, "a.py:caller", "caller")
        m.ir.relationships.append(
            Relationship(
                id="rel_i",
                source_symbol_id=module_a.id,
                target_symbol_id="unresolved:import:b.py",
                relationship_type=RelationshipType.IMPORTS,
                resolution_status=ResolutionStatus.UNRESOLVED,
                confidence=0.0,
                source_location=span(),
                model_version=VERSION,
                target_name="b.py",
            )
        )
        edge = m.call(caller, "Widget")
        report = m.resolve()
        self.assertIs(edge.resolution_status, ResolutionStatus.RESOLVED_EXACT)

    def test_unfired_rungs_are_absent_from_the_report(self) -> None:
        """The report names only what actually happened."""
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:real", "real")
        m.call(caller, "real")
        report = m.resolve()
        self.assertNotIn(ResolutionRung.AMBIGUOUS_IN_MODEL, report.counts)
        self.assertNotIn(ResolutionRung.NONE, report.counts)


class ReportTests(unittest.TestCase):
    def test_report_totals_match_the_model(self) -> None:
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:real", "real")
        m.call(caller, "real")
        m.call(caller, "ghost")
        report = m.resolve()
        self.assertEqual(
            report.resolved + report.ambiguous + report.unresolved,
            len(m.ir.relationships),
        )

    def test_report_is_json_serialisable(self) -> None:
        import json

        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:real", "real")
        m.call(caller, "real")
        report = m.resolve()
        payload = json.dumps(report.to_dict())
        self.assertIn("S1_SAME_FILE_EXACT", payload)

    def test_report_counts_by_rung_are_sorted(self) -> None:
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:real", "real")
        m.call(caller, "real")
        report = m.resolve()
        keys = list(report.to_dict()["by_rung"].keys())
        self.assertEqual(keys, sorted(keys))


class DeterminismTests(unittest.TestCase):
    def test_resolution_is_deterministic(self) -> None:
        def once() -> list[tuple[str, str, list[str]]]:
            m = _Model()
            a = m.file("a.py")
            b = m.file("b.py")
            m.symbol(a, "a.py:run", "run")
            m.symbol(b, "b.py:run", "run")
            caller = m.symbol(a, "a.py:caller", "caller")
            m.symbol(a, "a.py:real", "real")
            m.call(caller, "run")
            m.call(caller, "real")
            m.resolve()
            return [
                (
                    r.target_symbol_id,
                    str(r.resolution_status),
                    list(r.candidate_symbol_ids),
                )
                for r in m.ir.relationships
            ]

        self.assertEqual(once(), once())

    def test_resolving_twice_changes_nothing(self) -> None:
        """Idempotence: a second pass over a resolved model is a no-op."""
        m = _Model()
        f = m.file("a.py")
        caller = m.symbol(f, "a.py:caller", "caller")
        m.symbol(f, "a.py:real", "real")
        edge = m.call(caller, "real")
        m.resolve()
        first = (edge.target_symbol_id, str(edge.resolution_status))
        m.resolve()
        self.assertEqual((edge.target_symbol_id, str(edge.resolution_status)), first)


class IndexTests(unittest.TestCase):
    def test_enclosing_class_is_derived_from_nesting(self) -> None:
        m = _Model()
        f = m.file("a.py")
        cls = m.symbol(f, "a.py:Outer", "Outer", SymbolType.CLASS)
        inner = m.symbol(f, "a.py:Outer.Inner", "Inner", SymbolType.CLASS)
        method = m.symbol(f, "a.py:Outer.Inner.run", "run", SymbolType.METHOD)
        top = m.symbol(f, "a.py:top", "top")
        module = m.symbol(f, "a.py", "a.py", SymbolType.MODULE)
        index = _ModelIndex.build(m.ir)
        self.assertEqual(index.owner_class.get(inner.id), "a.py:Outer")
        self.assertEqual(index.owner_class.get(method.id), "a.py:Outer.Inner")
        # A top-level function and a module symbol belong to no class. Returning
        # None here is what keeps ``self.m()`` from resolving to a free function
        # that merely shares a name.
        self.assertIsNone(index.owner_class.get(top.id))
        self.assertNotIn(module.id, index.owner_class)


if __name__ == "__main__":
    unittest.main()
