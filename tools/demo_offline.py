"""Demo: index a repository and report what the offline pipeline produced.

This is a demonstration harness, not the Stage 23 CLI. It exists so the
pipeline's behaviour can be seen and reproduced without writing Python.

    python tools/demo_offline.py                            # the demo fixture
    python tools/demo_offline.py tests/fixtures/edgecase_repo
    python tools/demo_offline.py <repo> --touch <file>      # show incremental work
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from maat.offline import languages  # noqa: E402
from maat.offline.pipeline import OfflinePipeline  # noqa: E402


def rule(title: str) -> None:
    print()
    print(f"── {title} " + "─" * max(0, 68 - len(title)))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repository",
        nargs="?",
        default=str(PROJECT_ROOT / "tests" / "fixtures" / "demo_repo"),
    )
    parser.add_argument(
        "--index-dir",
        default=None,
        help="where to persist the model (default: <repo>/.maat)",
    )
    parser.add_argument(
        "--touch",
        default=None,
        help="append a comment to this repo-relative file, then reindex",
    )
    args = parser.parse_args(argv[1:])

    root = Path(args.repository).resolve()
    index_dir = Path(args.index_dir) if args.index_dir else root / ".maat"

    pipeline = OfflinePipeline()

    rule("index")
    first = pipeline.index(root, index_dir=index_dir)
    print(f"repository      {root}")
    print(f"index           {index_dir}")
    print(f"model version   {first.version.id}")
    print(f"files           {len(first.ir.files)}")
    print(f"symbols         {len(first.ir.symbols)}")
    print(f"relationships   {len(first.ir.relationships)}")
    print(f"evidence        {len(first.ir.evidence)}")
    print(f"chunks          {len(first.ir.chunks)}")
    print(f"duration        {first.stats.duration_ms} ms")

    rule("parse status")
    for status, count in sorted(
        Counter(str(f.parse_status) for f in first.ir.files).items()
    ):
        print(f"{status:<14} {count}")

    rule("languages")
    for language, count in first.snapshot.language_histogram().items():
        marker = "" if languages.extraction_query_path(language) else "  (parse only)"
        print(f"{language:<14} {count}{marker}")

    excluded = first.snapshot.exclusion_counts()
    if excluded:
        rule("excluded from the manifest")
        for reason, count in excluded.items():
            print(f"{reason:<14} {count}")

    degraded = [f for f in first.ir.files if f.is_degraded]
    if degraded:
        rule(f"degraded files ({len(degraded)})")
        for record in degraded:
            print(f"{record.parse_status:<9} {record.path}")
            if record.parse_error:
                print(f"          {record.parse_error}")
        print()
        print("Repository remains queryable: the healthy files are unaffected.")

    rule("sample symbols")
    for symbol in first.ir.symbols[:12]:
        print(f"{str(symbol.symbol_type):<12} {symbol.qualified_name}")

    rule("sample relationships")
    symbols = {s.id: s for s in first.ir.symbols}
    for relationship in first.ir.relationships[:12]:
        source = symbols.get(relationship.source_symbol_id)
        print(
            f"{str(relationship.relationship_type):<10} "
            f"{str(relationship.resolution_status):<18} "
            f"{source.qualified_name if source else '?':<45} -> {relationship.target_name}"
        )

    if args.touch:
        rule(f"incremental: touch {args.touch}")
        target = root / args.touch
        with open(target, "a", encoding="utf-8", newline="\n") as stream:
            stream.write("\n# touched by demo_offline.py\n")
        second = pipeline.index(root, index_dir=index_dir)
        print(f"changed files    {len(second.changes.changed)}")
        print(f"reparsed files   {second.stats.files_parsed}")
        print(f"reused files     {second.stats.files_reused}")
        print(f"model version    {second.version.id}")
        print(f"parent version   {second.version.parent_id}")
        print()
        print("No unrelated file was reparsed.")

    rule("validation")
    if first.is_valid:
        print("model is valid: no referential or structural problems")
    else:
        for problem in first.validation_problems[:20]:
            print(f"  {problem}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
