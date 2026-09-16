"""Run the whole MAAT test suite.

    python tests/run_all.py            # everything
    python tests/run_all.py -v         # verbose
    python tests/run_all.py offline    # only tests matching a pattern

Uses ``unittest`` from the standard library rather than pytest, so the suite
runs with no third-party test dependency. The only external requirement is
tree-sitter itself.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    verbosity = 2 if "-v" in argv else 1
    patterns = [a for a in argv[1:] if not a.startswith("-")]

    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=str(PROJECT_ROOT / "tests"),
        pattern="test_*.py",
        top_level_dir=str(PROJECT_ROOT),
    )

    if patterns:
        filtered = unittest.TestSuite()
        for test in _iter_tests(suite):
            name = test.id()
            if any(pattern in name for pattern in patterns):
                filtered.addTest(test)
        suite = filtered

    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    print()
    print(f"ran {result.testsRun} tests\n {result}")
    if result.failures:
        print(f"  failures: {len(result.failures)}")
    if result.errors:
        print(f"  errors:   {len(result.errors)}")
    if result.skipped:
        print(f"  skipped:  {len(result.skipped)}")
    if result.wasSuccessful():
        print("  result:   PASS")
    return 0 if result.wasSuccessful() else 1


def _iter_tests(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_tests(item)
        else:
            yield item


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
