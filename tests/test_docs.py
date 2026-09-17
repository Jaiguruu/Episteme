"""Documentation hygiene guard for decision D33.

A ``model_version`` is a digest of the raw bytes of every scanned file, so it varies
with line-ending policy and with any fixture edit. Quoting one in the documentation
produces a number the reader cannot reproduce -- which is worse than quoting none,
because it invites distrust of the figures that *are* correct. Both ``README.md`` and
``docs/testing.md`` carried stale IDs until D33 removed them.

This module enforces the decision. It is deliberately three tests rather than one: a
scan that finds nothing passes trivially if its pattern is broken, so the detector is
proved against known-bad and known-good strings first. Without that, the guard could
rot into a no-op and still report green.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: A concrete version ID: ``mv_`` followed by 16 hex characters.
#: Word boundaries keep a placeholder such as ``mv_<digest>`` and a synthetic
#: value such as ``mv_1`` from matching.
VERSION_ID_PATTERN = re.compile(r"\bmv_[0-9a-f]{16}\b")

#: Documentation is what this guard polices. Fixtures are arbitrary test data,
#: and the agent scratch directory is not ours to police.
DOC_SUFFIXES = (".md", ".html", ".htm")
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".workbuddy-ai",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "fixtures",
    }
)


def iter_documentation(root: Path = PROJECT_ROOT):
    """Yield every documentation file under ``root``, in a stable order.

    Walks with in-place pruning rather than ``rglob``. ``rglob`` descends into
    every directory *before* the filter can reject it, so it walked the whole
    ``.git`` object store and made this guard dominate the suite's runtime.
    Pruning ``dir_names`` stops the descent instead of discarding its results,
    which is the same technique ``maat/offline/snapshot.py`` uses.
    """
    for current_dir, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(
            name for name in dir_names if name.lower() not in SKIPPED_DIRECTORIES
        )
        for name in sorted(file_names):
            if name.lower().endswith(DOC_SUFFIXES):
                yield Path(current_dir) / name


class DocumentationHygieneTest(unittest.TestCase):
    def test_detector_recognises_a_version_id(self) -> None:
        """The guard must be able to fail, or it proves nothing.

        Uses a synthetic value rather than a real one: the point is the shape, and
        re-introducing a real digest anywhere would defeat D33's purpose.
        """
        self.assertIsNotNone(VERSION_ID_PATTERN.search("mv_0011223344556677"))
        self.assertIsNotNone(VERSION_ID_PATTERN.search('  "mv_0011223344556677"'))

    def test_detector_ignores_placeholders_and_synthetic_values(self) -> None:
        """``mv_<digest>`` is the documented way to refer to a version without quoting one."""
        self.assertIsNone(VERSION_ID_PATTERN.search("mv_<digest>"))
        self.assertIsNone(VERSION_ID_PATTERN.search("mv_1"))
        # 15 hex characters: one short of an ID.
        self.assertIsNone(VERSION_ID_PATTERN.search("mv_001122334455667"))

    def test_no_documentation_quotes_a_concrete_version_id(self) -> None:
        offenders: list[str] = []
        for path in iter_documentation():
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in VERSION_ID_PATTERN.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                location = path.relative_to(PROJECT_ROOT).as_posix()
                offenders.append(f"{location}:{line}: {match.group()}")

        self.assertEqual(
            offenders,
            [],
            "Documentation must not quote a concrete model_version (D33). Use "
            "'mv_<digest>', or describe the version instead of printing it:\n  "
            + "\n  ".join(offenders),
        )
