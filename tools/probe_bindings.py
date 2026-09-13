"""Probe a grammar's node names for binding-related constructs.

M1's first lesson: never guess tree-sitter node names. Grammar shapes differ
surprisingly (C nests names under `function_declarator`, Go uses a separate
`field_identifier`), so every capture pattern in `queries/*.scm` was written
against a dumped tree rather than a remembered one.

This tool dumps the real subtree for the three constructs a `BindingFact` needs:

    1. x = Type(...)                 local binding from a constructor call
    2. self.x = Type(...)            instance binding from a constructor call
    3. def f(self, p: Type)          parameter binding from an annotation
    4. self.x = p                    instance binding aliasing a parameter

    python tools/probe_bindings.py python
    python tools/probe_bindings.py python --source "self.repo = Repo()"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from maat.offline.parser import TreeSitterParser  # noqa: E402

#: Per-language snippets exercising the four binding shapes. Only languages
#: present here can be probed; add a key to extend coverage.
SAMPLES: dict[str, str] = {
    "python": (
        "def f(self, repo: Repo):\n"
        "    local = Service()\n"
        "    self.field = Service()\n"
        "    self.alias = repo\n"
        "    self.partial: Repo = make()\n"
    ),
    "javascript": (
        "function f(repo) {\n"
        "  const local = new Service();\n"
        "  this.field = new Service();\n"
        "  this.alias = repo;\n"
        "}\n"
    ),
    "java": (
        "class C {\n"
        "  void f(Repo repo) {\n"
        "    Service local = new Service();\n"
        "    this.field = new Service();\n"
        "    this.alias = repo;\n"
        "  }\n"
        "}\n"
    ),
    "go": (
        "package p\n"
        "func f(repo Repo) {\n"
        "  local := NewService()\n"
        "  var declared Service\n"
        "  _ = local\n"
        "  _ = declared\n"
        "}\n"
    ),
}


def dump(node: object, source: bytes, depth: int = 0, max_depth: int = 6) -> None:
    """Print a subtree with field names, indented."""
    indent = "  " * depth
    node_type = node.type  # type: ignore[attr-defined]
    is_named = node.is_named  # type: ignore[attr-defined]
    marker = "" if is_named else " (anonymous)"
    print(f"{indent}{node_type}{marker}")

    if depth >= max_depth:
        return

    for index in range(node.child_count):  # type: ignore[attr-defined]
        child = node.child(index)  # type: ignore[attr-defined]
        field = node.field_name_for_child(index)  # type: ignore[attr-defined]
        if field:
            print(f"{indent}  └─ field: {field}")
        dump(child, source, depth + 2, max_depth)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("language", nargs="?", default="python")
    parser.add_argument("--source", default=None, help="override the sample")
    parser.add_argument("--depth", type=int, default=6)
    args = parser.parse_args(argv[1:])

    language = args.language
    source_text = args.source if args.source is not None else SAMPLES.get(language)
    if source_text is None:
        print(f"no sample for {language!r}; available: {sorted(SAMPLES)}")
        return 1

    source = source_text.encode("utf-8")
    outcome = TreeSitterParser().parse(source, language, f"<probe>.{language}")
    if outcome.tree is None:
        print(f"parse produced no tree: {outcome.status}")
        for diagnostic in outcome.diagnostics:
            print(f"  {diagnostic}")
        return 1

    print(f"── {language} ── status {outcome.status}")
    print(source_text)
    print()
    dump(outcome.tree.root_node, source, 0, args.depth)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
