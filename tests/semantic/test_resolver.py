"""The resolver in ``maat/semantic/resolver.py``.

Covers section 13 (symbol and relationship resolution, AC1-AC6) and decision D24. The
resolver is a pure function of the model: these tests build models in memory, so no
fixture repository and no disk are involved.

Each test class is named after the behaviour it pins, with the acceptance criterion it
covers in its docstring -- the convention the rest of the suite follows.
"""

from __future__ import annotations

import json
import unittest

from maat.core.contracts import Binding, FileRecord, Relationship, SemanticIR, Symbol
from maat.core.enums import (
    BindingScope,
    ParseStatus,
    RelationshipType,
    ResolutionStatus,
    SymbolType,
)
from maat.core.locations import SourceSpan
from maat.semantic import ResolutionRung, resolve_ir
from maat.semantic.resolver import MAX_CANDIDATES, _ModelIndex

VERSION = "mv_test"


def span(line: int = 1, col: int = 1) -> SourceSpan:
    return SourceSpan.point(line, col)


def _simple_name(qualified_name: str) -> str:
    """The trailing name of a qualified name, ignoring the module prefix."""
    local = qualified_name.partition(":")[2] or qualified_name
    return local.rsplit(".", 1)[-1]


def make_file(path: str) -> FileRecord:
    return FileRecord(
        path=path,
        language="python",
        content_hash=f"hash_{path}",
        size=0,
        parse_status=ParseStatus.OK,
        parse_error=None,
        model_version=VERSION,
        id=f"file_{path}",
    )


def make_symbol(
    file_id: str,
    qualified_name: str,
    name: str | None = None,
    symbol_type: SymbolType = SymbolType.FUNCTION,
) -> Symbol:
    return Symbol(
        id="sym_" + qualified_name.replace(".", "_").replace(":", "_"),
        file_id=file_id,
        name=name or _simple_name(qualified_name),
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        signature=None,
        location=span(),
        documentation=None,
        content_hash="hash",
        model_version=VERSION,
    )


def make_call(source: Symbol, target_name: str, line: int = 1) -> Relationship:
    """An edge as Stage 5 emits it: unresolved, with the raw text retained."""
    return Relationship(
        id=f"rel_{source.id}_{target_name}_{line}",
        source_symbol_id=source.id,
        target_symbol_id=f"unresolved:call:{target_name}",
        relationship_type=RelationshipType.CALLS,
        resolution_status=ResolutionStatus.UNRESOLVED,
        confidence=0.0,
        source_location=span(line),
        model_version=VERSION,
        target_name=target_name,
    )


def make_binding(
    file_id: str,
    owner: Symbol | None,
    bound_name: str,
    type_name: str,
    scope: BindingScope = BindingScope.INSTANCE,
) -> Binding:
    return Binding(
        id=f"bind_{bound_name}_{type_name}_{scope.value}",
        file_id=file_id,
        bound_name=bound_name,
        type_name=type_name,
        scope=scope,
        location=span(),
        model_version=VERSION,
        enclosing_symbol_id=owner.id if owner is not None else None,
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
        symbol = make_symbol(record.id, qualified_name, name, symbol_type)
        self.ir.symbols.append(symbol)
        return symbol

    def call(self, source: Symbol, target: str, line: int = 1) -> Relationship:
        relationship = make_call(source, target, line)
        self.ir.relationships.append(relationship)
        return relationship

    def binding(
        self,
        record: FileRecord,
        owner: Symbol | None,
        bound_name: str,
        type_name: str,
        scope: BindingScope = BindingScope.INSTANCE,
    ) -> Binding:
        binding = make_binding(record.id, owner, bound_name, type_name, scope)
        self.ir.bindings.append(binding)
        return binding

    def resolve(self):
        return resolve_ir(self.ir)


class LocalResolutionTests(unittest.TestCase):
    """Section 13 AC1 -- a known reference resolves to the correct symbol."""

    def test_a_local_symbol_resolves_to_itself(self) -> None:
        model = _Model()
        record = model.file("a.py")
        callee = model.symbol(record, "a.py:run")
        caller = model.symbol(record, "a.py:main")
        edge = model.call(caller, "run")

        model.resolve()

        self.assertEqual(edge.target_symbol_id, callee.id)
        self.assertIs(edge.resolution_status, ResolutionStatus.RESOLVED_EXACT)

    def test_a_bound_receiver_member_resolves_to_the_right_method(self) -> None:
        """``self.svc.process`` must land on Service.process, not Other.process."""
        model = _Model()
        record = model.file("a.py")
        service = model.symbol(record, "a.py:Service", "Service", SymbolType.CLASS)
        process = model.symbol(
            record, "a.py:Service.process", "process", SymbolType.METHOD
        )
        other = model.symbol(record, "a.py:Other", "Other", SymbolType.CLASS)
        other_process = model.symbol(
            record, "a.py:Other.process", "process", SymbolType.METHOD
        )
        caller = model.symbol(record, "a.py:Caller.run", "run", SymbolType.METHOD)
        model.binding(record, caller, "svc", "Service", BindingScope.PARAMETER)
        edge = model.call(caller, "self.svc.process")

        model.resolve()

        self.assertEqual(edge.target_symbol_id, process.id)
        self.assertNotEqual(edge.target_symbol_id, other_process.id)
        self.assertNotEqual(edge.target_symbol_id, other.id)
        self.assertNotEqual(edge.target_symbol_id, service.id)

    def test_exact_resolution_implies_full_confidence(self) -> None:
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        caller = model.symbol(record, "a.py:main")
        edge = model.call(caller, "run")

        model.resolve()

        self.assertEqual(edge.confidence, 1.0)


class NamespaceSeparationTests(unittest.TestCase):
    """Section 13 AC2 -- same name in different modules stays distinct."""

    def test_a_local_name_wins_over_a_distant_one(self) -> None:
        model = _Model()
        local_file = model.file("a.py")
        distant_file = model.file("b.py")
        local = model.symbol(local_file, "a.py:Payment", "Payment", SymbolType.CLASS)
        distant = model.symbol(
            distant_file, "b.py:Payment", "Payment", SymbolType.CLASS
        )
        caller = model.symbol(local_file, "a.py:main")
        edge = model.call(caller, "Payment")

        report = model.resolve()

        self.assertEqual(edge.target_symbol_id, local.id)
        self.assertNotEqual(edge.target_symbol_id, distant.id)
        self.assertIn(ResolutionRung.SAME_FILE_EXACT, report.counts)

    def test_two_same_named_classes_keep_distinct_member_edges(self) -> None:
        """``self.save`` resolves against the caller's own class, not the namesake."""
        model = _Model()
        alpha_file = model.file("a.py")
        beta_file = model.file("b.py")
        alpha = model.symbol(alpha_file, "a.py:Alpha", "Alpha", SymbolType.CLASS)
        save_alpha = model.symbol(
            alpha_file, "a.py:Alpha.save", "save", SymbolType.METHOD
        )
        beta = model.symbol(beta_file, "b.py:Beta", "Beta", SymbolType.CLASS)
        save_beta = model.symbol(beta_file, "b.py:Beta.save", "save", SymbolType.METHOD)
        runner = model.symbol(
            alpha_file, "a.py:Alpha.run", "run", SymbolType.METHOD
        )
        edge = model.call(runner, "self.save")

        model.resolve()

        self.assertEqual(edge.target_symbol_id, save_alpha.id)
        self.assertNotEqual(edge.target_symbol_id, save_beta.id)
        self.assertNotEqual(alpha.id, beta.id)


class AmbiguousResolutionTests(unittest.TestCase):
    """Section 13 AC3 -- ambiguity is marked, never assigned an arbitrary target."""

    def _ambiguous(self, count: int = 2) -> tuple[_Model, Relationship]:
        model = _Model()
        for index in range(count):
            record = model.file(f"mod{index}.py")
            model.symbol(record, f"mod{index}.py:shared", "shared")
        caller_file = model.file("caller.py")
        caller = model.symbol(caller_file, "caller.py:main")
        return model, model.call(caller, "shared")

    def test_several_candidates_are_marked_ambiguous(self) -> None:
        model, edge = self._ambiguous()
        model.resolve()
        self.assertIs(edge.resolution_status, ResolutionStatus.AMBIGUOUS)

    def test_the_candidates_are_recorded(self) -> None:
        model, edge = self._ambiguous()
        model.resolve()
        self.assertEqual(len(edge.candidate_symbol_ids), 2)

    def test_an_ambiguous_edge_keeps_its_placeholder_target(self) -> None:
        """D28: edge counts must not inflate, so the placeholder survives."""
        model, edge = self._ambiguous()
        before = edge.target_symbol_id
        model.resolve()
        self.assertEqual(edge.target_symbol_id, before)
        self.assertTrue(edge.target_symbol_id.startswith("unresolved:"))

    def test_the_candidate_list_is_bounded(self) -> None:
        """A common name can match hundreds of symbols; the list is capped (D26)."""
        model, edge = self._ambiguous(MAX_CANDIDATES * 3)
        model.resolve()
        self.assertIs(edge.resolution_status, ResolutionStatus.AMBIGUOUS)
        self.assertLessEqual(len(edge.candidate_symbol_ids), MAX_CANDIDATES)

    def test_ambiguous_implies_zero_confidence(self) -> None:
        model, edge = self._ambiguous()
        model.resolve()
        self.assertEqual(edge.confidence, 0.0)


class UnknownTargetTests(unittest.TestCase):
    """Section 13 AC4 -- an unknown symbol is represented as unresolved."""

    def _unknown(self) -> tuple[_Model, Relationship]:
        model = _Model()
        record = model.file("a.py")
        caller = model.symbol(record, "a.py:main")
        return model, model.call(caller, "ghost")

    def test_an_unknown_name_stays_unresolved(self) -> None:
        model, edge = self._unknown()
        model.resolve()
        self.assertIs(edge.resolution_status, ResolutionStatus.UNRESOLVED)

    def test_the_raw_target_name_is_kept_for_a_later_pass(self) -> None:
        model, edge = self._unknown()
        model.resolve()
        self.assertEqual(edge.target_name, "ghost")

    def test_unresolved_implies_zero_confidence(self) -> None:
        model, edge = self._unknown()
        model.resolve()
        self.assertEqual(edge.confidence, 0.0)

    def test_a_call_with_no_source_symbol_is_left_alone(self) -> None:
        """A dangling source must not crash the run; the edge is simply recorded."""
        model = _Model()
        record = model.file("a.py")
        caller = model.symbol(record, "a.py:main")
        edge = model.call(caller, "run")
        edge.source_symbol_id = "sym_does_not_exist"

        report = model.resolve()

        self.assertIs(edge.resolution_status, ResolutionStatus.UNRESOLVED)
        self.assertEqual(report.counts[ResolutionRung.NONE], 1)

    def test_a_call_with_no_target_name_is_left_alone(self) -> None:
        model = _Model()
        record = model.file("a.py")
        caller = model.symbol(record, "a.py:main")
        edge = model.call(caller, "run")
        edge.target_name = None

        model.resolve()

        self.assertIs(edge.resolution_status, ResolutionStatus.UNRESOLVED)


class NoHallucinatedEdgeTests(unittest.TestCase):
    """Section 13 AC5 -- the resolver never invents a target."""

    def _resolved_model(self) -> _Model:
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        service = model.symbol(record, "a.py:Service", "Service", SymbolType.CLASS)
        model.symbol(record, "a.py:Service.process", "process", SymbolType.METHOD)
        caller = model.symbol(record, "a.py:Caller.run", "run", SymbolType.METHOD)
        model.binding(record, caller, "svc", "Service", BindingScope.PARAMETER)
        model.call(caller, "self.svc.process")
        model.call(caller, "ghost")
        model.resolve()
        return model

    def test_every_resolved_target_exists_in_the_model(self) -> None:
        model = self._resolved_model()
        known = {symbol.id for symbol in model.ir.symbols}
        for edge in model.ir.relationships:
            if edge.resolution_status is ResolutionStatus.RESOLVED_EXACT:
                with self.subTest(edge=edge.id):
                    self.assertIn(edge.target_symbol_id, known)

    def test_a_resolved_edge_is_never_self_invented(self) -> None:
        model = self._resolved_model()
        for edge in model.ir.relationships:
            with self.subTest(edge=edge.id):
                self.assertNotEqual(
                    edge.target_symbol_id, edge.source_symbol_id
                )

    def test_resolution_does_not_add_or_remove_edges(self) -> None:
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        caller = model.symbol(record, "a.py:main")
        model.call(caller, "run")
        model.call(caller, "ghost")
        before = len(model.ir.relationships)

        model.resolve()

        self.assertEqual(len(model.ir.relationships), before)


class ProvenanceTests(unittest.TestCase):
    """Section 13 AC6 -- every resolved relationship points back to its source."""

    def test_resolution_preserves_the_source_location(self) -> None:
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        caller = model.symbol(record, "a.py:main")
        edge = model.call(caller, "run", line=42)

        model.resolve()

        self.assertEqual(edge.source_location.start_line, 42)

    def test_resolution_preserves_the_relationship_id(self) -> None:
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        caller = model.symbol(record, "a.py:main")
        edge = model.call(caller, "run")
        before = edge.id

        model.resolve()

        self.assertEqual(edge.id, before)


class LadderFiringTests(unittest.TestCase):
    """Section 13, D24 -- the right rung fires, and only that rung is recorded."""

    def test_the_same_file_rung_fires_for_a_bare_local_name(self) -> None:
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        caller = model.symbol(record, "a.py:main")
        model.call(caller, "run")

        report = model.resolve()

        self.assertIn(ResolutionRung.SAME_FILE_EXACT, report.counts)

    def test_the_receiver_rung_fires_for_a_self_call(self) -> None:
        model = _Model()
        record = model.file("a.py")
        thing = model.symbol(record, "a.py:Thing", "Thing", SymbolType.CLASS)
        run = model.symbol(record, "a.py:Thing.run", "run", SymbolType.METHOD)
        caller = model.symbol(record, "a.py:Thing.go", "go", SymbolType.METHOD)
        edge = model.call(caller, "self.run")

        report = model.resolve()

        self.assertEqual(edge.target_symbol_id, run.id)
        self.assertIn(ResolutionRung.RECEIVER_CLASS_MEMBER, report.counts)
        self.assertNotEqual(edge.target_symbol_id, thing.id)

    def test_the_bound_type_rung_fires_through_a_one_hop_alias(self) -> None:
        """``self.repository = repo`` where ``repo`` carries the annotation."""
        model = _Model()
        record = model.file("a.py")
        repo_class = model.symbol(record, "a.py:Repo", "Repo", SymbolType.CLASS)
        save = model.symbol(record, "a.py:Repo.save", "save", SymbolType.METHOD)
        init = model.symbol(record, "a.py:Svc.__init__", "__init__", SymbolType.METHOD)
        model.binding(record, init, "repository", "repo", BindingScope.INSTANCE)
        model.binding(record, init, "repo", "Repo", BindingScope.PARAMETER)
        edge = model.call(init, "self.repository.save")

        report = model.resolve()

        self.assertEqual(edge.target_symbol_id, save.id)
        self.assertIn(ResolutionRung.BOUND_TYPE_MEMBER, report.counts)
        self.assertNotEqual(edge.target_symbol_id, repo_class.id)

    def test_the_imported_rung_fires_when_local_and_bound_fail(self) -> None:
        model = _Model()
        source_file = model.file("a.py")
        target_file = model.file("b.py")
        # Every file has a module symbol -- that is how an import names a file.
        model.symbol(target_file, "b.py", "b", SymbolType.MODULE)
        widget = model.symbol(target_file, "b.py:Widget", "Widget", SymbolType.CLASS)
        module = model.symbol(source_file, "a.py", "a", SymbolType.MODULE)
        caller = model.symbol(source_file, "a.py:main")
        model.ir.relationships.append(
            Relationship(
                id="rel_import",
                source_symbol_id=module.id,
                target_symbol_id="unresolved:module:b.py",
                relationship_type=RelationshipType.IMPORTS,
                resolution_status=ResolutionStatus.UNRESOLVED,
                confidence=0.0,
                source_location=span(),
                model_version=VERSION,
                target_name="b.py",
            )
        )
        edge = model.call(caller, "Widget")

        report = model.resolve()

        self.assertEqual(edge.target_symbol_id, widget.id)
        self.assertIn(ResolutionRung.IMPORTED_MODULE_SYMBOL, report.counts)

    def test_unfired_rungs_are_absent_from_the_report(self) -> None:
        """A rung that never answered must not appear with a count of zero."""
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        caller = model.symbol(record, "a.py:main")
        model.call(caller, "run")

        report = model.resolve()

        self.assertNotIn(ResolutionRung.AMBIGUOUS_IN_MODEL, report.counts)
        self.assertNotIn(ResolutionRung.NONE, report.counts)

    def test_a_structural_edge_is_not_touched(self) -> None:
        """``CONTAINS`` is already exact from Stage 5 and carries no rung."""
        model = _Model()
        record = model.file("a.py")
        module = model.symbol(record, "a.py", "a", SymbolType.MODULE)
        thing = model.symbol(record, "a.py:Thing", "Thing", SymbolType.CLASS)
        edge = Relationship(
            id="rel_contains",
            source_symbol_id=module.id,
            target_symbol_id=thing.id,
            relationship_type=RelationshipType.CONTAINS,
            resolution_status=ResolutionStatus.RESOLVED_EXACT,
            confidence=1.0,
            source_location=span(),
            model_version=VERSION,
            target_name=None,
        )
        model.ir.relationships.append(edge)

        report = model.resolve()

        self.assertEqual(edge.target_symbol_id, thing.id)
        self.assertIs(edge.resolution_status, ResolutionStatus.RESOLVED_EXACT)
        self.assertEqual(report.counts, {})


class AliasResolutionTests(unittest.TestCase):
    """Section 13, D36 -- an unannotated alias is followed, but only one hop."""

    def test_a_declared_type_beats_a_self_named_alias(self) -> None:
        """``self.repository = repository`` records no type, so the annotation wins.

        Both bindings share one name in one scope. Taking whichever the extractor
        emitted first would be a coin flip, which is why the declared type is
        preferred explicitly.
        """
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:Repo", "Repo", SymbolType.CLASS)
        save = model.symbol(record, "a.py:Repo.save", "save", SymbolType.METHOD)
        init = model.symbol(record, "a.py:Svc.__init__", "__init__", SymbolType.METHOD)
        model.binding(record, init, "repo", "repo", BindingScope.INSTANCE)
        model.binding(record, init, "repo", "Repo", BindingScope.PARAMETER)
        edge = model.call(init, "self.repo.save")

        model.resolve()

        self.assertEqual(edge.target_symbol_id, save.id)

    def test_a_self_referential_alias_terminates_and_stays_unresolved(self) -> None:
        """The alias walk is bounded, so a cycle cannot spin."""
        model = _Model()
        record = model.file("a.py")
        init = model.symbol(record, "a.py:Svc.__init__", "__init__", SymbolType.METHOD)
        model.binding(record, init, "loop", "loop", BindingScope.INSTANCE)
        edge = model.call(init, "self.loop.save")

        model.resolve()

        self.assertIs(edge.resolution_status, ResolutionStatus.UNRESOLVED)


class ReportTests(unittest.TestCase):
    """Section 13 -- the report describes the run and is machine-readable."""

    def _model(self) -> _Model:
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        caller = model.symbol(record, "a.py:main")
        model.call(caller, "run")
        model.call(caller, "ghost")
        return model

    def test_totals_match_the_model(self) -> None:
        model = self._model()
        report = model.resolve()
        self.assertEqual(
            report.resolved + report.ambiguous + report.unresolved,
            len(model.ir.relationships),
        )

    def test_the_report_is_json_serialisable(self) -> None:
        model = self._model()
        report = model.resolve()
        payload = json.dumps(report.to_dict())
        self.assertIn(ResolutionRung.SAME_FILE_EXACT.value, payload)

    def test_by_rung_is_in_ladder_order(self) -> None:
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        other_file = model.file("b.py")
        model.symbol(other_file, "b.py:helper")
        caller = model.symbol(record, "a.py:main")
        model.call(caller, "run")
        model.call(caller, "helper")

        report = model.resolve()
        keys = list(report.to_dict()["by_rung"].keys())

        self.assertEqual(keys, sorted(keys))

    def test_retargeted_counts_only_edges_whose_target_moved(self) -> None:
        model = self._model()
        report = model.resolve()
        self.assertEqual(report.retargeted, 1)


class ResolutionDeterminismTests(unittest.TestCase):
    """Section 13 and section 9 AC2 -- resolution is deterministic and idempotent."""

    def _build(self) -> _Model:
        model = _Model()
        record = model.file("a.py")
        model.symbol(record, "a.py:run")
        service = model.symbol(record, "a.py:Service", "Service", SymbolType.CLASS)
        model.symbol(record, "a.py:Service.process", "process", SymbolType.METHOD)
        caller = model.symbol(record, "a.py:Caller.run", "run", SymbolType.METHOD)
        model.binding(record, caller, "svc", "Service", BindingScope.PARAMETER)
        model.call(caller, "self.svc.process")
        model.call(caller, "ghost")
        return model

    def test_two_passes_produce_the_same_result(self) -> None:
        def once():
            model = self._build()
            model.resolve()
            return [
                (r.target_symbol_id, r.resolution_status.value, tuple(r.candidate_symbol_ids))
                for r in model.ir.relationships
            ]

        self.assertEqual(once(), once())

    def test_resolving_twice_changes_nothing(self) -> None:
        model = self._build()
        model.resolve()
        first = [(r.target_symbol_id, r.resolution_status.value) for r in model.ir.relationships]

        model.ir and resolve_ir(model.ir)
        second = [(r.target_symbol_id, r.resolution_status.value) for r in model.ir.relationships]

        self.assertEqual(first, second)


class ModelIndexTests(unittest.TestCase):
    """The lookup structures, including the nesting convention they rely on."""

    def test_the_enclosing_class_is_derived_from_nesting(self) -> None:
        model = _Model()
        record = model.file("a.py")
        outer = model.symbol(record, "a.py:Outer", "Outer", SymbolType.CLASS)
        inner = model.symbol(record, "a.py:Outer.Inner", "Inner", SymbolType.CLASS)
        method = model.symbol(
            record, "a.py:Outer.Inner.method", "method", SymbolType.METHOD
        )

        index = _ModelIndex.build(model.ir)

        self.assertEqual(index.owner_class.get(method.id), "a.py:Outer.Inner")
        self.assertEqual(index.owner_class.get(inner.id), "a.py:Outer")
        self.assertNotIn(outer.id, index.owner_class)

    def test_a_module_symbol_has_no_enclosing_class(self) -> None:
        model = _Model()
        record = model.file("a.py")
        module = model.symbol(record, "a.py", "a", SymbolType.MODULE)
        top = model.symbol(record, "a.py:top")

        index = _ModelIndex.build(model.ir)

        self.assertNotIn(module.id, index.owner_class)
        self.assertNotIn(top.id, index.owner_class)

    def test_qualified_names_are_indexed(self) -> None:
        model = _Model()
        record = model.file("a.py")
        thing = model.symbol(record, "a.py:Thing", "Thing", SymbolType.CLASS)

        index = _ModelIndex.build(model.ir)

        self.assertEqual(index.by_qualified_name["a.py:Thing"], [thing])
        self.assertIn("a.py:Thing", index.names)


if __name__ == "__main__":
    unittest.main()
