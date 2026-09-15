# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- Packaging metadata (`pyproject.toml`) and an Apache-2.0 `LICENSE`. The project
  is now installable with `pip install -e .`.
- Public API re-exported from `maat.offline`, so `from maat.offline import
  index_repository` works as documented.
- Contributor documentation: `ARCHITECTURE.md`, `CONTRIBUTING.md`, `ROADMAP.md`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`, and a `docs/` reference set.
- Continuous integration covering the test suite on Linux and Windows, plus a
  job that verifies all extraction queries compile and fire their captures.

### Changed

- `.gitignore` now covers build artifacts, caches, editor files, the runtime
  index directory and agent scratch memory. 33 generated files were removed from
  version control (27 bytecode files, 4 committed index artifacts, 2 scratch
  files). Tracked files: 261 → 228.
- The specification was renamed from `Problem_doc.md` to `SPEC.md` and gained a
  table of contents.

### Fixed

- **The documented import was broken.** `maat/offline/__init__.py` was a
  docstring-only module that exported nothing, so `from maat.offline import
  index_repository` raised `ImportError`.
- **A built wheel shipped no extraction queries.** `maat/offline/queries/` has no
  `__init__.py` — it is a data directory resolved relative to `languages.py` — so
  without an explicit `package-data` entry an installed wheel silently extracted
  nothing.
- **Stale index artifacts poisoned the documented demo.** Two fixture
  `.maat/` directories were committed. The `demo_repo` one held 7 symbols and 0
  relationships while carrying the same `model_version` as a correct build, so
  the documented demo command reused the degraded entities and reported 7/0
  instead of 26/42. They are now untracked and removed.

---

## [0.1.0] — M1

The first milestone: Stages 0–5 of the specification. A deterministic,
fault-tolerant offline pipeline that turns a repository directory into a
validated, language-neutral semantic model.

### Added

- **Contracts** (`maat/core/`) — closed vocabularies, source spans,
  content-addressed IDs, the entity contracts, and canonical JSON serialisation
  with atomic writes.
- **Language registry** (`maat/offline/languages.py`) — 61 languages matched by
  extension and exact filename.
- **Repository snapshot** (`maat/offline/snapshot.py`) — sorted traversal, ignore
  rules, binary sniffing, generated-file detection, and byte-level content
  hashing. Excluded files are recorded with a reason rather than dropped.
- **Incremental change detection** (`maat/offline/changes.py`) — manifest diffing
  producing `NEW / CHANGED / DELETED / RENAMED / UNCHANGED`, with rename detection
  by content hash.
- **Tree-sitter parsing** (`maat/offline/parser.py`) — one grammar per language
  behind a `ParserBackend` protocol, with a status ladder and statement-level
  error tolerance.
- **Extraction queries** (`maat/offline/queries/*.scm`) — 18 declarative
  tree-sitter queries. A language becomes extractable the moment its `.scm` file
  exists; no Python changes are required.
- **Language-neutral extraction** (`maat/offline/extractors/`) — one query-driven
  extractor serving every language, producing symbols, imports, calls,
  inheritance and bindings.
- **Semantic IR** (`maat/offline/ir_builder.py`) — facts validated into symbols,
  relationships, evidence and retrieval chunks.
- **Pipeline** (`maat/offline/pipeline.py`) — orchestration, incremental reuse,
  and atomic publication that only writes a model which passes validation.
- **Test suite** — 137 tests using stdlib `unittest`, with two fixtures: a 7-file
  demo repository and a 156-file polyglot repository that exercises 18 grammars
  and deliberately malformed input.

### Notes

- Every reference is emitted as `UNRESOLVED` by design. Only `CONTAINS` is
  resolved, because containment is structural rather than a reference. Resolution
  is Stage 6.
- The parser abstraction was originally planned around a hand-written lexer and
  recursive-descent parser. That approach was replaced mid-milestone by
  tree-sitter with declarative queries, and no hand-written parser was ever
  built.

[Unreleased]: https://github.com/Jaiguruu/Episteme/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Jaiguruu/Episteme/releases/tag/v0.1.0
