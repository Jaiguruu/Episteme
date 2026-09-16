"""Stage 4 — extractor tests.

Covers section 11 acceptance: PaymentService is extracted as a symbol, the
CheckoutService -> PaymentService and RefundService -> PaymentService calls are
identified, and no language-specific structure leaks into the canonical model.
"""

from __future__ import annotations

import unittest

from maat.core.enums import BindingScope, SymbolType
from maat.offline import languages
from maat.offline.extractors.base import looks_like_identifier, module_path_for
from maat.offline.extractors.query_extractor import QueryExtractor
from maat.offline.parser import TreeSitterParser

PYTHON_SAMPLE = b'''"""Payment domain service."""

from models.payment import Payment as Pay
from repositories.payment_repository import PaymentRepository


class PaymentService(Base, Mixin):
    """Validates and persists payments."""

    def process(self, payment: Payment) -> bool:
        if not self.validate(payment):
            return False
        self.repository.save(payment)
        return True

    def validate(self, payment: Payment) -> bool:
        return payment.amount > 0


def top_level(value):
    return value
'''


class ExtractorSymbolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = TreeSitterParser()
        self.extractor = QueryExtractor()

    def extract(self, source: bytes, path: str, language: str = "python"):
        outcome = self.parser.parse(source, language, path)
        return self.extractor.extract(outcome, path)

    def test_payment_service_is_extracted_as_a_symbol(self) -> None:
        facts = self.extract(PYTHON_SAMPLE, "services/payment_service.py")
        names = {fact.qualified_name for fact in facts.symbols}
        self.assertIn("services.payment_service:PaymentService", names)

    def test_module_symbol_is_always_present(self) -> None:
        facts = self.extract(PYTHON_SAMPLE, "services/payment_service.py")
        self.assertEqual(facts.symbols[0].symbol_type, SymbolType.MODULE)
        self.assertEqual(facts.symbols[0].qualified_name, "services.payment_service")

    def test_methods_are_distinguished_from_functions(self) -> None:
        facts = self.extract(PYTHON_SAMPLE, "services/payment_service.py")
        by_name = {fact.qualified_name: fact for fact in facts.symbols}
        self.assertEqual(
            by_name["services.payment_service:PaymentService.process"].symbol_type,
            SymbolType.METHOD,
        )
        self.assertEqual(
            by_name["services.payment_service:top_level"].symbol_type,
            SymbolType.FUNCTION,
        )

    def test_nesting_produces_parent_links(self) -> None:
        facts = self.extract(PYTHON_SAMPLE, "services/payment_service.py")
        by_name = {fact.qualified_name: fact for fact in facts.symbols}
        process = by_name["services.payment_service:PaymentService.process"]
        self.assertEqual(
            process.parent_qualified_name, "services.payment_service:PaymentService"
        )
        self.assertEqual(
            by_name["services.payment_service:PaymentService"].parent_qualified_name,
            "services.payment_service",
        )

    def test_docstring_is_attached(self) -> None:
        facts = self.extract(PYTHON_SAMPLE, "services/payment_service.py")
        by_name = {fact.qualified_name: fact for fact in facts.symbols}
        self.assertIn(
            "Validates and persists",
            by_name["services.payment_service:PaymentService"].documentation or "",
        )

    def test_signature_skips_decorators(self) -> None:
        source = (
            b"class A:\n"
            b"    @staticmethod\n"
            b"    def helper(value):\n"
            b"        return value\n"
        )
        facts = self.extract(source, "a.py")
        by_name = {fact.qualified_name: fact for fact in facts.symbols}
        signature = by_name["a:A.helper"].signature or ""
        self.assertIn("def helper", signature)
        self.assertNotIn("@staticmethod", signature)


class ExtractorRelationshipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = TreeSitterParser()
        self.extractor = QueryExtractor()

    def test_call_candidates_are_identified(self) -> None:
        """Section 11: the fixture's two call edges must be visible as facts."""
        checkout = b'''"""Checkout."""
from services.payment_service import PaymentService


class CheckoutService:
    def __init__(self):
        self.payment_service = PaymentService()

    def checkout(self, cart):
        return self.payment_service.process(cart)
'''
        refund = b'''"""Refunds."""
from services.payment_service import PaymentService


class RefundService:
    def __init__(self):
        self.payment_service = PaymentService()

    def refund(self, payment):
        return self.payment_service.process(payment)
'''
        checkout_facts = self.extractor.extract(
            self.parser.parse(checkout, "python", "services/checkout_service.py"),
            "services/checkout_service.py",
        )
        refund_facts = self.extractor.extract(
            self.parser.parse(refund, "python", "services/refund_service.py"),
            "services/refund_service.py",
        )

        checkout_targets = {call.target_name for call in checkout_facts.calls}
        refund_targets = {call.target_name for call in refund_facts.calls}

        self.assertIn("self.payment_service.process", checkout_targets)
        self.assertIn("self.payment_service.process", refund_targets)
        # Both call sites are attributed to the method that contains them.
        self.assertIn(
            "services.checkout_service:CheckoutService.checkout",
            {call.enclosing_qualified_name for call in checkout_facts.calls},
        )
        self.assertIn(
            "services.refund_service:RefundService.refund",
            {call.enclosing_qualified_name for call in refund_facts.calls},
        )

    def test_imports_are_grouped_per_statement(self) -> None:
        facts = QueryExtractor().extract(
            TreeSitterParser().parse(PYTHON_SAMPLE, "python", "services/payment_service.py"),
            "services/payment_service.py",
        )
        imports = {fact.module: fact for fact in facts.imports}
        self.assertIn("models.payment", imports)
        self.assertEqual(imports["models.payment"].names, ["Payment"])
        self.assertEqual(imports["models.payment"].alias, "Pay")
        self.assertIn("repositories.payment_repository", imports)

    def test_bare_import_with_alias_promotes_module(self) -> None:
        """``import os as o`` captures a name and alias but no module node."""
        source = b"import ujson as json\n"
        facts = QueryExtractor().extract(
            TreeSitterParser().parse(source, "python", "a.py"), "a.py"
        )
        self.assertEqual(len(facts.imports), 1)
        self.assertEqual(facts.imports[0].module, "ujson")
        self.assertEqual(facts.imports[0].alias, "json")

    def test_multiple_base_classes_are_all_captured(self) -> None:
        """A single capture binds a list; taking only the first would drop these."""
        source = b"class A(Base, Mixin, Serializable):\n    pass\n"
        facts = QueryExtractor().extract(
            TreeSitterParser().parse(source, "python", "a.py"), "a.py"
        )
        bases = {fact.base_name for fact in facts.inherits}
        self.assertEqual(bases, {"Base", "Mixin", "Serializable"})

    def test_expression_receivers_are_dropped(self) -> None:
        """``foo().bar`` is syntax, not a semantic receiver."""
        source = b"def f():\n    return obj.first().second()\n"
        facts = QueryExtractor().extract(
            TreeSitterParser().parse(source, "python", "a.py"), "a.py"
        )
        for call in facts.calls:
            if call.receiver is not None:
                self.assertTrue(looks_like_identifier(call.receiver), call.receiver)


class ExtractorLanguageCoverageTests(unittest.TestCase):
    """Every language with a query file must actually produce facts."""

    def test_all_extractable_languages_yield_symbols_and_calls(self) -> None:
        from tools.dump_trees import SAMPLES

        parser = TreeSitterParser()
        extractor = QueryExtractor()
        failures: list[str] = []

        for language in sorted(languages.extractable_languages()):
            sample = SAMPLES.get(language)
            if sample is None:
                failures.append(f"{language}: no sample in tools/dump_trees.py")
                continue
            path = f"src/sample.{language}"
            outcome = parser.parse(sample.encode("utf-8"), language, path)
            facts = extractor.extract(outcome, path)
            counts = facts.counts()
            if counts["symbols"] < 2:
                failures.append(f"{language}: only {counts['symbols']} symbols")
            if counts["imports"] == 0:
                failures.append(f"{language}: no imports extracted")

        self.assertEqual(failures, [])

    def test_language_without_query_reports_a_diagnostic(self) -> None:
        """Honest degradation: parsed, but no symbols, and it says so."""
        parser = TreeSitterParser()
        extractor = QueryExtractor()
        outcome = parser.parse(b"def f(): pass\n", "elixir", "a.ex")
        facts = extractor.extract(outcome, "a.ex")
        codes = {diagnostic.code for diagnostic in facts.diagnostics}
        self.assertIn("extract.no_query", codes)
        # Only the module symbol, no invented declarations.
        self.assertEqual(len(facts.symbols), 1)


class ModuleNamingTests(unittest.TestCase):
    def test_module_path_derivation(self) -> None:
        cases = {
            "services/payment_service.py": "services.payment_service",
            "pkg/__init__.py": "pkg",
            "src/api/index.ts": "src.api",
            "rust/src/mod.rs": "rust.src",
            "a.py": "a",
        }
        for path, expected in cases.items():
            self.assertEqual(module_path_for(path, "python"), expected, path)


class NoLeakageTests(unittest.TestCase):
    """Section 11 AC3: no language-specific structure may reach the model."""

    def test_facts_expose_no_tree_sitter_objects(self) -> None:
        parser = TreeSitterParser()
        facts = QueryExtractor().extract(
            parser.parse(PYTHON_SAMPLE, "python", "a.py"), "a.py"
        )
        payload = facts.to_dict()
        text = repr(payload)
        for forbidden in ("Node", "tree_sitter", "start_byte", "end_byte", "type="):
            self.assertNotIn(forbidden, text, forbidden)

    def test_fact_vocabulary_is_language_neutral(self) -> None:
        """Every fact field is a plain Python type, not a grammar node."""
        parser = TreeSitterParser()
        facts = QueryExtractor().extract(
            parser.parse(PYTHON_SAMPLE, "python", "a.py"), "a.py"
        )
        for symbol in facts.symbols:
            self.assertIsInstance(symbol.name, str)
            self.assertIsInstance(symbol.qualified_name, str)
            self.assertIsInstance(symbol.symbol_type, SymbolType)
            self.assertFalse(hasattr(symbol, "node"))


if __name__ == "__main__":
    unittest.main()
