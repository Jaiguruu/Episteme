"""Derive the suite figures quoted in the documentation.

The documentation states a test count, a class count and a file count (see
``docs/testing.md`` §6 and ``docs/verification.md`` §2). Those numbers were
hand-maintained and drifted: the class count was documented as 50 when the real
value was 53, and two per-file rows were wrong as well. This tool removes the
hand-maintenance — run it and paste the output, exactly as the docs describe the
source of the other measured figures.

Counting is a syntax question, so it is answered from the AST rather than by
importing the tests. Importing would execute module-level code and would report
a different number from the one ``unittest`` discovers if a module failed to
import.

    python tools/count_tests.py            # per-file table plus the totals
    python tools/count_tests.py --json     # machine-readable, for a doc check

A test is a ``def`` named ``test_*`` anywhere in the module, which is what
``unittest.TestLoader`` discovers. A class is a module-level ``class`` statement;
nested classes are helpers, not test cases.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys

TESTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "tests"


def _count_module(path: pathlib.Path) -> tuple[int, int]:
    """Return ``(tests, classes)`` for one module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tests = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )
    classes = sum(1 for node in tree.body if isinstance(node, ast.ClassDef))
    return tests, classes


def measure(root: pathlib.Path = TESTS_DIR) -> list[dict[str, object]]:
    """Measure every test module under ``root``, in sorted path order."""
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("test_*.py")):
        tests, classes = _count_module(path)
        if tests == 0:
            continue
        rows.append(
            {
                "file": path.relative_to(root.parent).as_posix(),
                "tests": tests,
                "classes": classes,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--json", action="store_true", help="emit JSON instead of a table"
    )
    args = parser.parse_args(argv)

    rows = measure()
    totals = {
        "tests": sum(int(r["tests"]) for r in rows),
        "classes": sum(int(r["classes"]) for r in rows),
        "files": len(rows),
    }

    if args.json:
        json.dump({"modules": rows, "totals": totals}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    width = max(len(str(r["file"])) for r in rows)
    for row in rows:
        print(
            f"{str(row['file']):<{width}}  "
            f"{int(row['tests']):>4} tests  {int(row['classes']):>2} classes"
        )
    print(
        f"\n{totals['tests']} tests, {totals['classes']} classes, "
        f"{totals['files']} files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
