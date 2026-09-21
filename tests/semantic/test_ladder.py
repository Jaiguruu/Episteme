"""The resolution precedence ladder in ``maat/semantic/ladder.py``.

Covers section 13 (symbol and relationship resolution) and decision D24. The ladder
carries no resolution logic: it states which syntactic fact justifies an edge, and
what status and confidence follow from it. The resolver that walks it is tested
separately.
"""

from __future__ import annotations

import unittest

from maat.core.enums import ResolutionStatus
from maat.semantic import (
    INSTANCE_RECEIVERS,
    ResolutionRung,
    resolve_qualified_name,
)


class LadderOrderTests(unittest.TestCase):
    """Section 13, D24 -- the ladder is ordered by how much the evidence constrains."""

    def test_every_rung_has_a_position(self) -> None:
        for rung in ResolutionRung:
            with self.subTest(rung=rung.name):
                self.assertIsInstance(rung.order, int)

    def test_positions_are_contiguous_from_one(self) -> None:
        """A gap would silently change which rung wins.

        The ordering *is* the correctness argument -- a rung is tried only if every
        rung above it failed -- so a missing or duplicated position means a
        mis-ordered ladder, and that is invisible in a passing suite unless asserted.
        """
        positions = sorted(rung.order for rung in ResolutionRung)
        self.assertEqual(positions, list(range(1, len(ResolutionRung) + 1)))

    def test_order_is_a_total_order_with_no_duplicates(self) -> None:
        orders = [rung.order for rung in ResolutionRung]
        self.assertEqual(len(set(orders)), len(orders))

    def test_same_file_is_strongest_and_none_is_weakest(self) -> None:
        self.assertEqual(ResolutionRung.SAME_FILE_EXACT.order, 1)
        self.assertEqual(ResolutionRung.NONE.order, len(ResolutionRung))


class RungPolicyTests(unittest.TestCase):
    """Section 13 -- every rung declares the status and confidence it produces."""

    def test_every_rung_declares_a_status(self) -> None:
        for rung in ResolutionRung:
            with self.subTest(rung=rung.name):
                self.assertIsInstance(rung.status, ResolutionStatus)

    def test_every_rung_declares_a_confidence_within_range(self) -> None:
        for rung in ResolutionRung:
            with self.subTest(rung=rung.name):
                self.assertGreaterEqual(rung.confidence, 0.0)
                self.assertLessEqual(rung.confidence, 1.0)

    def test_confidence_agrees_with_status(self) -> None:
        """A stored confidence must never contradict a stored status.

        Certainty is binary: every rung that resolves exactly is certain, and the
        ambiguous and failure rungs are not. Deriving confidence from the rung is
        what makes disagreement impossible rather than merely unlikely.
        """
        for rung in ResolutionRung:
            with self.subTest(rung=rung.name):
                if rung.status is ResolutionStatus.RESOLVED_EXACT:
                    self.assertEqual(rung.confidence, 1.0)
                else:
                    self.assertEqual(rung.confidence, 0.0)

    def test_only_the_ambiguous_rungs_are_ambiguous(self) -> None:
        ambiguous = {
            rung
            for rung in ResolutionRung
            if rung.status is ResolutionStatus.AMBIGUOUS
        }
        self.assertEqual(
            ambiguous,
            {
                ResolutionRung.AMBIGUOUS_IN_MODEL,
                ResolutionRung.ATTRIBUTE_CHAIN_AMBIGUOUS,
            },
        )

    def test_only_the_none_rung_is_unresolved(self) -> None:
        unresolved = {
            rung
            for rung in ResolutionRung
            if rung.status is ResolutionStatus.UNRESOLVED
        }
        self.assertEqual(unresolved, {ResolutionRung.NONE})

    def test_no_rung_claims_heuristic(self) -> None:
        """``RESOLVED_HEURISTIC`` is deliberately unfired.

        Nothing in the model provides evidence of "probable but not certain", so a
        rung using it would be manufacturing exactly the confident wrong edge that
        section 4.2 forbids. Asserting this makes adding one a deliberate act.
        """
        for rung in ResolutionRung:
            with self.subTest(rung=rung.name):
                self.assertIsNot(rung.status, ResolutionStatus.RESOLVED_HEURISTIC)

    def test_str_returns_the_bare_value(self) -> None:
        """Rung names appear in reports and logs, so they must not be qualified."""
        for rung in ResolutionRung:
            with self.subTest(rung=rung.name):
                self.assertEqual(str(rung), rung.value)
                self.assertEqual(f"{rung}", rung.value)


class ReceiverNameTests(unittest.TestCase):
    """Section 13 -- receiver names meaning "the current instance or type"."""

    def test_the_known_receiver_names_are_recognised(self) -> None:
        for name in ("self", "this", "cls", "Self"):
            with self.subTest(name=name):
                self.assertIn(name, INSTANCE_RECEIVERS)

    def test_the_set_is_exactly_these_four(self) -> None:
        """Widening this set changes resolution behaviour, so it is asserted.

        A name added here silently reclassifies a receiver as an instance, which is
        a behavioural change rather than a cosmetic one.
        """
        self.assertEqual(
            INSTANCE_RECEIVERS, frozenset({"self", "this", "cls", "Self"})
        )

    def test_it_is_immutable(self) -> None:
        self.assertIsInstance(INSTANCE_RECEIVERS, frozenset)


class QualifiedNameMatchTests(unittest.TestCase):
    """Section 13 -- matching a dotted name against known qualified names."""

    NAMES = frozenset(
        {
            "a.py:Outer.Inner.method",
            "a.py:Outer.save",
            "pkg.mod:Service.process",
        }
    )

    def test_an_exact_qualified_name_matches(self) -> None:
        rung, matches = resolve_qualified_name("a.py:Outer.save", self.NAMES)
        self.assertIs(rung, ResolutionRung.ATTRIBUTE_CHAIN)
        self.assertEqual(matches, ["a.py:Outer.save"])

    def test_a_dotted_tail_matches_at_a_segment_boundary(self) -> None:
        rung, matches = resolve_qualified_name("Inner.method", self.NAMES)
        self.assertIs(rung, ResolutionRung.ATTRIBUTE_CHAIN)
        self.assertEqual(matches, ["a.py:Outer.Inner.method"])

    def test_an_unknown_name_returns_the_none_rung(self) -> None:
        rung, matches = resolve_qualified_name("ghost.method", self.NAMES)
        self.assertIs(rung, ResolutionRung.NONE)
        self.assertEqual(matches, [])

    def test_an_empty_name_returns_the_none_rung(self) -> None:
        rung, matches = resolve_qualified_name("", self.NAMES)
        self.assertIs(rung, ResolutionRung.NONE)
        self.assertEqual(matches, [])

    def test_a_partial_segment_does_not_match(self) -> None:
        """The boundary check keeps a short name from picking up strangers.

        Without it, ``er.save`` would match ``Outer.save`` -- a silent wrong answer
        rather than an explicit miss.
        """
        rung, matches = resolve_qualified_name("er.save", self.NAMES)
        self.assertIs(rung, ResolutionRung.NONE)
        self.assertEqual(matches, [])

    def test_several_matches_are_ambiguous_not_guessed(self) -> None:
        names = frozenset({"a.py:One.save", "b.py:Two.save"})
        rung, matches = resolve_qualified_name("save", names)
        self.assertIs(rung, ResolutionRung.ATTRIBUTE_CHAIN_AMBIGUOUS)
        self.assertEqual(matches, ["a.py:One.save", "b.py:Two.save"])

    def test_matches_are_sorted_for_determinism(self) -> None:
        names = frozenset({"z.py:X.save", "a.py:Y.save"})
        _, matches = resolve_qualified_name("save", names)
        self.assertEqual(matches, sorted(matches))


if __name__ == "__main__":
    unittest.main()
