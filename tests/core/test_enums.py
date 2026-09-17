"""Closed vocabularies in ``maat/core/enums.py``.

Every value here is a persisted contract: renaming or removing a member breaks
already-stored model versions, so the member sets are asserted rather than assumed.
"""

from __future__ import annotations

import unittest

from maat.core.enums import (
    RECOVERY_BLOCK,
    RECOVERY_FILE,
    RECOVERY_NONE,
    RECOVERY_STATEMENT,
    BindingScope,
    ChangeKind,
    DiagnosticSeverity,
    FileKind,
    ParseStatus,
    RelationshipType,
    ResolutionStatus,
    SymbolType,
    VersionStatus,
    _StrEnum,
)

#: Every closed vocabulary in the module.
STRING_ENUMS = (
    ParseStatus,
    SymbolType,
    BindingScope,
    RelationshipType,
    ResolutionStatus,
    DiagnosticSeverity,
    VersionStatus,
    FileKind,
    ChangeKind,
)


class StringEnumTests(unittest.TestCase):
    def test_every_member_is_a_str_enum(self) -> None:
        for enum_type in STRING_ENUMS:
            with self.subTest(enum=enum_type.__name__):
                self.assertTrue(issubclass(enum_type, _StrEnum))
                self.assertTrue(issubclass(enum_type, str))

    def test_str_returns_the_bare_value(self) -> None:
        """``str(ParseStatus.OK)`` must be ``"OK"``, not ``"ParseStatus.OK"``.

        These values are serialised straight into canonical JSON and, later, into
        SQLite columns. A qualified name would corrupt every persisted status.
        """
        for enum_type in STRING_ENUMS:
            for member in enum_type:
                with self.subTest(enum=enum_type.__name__, member=member.name):
                    self.assertEqual(str(member), member.value)
                    self.assertNotIn(".", str(member))
                    self.assertEqual(f"{member}", member.value)

    def test_members_are_usable_as_plain_strings(self) -> None:
        self.assertEqual(ParseStatus.OK, "OK")
        self.assertEqual("status=" + ParseStatus.FAILED, "status=FAILED")
        self.assertIn(RelationshipType.CALLS, {"CALLS", "IMPORTS"})

    def test_member_sets_are_exactly_what_is_persisted(self) -> None:
        self.assertEqual(
            {m.name for m in ParseStatus},
            {"OK", "PARTIAL", "FAILED", "EMPTY", "UNSUPPORTED"},
        )
        self.assertEqual(
            {m.name for m in ResolutionStatus},
            {"RESOLVED_EXACT", "RESOLVED_HEURISTIC", "AMBIGUOUS", "UNRESOLVED"},
        )
        self.assertEqual(
            {m.name for m in BindingScope}, {"LOCAL", "INSTANCE", "PARAMETER"}
        )
        self.assertEqual(
            {m.name for m in VersionStatus},
            {"BUILDING", "PUBLISHED", "FAILED", "SUPERSEDED"},
        )
        self.assertEqual(
            {m.name for m in FileKind},
            {"SOURCE", "BINARY", "GENERATED", "IGNORED", "UNSUPPORTED"},
        )


class ParseStatusTests(unittest.TestCase):
    def test_failed_is_the_only_error_status(self) -> None:
        """EMPTY and UNSUPPORTED are expected states, not errors.

        Treating them as errors would make an ordinary repository look broken.
        """
        for member in ParseStatus:
            with self.subTest(member=member.name):
                self.assertEqual(member.is_error, member is ParseStatus.FAILED)

    def test_partial_and_failed_are_degraded(self) -> None:
        self.assertTrue(ParseStatus.PARTIAL.is_degraded)
        self.assertTrue(ParseStatus.FAILED.is_degraded)
        self.assertFalse(ParseStatus.OK.is_degraded)
        self.assertFalse(ParseStatus.EMPTY.is_degraded)
        self.assertFalse(ParseStatus.UNSUPPORTED.is_degraded)


class RelationshipTypeTests(unittest.TestCase):
    def test_only_observed_relationship_types_are_declared(self) -> None:
        """Derived types must never enter the model as if they were observed.

        DEPENDS_ON and friends are computed by the graph projection in a later
        stage. Declaring them here would invite writing a derived edge into the
        semantic model, which section 4.3 forbids.
        """
        declared = {m.name for m in RelationshipType}
        self.assertEqual(
            declared,
            {"CONTAINS", "IMPORTS", "CALLS", "REFERENCES", "INHERITS", "IMPLEMENTS"},
        )
        for derived in (
            "DEPENDS_ON",
            "TRANSITIVELY_DEPENDS_ON",
            "IMPACTED_BY",
            "REACHABLE_FROM",
        ):
            self.assertNotIn(derived, declared)

    def test_reserved_members_are_still_present(self) -> None:
        """Reserved for later stages; removing them needs an explicit decision."""
        self.assertEqual(RelationshipType.REFERENCES, "REFERENCES")
        self.assertEqual(RelationshipType.IMPLEMENTS, "IMPLEMENTS")


class RecoveryVocabularyTests(unittest.TestCase):
    def test_recovery_levels_are_distinct_lowercase_tokens(self) -> None:
        levels = [RECOVERY_NONE, RECOVERY_STATEMENT, RECOVERY_BLOCK, RECOVERY_FILE]
        self.assertEqual(len(set(levels)), len(levels))
        for level in levels:
            with self.subTest(level=level):
                self.assertEqual(level, level.lower())


if __name__ == "__main__":
    unittest.main()
