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
- **Bindings are now persisted.** `BindingFact` was captured in Tier 2 but dropped
  at the Tier 3 boundary, so Stage 6 had nothing to resolve a member call against.
  `SemanticIR` gains a seventh collection, `bindings`, holding a `Binding` entity
  per resolvable fact with a `bind_*` content-addressed ID. `demo_repo` yields 15
  bindings, all three of them surviving the extractor, the model and `ir.json`.
- **A dedicated test module for `maat/core/`.** `tests/core/` adds 114 tests across
  `test_enums.py`, `test_locations.py`, `test_contracts.py` and
  `test_serialization.py`, covering behaviour that until now was only exercised
  indirectly. The suite is 275 tests, up from 137.
- **A guard against documentation drift.** `tests/test_docs.py` fails the suite if a
  concrete `model_version` value is quoted in any tracked document (D33), since a
  version ID is a raw-byte digest and does not reproduce across line-ending policies.
- **`tools/count_tests.py`,** which derives the test/class/file figures the docs quote
  by walking the AST. The counts were hand-maintained and had drifted — the documented
  class total was 50 against a real 53, and two per-file rows were wrong.
- **Stage 6: symbol and relationship resolution** (`maat/semantic/`). A new sibling
  package resolves observed references to real symbols through a nine-rung precedence
  ladder (D24), so an edge's status *is* its explanation. On `demo_repo` every one of
  the 42 edges resolves exactly and the spec's §7 chain is now walkable as real
  `CALLS` edges rather than only as module imports; on `edgecase_repo` the 494
  initially-unresolved edges become 177 unresolved and 62 explicitly ambiguous. The
  resolver never invents a target (AC5, asserted) and never guesses between candidates
  (AC3) — ambiguity is recorded with a bounded candidate list instead.
- **A pipeline fingerprint on version identity (D27).** A version ID is now derived
  from file content *and* the identity of the pipeline that interpreted it. Resolution
  changes the model without touching a file, so without this a resolved model and an
  unresolved one built from the same bytes would share a `model_version` ID and
  incremental reuse would serve the wrong one. `index_repository(..., resolve=True)`
  is opt-in, so M1's output stays reproducible bit-for-bit.

### Changed

- `.gitignore` now covers build artifacts, caches, editor files, the runtime
  index directory and agent scratch memory. 33 generated files were removed from
  version control (27 bytecode files, 4 committed index artifacts, 2 scratch
  files). Tracked files: 261 → 228.
- The specification was renamed from `Problem_doc.md` to `SPEC.md` and gained a
  table of contents.

### Fixed

- **A structurally invalid `ir.json` aborted the index run instead of triggering a
  rebuild.** `load_previous_ir` wrapped the JSON parse but not the rehydration that
  follows it, so a payload that parsed but did not match the persisted shape raised
  `KeyError`, `ValueError` or `TypeError` out of `index_repository` — breaking the
  function's own documented promise that a corrupt model is treated as absent. The
  guard now wraps rehydration as well and reports absence. The realistic trigger is
  schema drift across versions, not a truncated write, since publication is atomic.
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
- **Documentation quoted `model_version` values that do not travel between
  checkouts.** `README.md` and `docs/testing.md` quoted concrete `mv_*` values. A
  model version is a digest of the raw bytes of every scanned file, so a checkout
  with `core.autocrlf=true` derives a different value than an LF checkout does from
  identical source — the quoted IDs did not reproduce, while the symbol and
  relationship counts beside them did. The IDs are removed rather than
  re-measured, `docs/testing.md` §4 now states the mechanism instead of only the
  rule, and `tests/test_docs.py` guards against reintroducing them.
- **`edgecase_repo` was documented as holding 156 files.** It holds 155: 142
  scanned, 8 excluded as files (1 binary, 3 generated, 4 ignored), and 5 inside 4
  pruned directories. The docs now state the composition rather than a bare total.
- **A model written by an earlier build was reloaded as if it were current.** With
  `bindings` added as a seventh collection (D34), a payload written before it
  existed did not fail to load — it loaded, was reused, and produced a new model
  silently missing a whole collection while carrying the *identical*
  `model_version` ID as a correct build. `EXPECTED_COLLECTIONS` now guards the
  loader: a payload missing any collection is treated as stale and rebuilt, which
  costs one full index for the upgrade and makes the silent-corruption case
  impossible.

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
