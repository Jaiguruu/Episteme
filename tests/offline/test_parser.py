"""Stage 3 — parser tests.

Covers section 10 AC1-AC6, plus the section 36 parser edge-case matrix.
"""

from __future__ import annotations

import unittest

from maat.core.enums import ParseStatus
from maat.core.locations import SourceSpan
from maat.offline.parser import GrammarUnavailableError, TreeSitterParser, load_grammar

VALID_PYTHON = b'''"""Docstring."""


class Service:
    def handle(self, payload):
        return payload
'''

PARTIAL_PYTHON = b'''"""Valid header."""

import os


class Service:
    def good(self):
        return 1

    def bad(self):
        return (
'''

WHOLLY_BROKEN = b"def broken(:\n    return 1\n\nclass Also(:\n    pass\n"


class ParserStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = TreeSitterParser()

    def test_ac1_valid_file_parses_ok(self) -> None:
        outcome = self.parser.parse(VALID_PYTHON, "python", "a.py")
        self.assertEqual(outcome.status, ParseStatus.OK)
        self.assertTrue(outcome.has_tree)
        self.assertEqual(outcome.error_node_count, 0)
        self.assertEqual(outcome.missing_node_count, 0)

    def test_ac2_syntax_error_does_not_raise(self) -> None:
        outcome = self.parser.parse(WHOLLY_BROKEN, "python", "a.py")
        self.assertIn(
            outcome.status, (ParseStatus.PARTIAL, ParseStatus.FAILED)
        )
        self.assertTrue(outcome.diagnostics)

    def test_ac3_empty_file_is_handled(self) -> None:
        outcome = self.parser.parse(b"", "python", "a.py")
        self.assertEqual(outcome.status, ParseStatus.EMPTY)
        self.assertFalse(outcome.has_tree)
        self.assertEqual(outcome.node_count, 0)

    def test_ac3_whitespace_only_file_is_empty(self) -> None:
        outcome = self.parser.parse(b"   \n\t\n", "python", "a.py")
        self.assertEqual(outcome.status, ParseStatus.EMPTY)

    def test_ac4_unknown_grammar_is_unsupported(self) -> None:
        outcome = self.parser.parse(VALID_PYTHON, "not_a_real_grammar", "a.x")
        self.assertEqual(outcome.status, ParseStatus.UNSUPPORTED)
        self.assertFalse(outcome.has_tree)
        self.assertTrue(outcome.diagnostics)
        self.assertEqual(outcome.diagnostics[0].code, "parse.grammar_unavailable")

    def test_ac5_locations_are_preserved(self) -> None:
        outcome = self.parser.parse(VALID_PYTHON, "python", "a.py")
        root = outcome.tree.root_node
        class_node = next(
            child for child in root.children if child.type == "class_definition"
        )
        span = SourceSpan.from_tree_sitter(class_node)
        self.assertEqual(span.start_line, 4)  # 1-based, matching editors
        self.assertEqual(span.start_col, 0)
        self.assertGreaterEqual(span.end_line, span.start_line)
        self.assertTrue(span.is_valid())

    def test_ac6_partial_parse_retains_valid_regions(self) -> None:
        outcome = self.parser.parse(PARTIAL_PYTHON, "python", "a.py")
        self.assertEqual(outcome.status, ParseStatus.PARTIAL)
        # The valid parts survive: the module, the import and the class header.
        text = outcome.source.decode()
        self.assertIn("class Service", text)
        self.assertGreater(outcome.node_count, 0)
        self.assertGreater(outcome.error_node_count, 0)

    def test_wholly_broken_file_is_failed(self) -> None:
        """No top-level statement parsed, so nothing could be extracted."""
        outcome = self.parser.parse(WHOLLY_BROKEN, "python", "a.py")
        self.assertEqual(outcome.status, ParseStatus.FAILED)
        codes = {d.code for d in outcome.diagnostics}
        self.assertIn("parse.no_clean_statements", codes)


class ParserDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = TreeSitterParser()

    def test_diagnostics_name_the_file_and_language(self) -> None:
        outcome = self.parser.parse(WHOLLY_BROKEN, "python", "src/a.py")
        for diagnostic in outcome.diagnostics:
            self.assertEqual(diagnostic.file_path, "src/a.py")
            self.assertEqual(diagnostic.language, "python")

    def test_diagnostics_carry_a_location(self) -> None:
        outcome = self.parser.parse(WHOLLY_BROKEN, "python", "a.py")
        located = [d for d in outcome.diagnostics if d.span is not None]
        self.assertTrue(located)
        for diagnostic in located:
            self.assertGreaterEqual(diagnostic.span.start_line, 1)

    def test_diagnostic_count_is_bounded(self) -> None:
        """A catastrophically broken file must not produce unbounded output."""
        parser = TreeSitterParser(max_diagnostics=10)
        source = b"\n".join(b"def broken%d(:" % i for i in range(500))
        outcome = parser.parse(source, "python", "a.py")
        self.assertLessEqual(len(outcome.diagnostics), 11)


class ParserEdgeCaseTests(unittest.TestCase):
    """Section 36 — parser edge cases."""

    def setUp(self) -> None:
        self.parser = TreeSitterParser()

    def test_deep_nesting_does_not_exhaust_recursion(self) -> None:
        """A recursive tree walk would raise RecursionError here.

        300 nested blocks produce a tree over 600 levels deep, comfortably past
        Python's default recursion limit.
        """
        lines = ["def deep(value):"]
        for level in range(300):
            lines.append("    " * (level + 1) + f"if value > {level}:")
        lines.append("    " * 301 + "return value")
        source = ("\n".join(lines) + "\n").encode("utf-8")

        outcome = self.parser.parse(source, "python", "deep.py")
        self.assertEqual(outcome.status, ParseStatus.OK)
        self.assertGreater(outcome.max_depth, 300)

    def test_unicode_identifiers_parse(self) -> None:
        source = (
            "π = 3.14\ncafé = 'x'\n\n\n"
            "class Données:\n    def calculer(self):\n        return π\n"
        ).encode("utf-8")
        outcome = self.parser.parse(source, "python", "u.py")
        self.assertEqual(outcome.status, ParseStatus.OK)

    def test_utf8_bom_does_not_break_parsing(self) -> None:
        outcome = self.parser.parse(
            b"\xef\xbb\xbf" + VALID_PYTHON, "python", "bom.py"
        )
        self.assertIn(outcome.status, (ParseStatus.OK, ParseStatus.PARTIAL))

    def test_crlf_line_endings_parse(self) -> None:
        outcome = self.parser.parse(
            VALID_PYTHON.replace(b"\n", b"\r\n"), "python", "crlf.py"
        )
        self.assertEqual(outcome.status, ParseStatus.OK)

    def test_missing_trailing_newline_parses(self) -> None:
        outcome = self.parser.parse(b"value = 1", "python", "a.py")
        self.assertEqual(outcome.status, ParseStatus.OK)

    def test_invalid_utf8_bytes_do_not_raise(self) -> None:
        outcome = self.parser.parse(b"value = 1\n# \xff\xfe\n", "python", "a.py")
        self.assertIsNotNone(outcome.status)

    def test_large_file_parses(self) -> None:
        lines = []
        for index in range(3000):
            lines.append(f"def f{index}(v):\n    return v + {index}\n")
        outcome = self.parser.parse("\n".join(lines).encode(), "python", "big.py")
        self.assertEqual(outcome.status, ParseStatus.OK)
        self.assertGreater(outcome.node_count, 10000)


class ParserBackendTests(unittest.TestCase):
    def test_every_registered_code_language_has_a_loadable_grammar(self) -> None:
        from maat.offline import languages

        failures = []
        for key, spec in languages.LANGUAGE_SPECS.items():
            if not spec.is_code:
                continue
            try:
                load_grammar(key)
            except GrammarUnavailableError as error:
                failures.append(f"{key}: {error}")
        self.assertEqual(failures, [])

    def test_grammar_objects_are_cached(self) -> None:
        self.assertIs(load_grammar("python"), load_grammar("python"))


if __name__ == "__main__":
    unittest.main()
