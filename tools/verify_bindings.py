"""Report binding extraction coverage across every language in a repository.

The rollout harness for the `@bind.*` capture family. Rather than probing each
grammar by hand, this runs the real extractor over a real polyglot repository and
reports, per language, how many bindings were found. A language reporting zero is
one whose query file has no binding patterns yet.

    python tools/verify_bindings.py                       # the edge-case repo
    python tools/verify_bindings.py tests/fixtures/demo_repo
    python tools/verify_bindings.py --examples 3          # show sample bindings
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from maat.offline import languages  # noqa: E402
from maat.offline.extractors.query_extractor import (  # noqa: E402
    QueryExtractor,
    QueryUnavailableError,
)
from maat.offline.parser import TreeSitterParser  # noqa: E402
from maat.offline.snapshot import SnapshotOptions, scan_repository  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repository",
        nargs="?",
        default=str(PROJECT_ROOT / "tests" / "fixtures" / "edgecase_repo"),
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=0,
        help="show this many example bindings per language",
    )
    args = parser.parse_args(argv[1:])

    root = Path(args.repository).resolve()
    snapshot = scan_repository(root, SnapshotOptions())

    parser_backend = TreeSitterParser()
    extractor = QueryExtractor()

    bindings_by_language: Counter[str] = Counter()
    files_by_language: Counter[str] = Counter()
    scopes_by_language: defaultdict[str, Counter[str]] = defaultdict(Counter)
    examples: defaultdict[str, list[str]] = defaultdict(list)
    failed: list[tuple[str, str]] = []

    for record in snapshot.files:
        language = record.language
        if language is None:
            continue
        if languages.extraction_query_path(language) is None:
            continue

        try:
            source = (root / record.path).read_bytes()
            outcome = parser_backend.parse(source, language, record.path)
            facts = extractor.extract(outcome, record.path)
        except (QueryUnavailableError, OSError) as error:
            failed.append((record.path, str(error)))
            continue

        files_by_language[language] += 1
        bindings_by_language[language] += len(facts.bindings)
        for binding in facts.bindings:
            scopes_by_language[language][str(binding.scope)] += 1
            if len(examples[language]) < args.examples:
                examples[language].append(
                    f"{binding.bound_name} -> {binding.type_name} "
                    f"[{binding.scope}] in {binding.enclosing_qualified_name}"
                )

    print(f"repository: {root}")
    print(f"languages with a query file: {len(languages.extractable_languages())}")
    print()
    header = f"{'language':<13}{'files':>6}{'bindings':>10}  scopes"
    print(header)
    print("-" * len(header))

    missing: list[str] = []
    for language in sorted(languages.extractable_languages()):
        count = bindings_by_language.get(language, 0)
        files = files_by_language.get(language, 0)
        scopes = ",".join(
            f"{k}={v}" for k, v in sorted(scopes_by_language.get(language, {}).items())
        )
        flag = ""
        if files and count == 0:
            flag = "   <-- NEEDS PATTERNS"
            missing.append(language)
        print(f"{language:<13}{files:>6}{count:>10}  {scopes}{flag}")

    if args.examples:
        print()
        for language in sorted(examples):
            print(f"── {language}")
            for line in examples[language]:
                print(f"     {line}")

    if failed:
        print()
        print(f"errors ({len(failed)}):")
        for path, message in failed[:10]:
            print(f"  {path}: {message}")

    print()
    if missing:
        print(f"languages needing binding patterns ({len(missing)}): {', '.join(missing)}")
    else:
        print("every language with files produced at least one binding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
