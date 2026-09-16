"""Verify that every extraction query compiles and fires on a real sample.

Not part of the pipeline. For each language it:

1. loads the tree-sitter grammar and parses the sample from ``dump_trees.py``,
2. compiles ``maat/offline/queries/<language>.scm`` with ``tree_sitter.Query``,
3. runs ``QueryCursor(query).matches(tree.root_node)``,
4. reports the match count and which capture names fired.

It then checks the three properties the queries must satisfy for every language
that has one:

* the query compiles (no ``QueryError``),
* at least one definition capture fires,
* at least one call capture fires (``@call.fn`` or ``@call.attr``),
* at least one import capture fires (``@import.module``),

plus the structural convention that every match containing a ``@def.*`` capture
also contains a ``@name.*`` capture (the two-capture-per-pattern rule).
Constructors are exempt: an `init_declaration` / `primary_constructor` has no
identifier child of its own.

Usage:
    python tools/verify_queries.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import tree_sitter
import tree_sitter_language_pack as pack

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.dump_trees import SAMPLES  # noqa: E402

QUERY_DIR = ROOT / "maat" / "offline" / "queries"

LANGUAGES = [
    "python",
    "javascript",
    "typescript",
    "tsx",
    "java",
    "go",
    "rust",
    "c",
    "cpp",
    "csharp",
    "ruby",
    "php",
    "kotlin",
    "swift",
    "scala",
    "lua",
    "bash",
    "dart",
]

# tree-sitter returns capture names without the leading "@".
DEF_CAPTURES = {
    "def.class",
    "def.interface",
    "def.function",
    "def.method",
    "def.struct",
    "def.enum",
    "def.type",
    "def.module",
    "def.constructor",
    "def.field",
}
CALL_CAPTURES = {"call.fn", "call.attr"}

# Definition captures that are legitimately nameless, so a match carrying only
# these is allowed to have no matching @name.* capture.
NAMELESS_DEF_CAPTURES = {"def.constructor"}

# Some samples contain no call expression at all. These extra snippets are used
# only to prove the call patterns fire when a call *is* present; they do not
# change the pass/fail verdict for the sample itself.
EXTRA_SNIPPETS: dict[str, str] = {
    "tsx": "const a = foo(1);\nconst b = obj.bar(2);\n",
}


def count_captures(matches) -> dict[str, int]:
    """Collapse a match list into ``{capture_name: total_nodes}``."""
    counts: dict[str, int] = {}
    for _pattern_index, captures in matches:
        for name, nodes in captures.items():
            counts[name] = counts.get(name, 0) + (
                len(nodes) if isinstance(nodes, list) else 1
            )
    return counts


def run_query(language: str, source: str, text: str):
    """Compile and run a query against a snippet.

    Returns ``(query_error, matches)``. ``matches`` is empty when the query did
    not compile.
    """
    grammar = pack.get_language(language)
    parser = pack.get_parser(language)
    tree = parser.parse(text.encode("utf-8"))
    try:
        query = tree_sitter.Query(grammar, source)
    except Exception as error:  # noqa: BLE001 - QueryError is the point
        return str(error), []
    cursor = tree_sitter.QueryCursor(query)
    return None, cursor.matches(tree.root_node)


def unpaired_def_matches(matches) -> list[tuple[int, list[str]]]:
    """Matches that captured a named @def.* but no @name.* (convention violations)."""
    bad: list[tuple[int, list[str]]] = []
    for pattern_index, captures in matches:
        named_defs = {
            c
            for c in captures
            if c.startswith("def.") and c not in NAMELESS_DEF_CAPTURES
        }
        has_name = any(c.startswith("name.") for c in captures)
        if named_defs and not has_name:
            bad.append((pattern_index, sorted(captures)))
    return bad


def main() -> int:
    failures: list[str] = []
    partials: list[str] = []

    for language in LANGUAGES:
        sample = SAMPLES.get(language)
        query_path = QUERY_DIR / f"{language}.scm"
        print(f"=== {language} ===")

        if sample is None:
            print("  no sample in dump_trees.py")
            failures.append(language)
            continue
        if not query_path.is_file():
            print(f"  missing query file: {query_path}")
            failures.append(language)
            continue

        source = query_path.read_text(encoding="utf-8")
        error, matches = run_query(language, source, sample)
        if error is not None:
            print(f"  QUERY ERROR: {error}")
            failures.append(language)
            continue

        counts = count_captures(matches)
        fired = sorted(c for c in counts if not c.startswith("_"))
        print(f"  matches={len(matches)} captures={len(fired)}")
        print(f"  fired: {', '.join(fired) if fired else '(none)'}")

        has_def = any(c in counts for c in DEF_CAPTURES)
        has_call = any(c in counts for c in CALL_CAPTURES)
        has_import = "import.module" in counts

        problems: list[str] = []
        if not has_def:
            problems.append("no definition capture")
        if not has_call:
            problems.append("no call capture")
        if not has_import:
            problems.append("no import capture")

        bad_pairs = unpaired_def_matches(matches)
        if bad_pairs:
            problems.append(f"{len(bad_pairs)} @def.* match(es) without @name.*")

        if problems:
            # A missing call capture is only a real bug when the sample actually
            # contains a call; probe with a supplementary snippet to tell them
            # apart.
            if not has_call and language in EXTRA_SNIPPETS:
                extra_error, extra_matches = run_query(
                    language, source, EXTRA_SNIPPETS[language]
                )
                if extra_error is None:
                    extra_counts = count_captures(extra_matches)
                    if any(c in extra_counts for c in CALL_CAPTURES):
                        problems.remove("no call capture")
                        partials.append(
                            f"{language}: sample has no call expression; "
                            "call pattern verified with an extra snippet"
                        )

        if problems:
            print(f"  FAIL: {', '.join(problems)}")
            failures.append(language)
        else:
            note = ""
            if "doc" not in counts:
                note = "  (no @doc in this sample)"
            print(f"  OK{note}")

    print()
    print("--- summary ---")
    print(f"languages checked: {len(LANGUAGES)}")
    print(f"failed: {len(failures)} {failures if failures else ''}")
    for line in partials:
        print(f"note: {line}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
