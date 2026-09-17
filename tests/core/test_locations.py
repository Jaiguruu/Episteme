"""``SourceSpan`` in ``maat/core/locations.py``.

The conventions under test are the ones every off-by-one bug in a code-intelligence
tool comes from: line 1-based, column 0-based, end exclusive. Getting them wrong is
silent, so they are pinned here rather than inferred from usage.
"""

from __future__ import annotations

import unittest

from maat.core.locations import SourceSpan


class _FakeNode:
    """The only two attributes ``SourceSpan.from_tree_sitter`` reads."""

    def __init__(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        self.start_point = start
        self.end_point = end


class ConstructionTests(unittest.TestCase):
    def test_from_tree_sitter_shifts_rows_to_one_based(self) -> None:
        """tree-sitter reports rows 0-based; every editor reports lines 1-based."""
        span = SourceSpan.from_tree_sitter(_FakeNode((0, 0), (3, 8)))
        self.assertEqual(
            (span.start_line, span.start_col, span.end_line, span.end_col),
            (1, 0, 4, 8),
        )

    def test_from_tree_sitter_keeps_columns_zero_based(self) -> None:
        span = SourceSpan.from_tree_sitter(_FakeNode((9, 4), (9, 12)))
        self.assertEqual(span.start_col, 4)
        self.assertEqual(span.end_col, 12)

    def test_point_is_zero_width(self) -> None:
        span = SourceSpan.point(3, 4)
        self.assertTrue(span.is_zero_width())
        self.assertEqual(span.line_count, 1)
        self.assertEqual((span.start_line, span.start_col), (3, 4))

    def test_whole_file_spans_every_line(self) -> None:
        span = SourceSpan.whole_file(10)
        self.assertEqual(span.start_line, 1)
        self.assertEqual(span.end_line, 10)
        self.assertEqual(span.start_col, 0)
        self.assertEqual(span.end_col, 0)
        self.assertTrue(span.is_valid())

    def test_whole_file_never_reports_a_line_below_one(self) -> None:
        """An empty file still has line 1; ``end_line`` 0 would be an invalid span."""
        span = SourceSpan.whole_file(0)
        self.assertEqual(span.end_line, 1)
        self.assertTrue(span.is_valid())


class QueryTests(unittest.TestCase):
    def test_line_count_counts_both_ends(self) -> None:
        self.assertEqual(SourceSpan(1, 0, 1, 5).line_count, 1)
        self.assertEqual(SourceSpan(1, 0, 3, 0).line_count, 3)

    def test_contains_line_is_inclusive_at_both_ends(self) -> None:
        span = SourceSpan(5, 0, 9, 0)
        for line in (5, 6, 7, 8, 9):
            with self.subTest(line=line):
                self.assertTrue(span.contains_line(line))
        for line in (4, 10):
            with self.subTest(line=line):
                self.assertFalse(span.contains_line(line))

    def test_is_zero_width_needs_both_line_and_column_to_match(self) -> None:
        self.assertTrue(SourceSpan(2, 3, 2, 3).is_zero_width())
        # Same line, different column: a real span on one line, not zero width.
        self.assertFalse(SourceSpan(2, 3, 2, 9).is_zero_width())
        self.assertFalse(SourceSpan(2, 3, 3, 3).is_zero_width())

    def test_spans_are_orderable(self) -> None:
        """``order=True`` is what lets spans be sorted deterministically."""
        spans = [SourceSpan(3, 0, 3, 1), SourceSpan(1, 0, 1, 1)]
        self.assertEqual(
            sorted(spans),
            [SourceSpan(1, 0, 1, 1), SourceSpan(3, 0, 3, 1)],
        )

    def test_spans_are_frozen_and_hashable(self) -> None:
        span = SourceSpan(1, 0, 1, 1)
        with self.assertRaises(Exception):
            span.start_line = 2  # type: ignore[misc]
        self.assertEqual(len({span, SourceSpan(1, 0, 1, 1)}), 1)


class ValidationTests(unittest.TestCase):
    def test_a_well_formed_span_has_no_problems(self) -> None:
        span = SourceSpan(1, 0, 4, 8)
        self.assertEqual(span.problems(), [])
        self.assertTrue(span.is_valid())

    def test_line_numbers_below_one_are_rejected(self) -> None:
        self.assertTrue(SourceSpan(0, 0, 1, 0).problems())
        self.assertTrue(SourceSpan(1, 0, 0, 0).problems())

    def test_negative_columns_are_rejected(self) -> None:
        self.assertTrue(SourceSpan(1, -1, 1, 0).problems())
        self.assertTrue(SourceSpan(1, 0, 1, -1).problems())

    def test_an_end_before_the_start_is_rejected(self) -> None:
        span = SourceSpan(5, 0, 2, 0)
        self.assertFalse(span.is_valid())
        self.assertTrue(any("precedes" in p for p in span.problems()))

    def test_validation_reports_every_problem_rather_than_the_first(self) -> None:
        """Rejection happens by returning problems, never by raising."""
        problems = SourceSpan(0, -1, 0, -1).problems()
        self.assertGreaterEqual(len(problems), 2)

    def test_validation_never_raises(self) -> None:
        for span in (
            SourceSpan(0, -5, -1, -9),
            SourceSpan(10, 0, 1, 0),
            SourceSpan(1, 0, 1, 0),
        ):
            with self.subTest(span=str(span)):
                self.assertIsInstance(span.problems(), list)


class SerialisationTests(unittest.TestCase):
    def test_to_dict_uses_the_documented_key_names(self) -> None:
        self.assertEqual(
            SourceSpan(1, 2, 3, 4).to_dict(),
            {"start_line": 1, "start_col": 2, "end_line": 3, "end_col": 4},
        )

    def test_str_is_line_colon_col_dash_line_colon_col(self) -> None:
        self.assertEqual(str(SourceSpan(1, 0, 2, 4)), "1:0-2:4")


if __name__ == "__main__":
    unittest.main()
