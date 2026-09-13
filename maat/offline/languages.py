"""Language registry: file path -> tree-sitter grammar name.

The grammar itself is never written by us. ``tree_sitter_language_pack`` ships
pre-compiled grammars for several hundred languages, and this module is the
single place that decides which one a given file belongs to.

Three deliberate choices:

1. **An explicit table, not the pack's ``detect_language_from_path``.** The
   pack's detector maps ``.csv`` to a CSV grammar and ``.txt`` to a text
   grammar. Those are not source code and must not enter the semantic model as
   if they were. An explicit table also means language detection is
   deterministic and reviewable, which section 8 AC5 requires.

2. **Extraction coverage is tiered and derived from the filesystem, not
   hard-coded.** A language is extractable exactly when a query file exists in
   ``maat/offline/queries/<key>.scm``. Nothing to keep in sync: dropping in a
   new query file upgrades the language with no code change, and deleting one
   downgrades it cleanly.

3. **Parse coverage is much wider than extraction coverage.** Every registered
   language can be parsed, because the grammar exists. Only languages with a
   query file yield symbols. A parse-only language is reported honestly as such
   rather than silently producing an empty symbol set (section 10 AC4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

#: Directory holding the declarative extraction queries.
QUERY_DIR = Path(__file__).resolve().parent / "queries"


@dataclass(frozen=True)
class LanguageSpec:
    """One grammar, and the file names that select it."""

    key: str
    """tree-sitter grammar name, e.g. ``"python"``. Must be loadable by the pack."""

    display: str
    """Human-readable name for reports."""

    extensions: tuple[str, ...] = ()
    """Lower-case extensions including the dot."""

    filenames: tuple[str, ...] = ()
    """Exact file names that select this language regardless of extension."""

    is_code: bool = True
    """False for data/config formats. They are still parsed but are not
    treated as sources of symbols, so they never appear as degraded files."""


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

_SPECS: tuple[LanguageSpec, ...] = (
    # --- languages with extraction queries -------------------------------
    LanguageSpec("python", "Python", (".py", ".pyi", ".pyw")),
    LanguageSpec("javascript", "JavaScript", (".js", ".mjs", ".cjs", ".jsx")),
    LanguageSpec("typescript", "TypeScript", (".ts", ".mts", ".cts")),
    LanguageSpec("tsx", "TypeScript JSX", (".tsx",)),
    LanguageSpec("java", "Java", (".java",)),
    LanguageSpec("go", "Go", (".go",)),
    LanguageSpec("rust", "Rust", (".rs",)),
    LanguageSpec("c", "C", (".c", ".h")),
    LanguageSpec("cpp", "C++", (".cc", ".cpp", ".cxx", ".c++", ".hpp", ".hh", ".hxx")),
    LanguageSpec("csharp", "C#", (".cs",)),
    LanguageSpec("ruby", "Ruby", (".rb", ".rake", ".gemspec")),
    LanguageSpec("php", "PHP", (".php", ".phtml")),
    LanguageSpec("kotlin", "Kotlin", (".kt", ".kts")),
    LanguageSpec("swift", "Swift", (".swift",)),
    LanguageSpec("scala", "Scala", (".scala", ".sc")),
    LanguageSpec("lua", "Lua", (".lua",)),
    LanguageSpec("bash", "Shell", (".sh", ".bash", ".zsh")),
    LanguageSpec("dart", "Dart", (".dart",)),
    # --- parse-only languages --------------------------------------------
    LanguageSpec("elixir", "Elixir", (".ex", ".exs")),
    LanguageSpec("erlang", "Erlang", (".erl", ".hrl")),
    LanguageSpec("haskell", "Haskell", (".hs",)),
    LanguageSpec("ocaml", "OCaml", (".ml", ".mli")),
    LanguageSpec("clojure", "Clojure", (".clj", ".cljs", ".cljc")),
    LanguageSpec("perl", "Perl", (".pl", ".pm")),
    LanguageSpec("r", "R", (".r", ".R")),
    LanguageSpec("julia", "Julia", (".jl",)),
    LanguageSpec("nim", "Nim", (".nim",)),
    LanguageSpec("zig", "Zig", (".zig",)),
    LanguageSpec("gdscript", "GDScript", (".gd",)),
    LanguageSpec("groovy", "Groovy", (".groovy", ".gradle")),
    LanguageSpec("fsharp", "F#", (".fs", ".fsi", ".fsx")),
    LanguageSpec("vb", "Visual Basic", (".vb",)),
    LanguageSpec("powershell", "PowerShell", (".ps1", ".psm1")),
    LanguageSpec("batch", "Batch", (".bat", ".cmd")),
    LanguageSpec("objc", "Objective-C", (".mm",)),
    LanguageSpec("asm", "Assembly", (".asm", ".s", ".S")),
    LanguageSpec("solidity", "Solidity", (".sol",)),
    LanguageSpec("proto", "Protocol Buffers", (".proto",)),
    LanguageSpec("thrift", "Thrift", (".thrift",)),
    LanguageSpec("graphql", "GraphQL", (".graphql", ".gql")),
    LanguageSpec("sql", "SQL", (".sql",), is_code=False),
    LanguageSpec("hcl", "HCL / Terraform", (".tf", ".tfvars", ".hcl"), is_code=False),
    LanguageSpec("dockerfile", "Dockerfile", (), ("Dockerfile",), is_code=False),
    LanguageSpec("make", "Makefile", (".mk",), ("Makefile", "makefile", "GNUmakefile")),
    LanguageSpec("cmake", "CMake", (".cmake",), ("CMakeLists.txt",), is_code=False),
    LanguageSpec("css", "CSS", (".css",), is_code=False),
    LanguageSpec("scss", "SCSS", (".scss",), is_code=False),
    LanguageSpec("html", "HTML", (".html", ".htm"), is_code=False),
    LanguageSpec("vue", "Vue", (".vue",)),
    LanguageSpec("svelte", "Svelte", (".svelte",)),
    LanguageSpec("xml", "XML", (".xml", ".xsd", ".xsl"), is_code=False),
    LanguageSpec("json", "JSON", (".json",), is_code=False),
    LanguageSpec("yaml", "YAML", (".yaml", ".yml"), is_code=False),
    LanguageSpec("toml", "TOML", (".toml",), is_code=False),
    LanguageSpec("markdown", "Markdown", (".md", ".markdown"), is_code=False),
    LanguageSpec("rst", "reStructuredText", (".rst",), is_code=False),
    LanguageSpec("csv", "CSV", (".csv", ".tsv"), is_code=False),
    LanguageSpec("ini", "INI", (".ini", ".cfg"), is_code=False),
    LanguageSpec("gitignore", "gitignore", (), (".gitignore",), is_code=False),
    LanguageSpec("requirements", "Python requirements", (), ("requirements.txt",), is_code=False),
    LanguageSpec("gomod", "Go module", (), ("go.mod",), is_code=False),
)


LANGUAGE_SPECS: dict[str, LanguageSpec] = {spec.key: spec for spec in _SPECS}

_EXTENSION_INDEX: dict[str, str] = {}
_FILENAME_INDEX: dict[str, str] = {}
for _spec in _SPECS:
    for _ext in _spec.extensions:
        # First writer wins, so an earlier, more specific spec keeps the
        # extension if two specs ever claim the same one.
        _EXTENSION_INDEX.setdefault(_ext.lower(), _spec.key)
    for _name in _spec.filenames:
        _FILENAME_INDEX.setdefault(_name, _spec.key)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def detect_language(path: str) -> str | None:
    """Return the tree-sitter grammar key for a repository-relative path.

    Returns ``None`` for anything not in the registry. ``None`` is a meaningful
    answer -- it drives ``FileKind.UNSUPPORTED`` and ``ParseStatus.UNSUPPORTED``
    rather than an exception (section 10 AC4).
    """
    name = path.rsplit("/", 1)[-1]
    if name in _FILENAME_INDEX:
        return _FILENAME_INDEX[name]
    lowered = name.lower()
    if lowered in _FILENAME_INDEX:
        return _FILENAME_INDEX[lowered]
    dot = lowered.rfind(".")
    if dot <= 0:
        return None
    return _EXTENSION_INDEX.get(lowered[dot:])


def is_code_language(language: str | None) -> bool:
    if language is None:
        return False
    spec = LANGUAGE_SPECS.get(language)
    return bool(spec and spec.is_code)


def display_name(language: str | None) -> str:
    if language is None:
        return "Unknown"
    spec = LANGUAGE_SPECS.get(language)
    return spec.display if spec else language


def extraction_query_path(language: str) -> Path | None:
    """Path to the extraction query for a language, or ``None`` if it has none.

    Derived from the filesystem so coverage can never drift from reality.
    """
    candidate = QUERY_DIR / f"{language}.scm"
    return candidate if candidate.is_file() else None


@lru_cache(maxsize=1)
def extractable_languages() -> frozenset[str]:
    """Every language that currently has an extraction query."""
    if not QUERY_DIR.is_dir():
        return frozenset()
    return frozenset(p.stem for p in QUERY_DIR.glob("*.scm"))


def registered_language_count() -> int:
    return len(LANGUAGE_SPECS)


def registry_summary() -> dict[str, int]:
    return {
        "registered": len(LANGUAGE_SPECS),
        "code_languages": sum(1 for s in _SPECS if s.is_code),
        "extensions": len(_EXTENSION_INDEX),
        "filenames": len(_FILENAME_INDEX),
        "extractable": len(extractable_languages()),
    }
