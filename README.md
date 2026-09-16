# Episteme

### MAAT's offline knowledge plane

**Episteme** turns a source repository into a **deterministic, queryable semantic
model** — without an LLM, without network access, and without a database. It reads
files, parses them with [Tree-sitter](https://tree-sitter.github.io/tree-sitter/),
extracts language-neutral facts, and produces a versioned `SemanticIR`.

It is the offline half of **MAAT** (Repository Intelligence Agent), and the
substrate the online pipeline reasons over.

> **M1 · Stages 0–5** of the [MAAT roadmap](ROADMAP.md)

```text
Source repository
       │
       ▼
   Snapshot ──► Change detection ──► Tree-sitter parsing
                                            │
                                            ▼
                                   Semantic extraction
                                            │
                                            ▼
                                      SemanticIR
                                            │
                            ┌───────────────┼───────────────┐
                            ▼               ▼               ▼
                          Graph           FTS5           Vectors
                       (projections — M3, not built yet)
```

---

## Quick start

```bash
git clone https://github.com/Jaiguruu/Episteme.git
cd Episteme
pip install -e .
```

`tree-sitter` and `tree-sitter-language-pack` come with it — the pack supplies
around 400 pre-compiled grammars, so there is no grammar build step.

```bash
# 1. Run the test suite (~15 s)
python tests/run_all.py

# 2. Index a repository and print what came out
python tools/demo_offline.py tests/fixtures/demo_repo

# 3. The polyglot edge-case repository — 18 grammars, deliberate malformed files
python tools/demo_offline.py tests/fixtures/edgecase_repo
```

From Python:

```python
from maat.offline import index_repository

result = index_repository("path/to/repo")   # writes <repo>/.maat/{manifest,ir}.json

print(result.version.id)                     # mv_4c0e0541d4d748b2
print(len(result.ir.symbols), len(result.ir.relationships))   # 26 42
print(result.ir.problems())                  # [] means the model is valid
```

Pass `persist=False` to index without writing anything. That is the right choice
in tests and experiments, because it cannot dirty a fixture:

```python
result = index_repository("path/to/repo", persist=False)
```

> **`pip install -e .` is the supported path.** If you have several interpreters on
> `PATH`, confirm the one you are using has tree-sitter — `maat.offline` imports it
> at module scope, so nothing runs without it.

---

## What it produces

One canonical `SemanticIR` — the source of truth from which the graph, FTS5 and
vector indexes are later projected:

| Component | Contents |
|---|---|
| `files` | every scanned file: language, content hash, parse status |
| `symbols` | modules, classes, interfaces, enums, functions, methods, fields |
| `relationships` | `CONTAINS`, `IMPORTS`, `CALLS`, `INHERITS` |
| `evidence` | the source span backing each symbol |
| `chunks` | token-bounded slices for downstream retrieval |
| `diagnostics` | parse and extraction failures, with human-readable reasons |

Persisted to `<repository>/.maat/`:

| File | Property |
|---|---|
| `ir.json` | the model — **byte-for-byte reproducible** for identical content |
| `manifest.json` | the change-detection baseline — carries a scan timestamp, so deliberately *not* reproducible |

---

## Design in one page

Full detail, including the module map and the invariants a change must not break,
is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

### Three tiers, and one rule between them

```text
Tier 1  acquisition   languages.py  snapshot.py  changes.py     files on disk
Tier 2  syntax        parser.py     queries/*.scm               tree-sitter — disposable
Tier 3  semantics     extractors/   ir_builder.py              language-neutral
```

**The rule:** no language-specific shape may cross the Tier 2 → Tier 3 boundary.
Tier 2 deals in tree-sitter node types and `.scm` queries; Tier 3 sees only
`SymbolFact`, `ImportFact`, `CallFact`, `InheritFact` and `BindingFact`.

That is what lets one extractor and one IR builder serve all 18 languages — and
what makes the parser replaceable without touching the model.

### Language support

| Tier | Count | What works |
|---|---:|---|
| **Extractable** | **18** | Full parse + symbols, imports, calls, inheritance, docstrings |
| Parse-only | 39 | Parsed and reported, but no symbols — an honest `extract.no_query` diagnostic |
| Data / config | 4 | `.ini`, `.gitignore`, `go.mod`, `requirements.txt` — parsed, never symbol sources |
| **Total registered** | **61** | `len(LANGUAGE_SPECS)` |

Extractable means exactly "has a file in `maat/offline/queries/`" — the set is
derived from the filesystem, never hard-coded. Dropping in a new `.scm` upgrades a
language with **no code change**. See
[`docs/adding-a-language.md`](docs/adding-a-language.md).

### Three mechanisms that make one engine serve 18 grammars

Grammars agree on almost nothing, so the design avoids per-language special cases
by exploiting three properties instead:

1. **Pairing by match.** Each pattern captures a declaration *and* its name
   (`@def.class` + `@name.class`) in one pattern, because the name node's parent
   is frequently not the declaration node — C nests names under
   `function_declarator`, Go uses a separate `field_identifier`.
2. **Nesting by span containment.** A declaration's parent is the innermost
   declaration whose byte range contains it. No per-language container lists.
3. **Reclassification by context.** A function whose enclosing declaration is a
   class, interface or enum becomes a `METHOD`.

### Determinism

Two runs over unchanged content produce an identical `model_digest` and an
identical `ir.json`. Enforced by sorted traversal, byte-level content hashing,
canonical JSON, a final sort over every collection, and — critically — a model
version computed from **content hashes only**, never from the parent version.
Reindexing unchanged content does not mint a new version.

### Failure is data, never an exception

Nothing in the offline path raises on bad input. Each file lands on a status
ladder — `OK` / `PARTIAL` / `FAILED` / `EMPTY` / `UNSUPPORTED` — and every
degraded file carries a human-readable reason. A file that fails to parse is
isolated: the rest of the repository stays queryable.

---

## Verified behaviour

**137 tests, all passing** (`python tests/run_all.py`, ~15 s).

| Repository | Scanned | Symbols | Relationships | Model version |
|---|---:|---:|---:|---|
| `tests/fixtures/demo_repo` | 7 files | 26 | 42 | `mv_4c0e0541d4d748b2` |
| `tests/fixtures/edgecase_repo` | 142 of 156 | 5,044 | 5,398 | `mv_72dfca7b6037c080` |

The edge-case repository exercises 18 grammars and deliberately includes malformed
files, BOM and CRLF line endings, empty files, a 197 KB single file, nesting past
Python's recursion limit, duplicate names, cyclic imports, star imports, unicode
identifiers, and a binary payload:

```text
OK 128   PARTIAL 3   FAILED 6   EMPTY 3   UNSUPPORTED 2
model is valid: no referential or structural problems
```

The 9 degraded files are isolated and named; the other 133 are unaffected.

> **On timings.** Per-repository durations are not comparable across machines or
> across cold and warm grammar caches — the edge-case figure in particular
> includes first-run grammar loading for 18 languages. Treat any single-run
> duration as indicative only.

---

## Project structure

```text
maat/core/          contracts, enums, spans, deterministic IDs, serialization
maat/offline/
  languages.py      path → grammar registry (61 languages)
  snapshot.py       traversal, ignore rules, binary sniffing
  changes.py        manifest diffing, content-hash rename detection
  parser.py         tree-sitter behind a ParserBackend protocol
  queries/          18 .scm extraction queries
  extractors/       grammar-neutral facts
  ir_builder.py     facts → SemanticIR
  pipeline.py       orchestration, incremental reuse, atomic publication
tests/              stdlib unittest — no pytest
tools/              demo harness, tree dumper, query and binding verifiers
docs/               contributor reference
```

---

## Documentation

| Document | For |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | how the system works, and why — read this first |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | setup, workflow, conventions, PR process |
| [`ROADMAP.md`](ROADMAP.md) | current status, milestones, where to contribute |
| [`SPEC.md`](SPEC.md) | the normative specification (25 stages, 131 criteria) |
| [`docs/`](docs/README.md) | full index of the reference documentation |

---

## Scope

M1 covers Stages 0–5: snapshot, change detection, parsing, extraction, and the
semantic IR.

**Deliberately not included yet:** reference resolution (every reference is emitted
as `UNRESOLVED` by design — M1 observes, it does not infer), the graph / FTS5 /
vector projections, retrieval, reasoning, and the MCP tool layer. Those are M2–M6
in [`ROADMAP.md`](ROADMAP.md).

---

## Contributing

Contributions are welcome. [`CONTRIBUTING.md`](CONTRIBUTING.md) has the workflow
and conventions, and [`ROADMAP.md`](ROADMAP.md) lists the highest-value gaps —
adding `@bind.*` patterns for the 17 languages that lack them is the most
self-contained place to start.

Participation is covered by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). For
security issues, see [`SECURITY.md`](SECURITY.md).

## License

[Apache-2.0](LICENSE).
