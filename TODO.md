# TODO — MAAT Repository Intelligence Agent

**Source spec:** [`Problem_doc.md`](Problem_doc.md) — v1.0, 41 sections, 25 implementation stages
**Current state:** **M1 complete and verified.** M2 plan written; blocked on two decisions (D23, D27) — see §4.

**Legend:** `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked

> **History note — read this before trusting an older copy of this file.**
> Earlier revisions described M1 as a hand-written lexer + recursive-descent parser
> (`lexer.py`, `ast_nodes.py`, `HandwrittenParser`, `python_extractor.py`).
> **None of those files were ever built.** Mid-M1 the approach changed to
> **tree-sitter with pre-compiled grammars + declarative `.scm` queries**, and the
> implementation plan was rewritten to revision 2. This file now describes what
> actually shipped, so it can be trusted as a task list again.

---

## 1. Milestone Map

The spec's 25 stages are grouped into six delivery milestones. Milestones are strictly
ordered — each depends on the artifacts of the previous one, matching §37
"Implementation Order".

| Milestone | Stages | Theme | Status | Exit condition |
|---|---|---|---|---|
| **M1** | 0–5 | Foundations & Offline Parser | **DONE** | Semantic IR produced from `demo_repo`; broken file isolated |
| **M2** | 6–8 | Resolution & Canonical Model | **PLANNED, BLOCKED** | Versioned, validated, queryable semantic model |
| **M3** | 9–12 | Index Projections | Not started | Graph + FTS5 + Vector published atomically as one version |
| **M4** | 13–18 | Online Query Pipeline | Not started | E001–E004 answered with evidence, no LLM for deterministic queries |
| **M5** | 19–20 | Agent Layer | Not started | E005 multi-step trace with per-transition evidence |
| **M6** | 21–24 | Incremental, Fault Tolerance, CLI, E2E | Not started | §33 quality gates all pass |

---

## 2. M1 — Foundations & Offline Parser (COMPLETE)

Plan: [`docs/implementation-plan-offline-parser.md`](docs/implementation-plan-offline-parser.md)
Walkthrough: [`docs/walkthrough-offline-parser.md`](docs/walkthrough-offline-parser.md)
Fast tour: [`docs/m1-tour.md`](docs/m1-tour.md)

### M1.0 — Contracts (Stage 0) — DONE
- [x] `maat/core/enums.py` — `ParseStatus`, `SymbolType`, `RelationshipType`, `ResolutionStatus`, `FileKind`, `VersionStatus`, `DiagnosticSeverity`, `BindingScope`
- [x] `maat/core/locations.py` — `SourceSpan` (line 1-based, column 0-based, end exclusive)
- [x] `maat/core/contracts.py` — `FileRecord`, `Symbol`, `Relationship`, `Evidence`, `SemanticChunk`, `ModelVersion`, `SemanticIR`, `ChangeSet`, `RepositorySnapshot`, `Diagnostic`, `ExcludedFile`
- [x] `maat/core/ids.py` — content-addressed stable IDs
- [x] `maat/core/serialization.py` — canonical JSON + atomic writes
- [x] `tests/fixtures/demo_repo/` — 7 files including one intentionally broken
- [x] `tests/fixtures/edgecase_repo/` — 156 files, 18 grammars, deliberate edge cases

**Superseded (do not build):** `tests/fixtures/expected_graph.py` and
`tests/fixtures/contracts.md` were planned as separate fixture files. The expected
symbol/relationship set lives inside `tests/offline/test_pipeline.py` instead, where it
is asserted directly. The contracts are documented in module docstrings rather than a
separate prose file.

### M1.1 — Repository snapshot (Stage 1) — DONE
- [x] `maat/offline/languages.py` — 61-language registry (extension + exact filename)
- [x] `maat/offline/snapshot.py` — sorted walk, ignore rules, binary sniff, generated detection
- [x] Byte-level `sha256` content hashing
- [x] `FileRecord` manifest with stable ordering; exclusions recorded with a reason
- [x] AC1–AC5 covered by `tests/offline/test_snapshot.py` (16 tests)

### M1.2 — Change detection (Stage 2) — DONE
- [x] `maat/offline/changes.py` — manifest diff → `NEW / CHANGED / DELETED / UNCHANGED`
- [x] Content-hash rename detection (byte-identical only; no similarity heuristic)
- [x] `ChangeSet` with incremental statistics
- [x] AC1–AC6 covered by `tests/offline/test_changes.py` (19 tests)

### M1.3 / M1.4 — Lexer + Parser (Stage 3) — DONE, **approach changed**
- [x] ~~`maat/offline/lexer.py` — indentation-aware tokenizer~~ **NOT BUILT — superseded**
- [x] ~~`maat/offline/ast_nodes.py` — AST node dataclasses~~ **NOT BUILT — superseded**
- [x] `maat/offline/parser.py` — tree-sitter behind a `ParserBackend` protocol
- [x] Status ladder `OK / PARTIAL / FAILED / EMPTY / UNSUPPORTED`; never raises
- [x] Statement-level error tolerance via tree-sitter `ERROR` / `MISSING` node classification
- [x] AC1–AC6 covered by `tests/offline/test_parser.py` (20 tests)

The `ParserBackend` seam was kept, as §10 requires. `TreeSitterParser` is the only
implementation. A hand-written zero-dependency backend remains possible but is no longer
planned work.

### M1.5 — Extractors & Semantic IR (Stages 4–5) — DONE
- [x] `maat/offline/extractors/base.py` — `Extractor` protocol + the fact vocabulary
- [x] `maat/offline/extractors/query_extractor.py` — one extractor for all 18 languages
- [x] `maat/offline/queries/*.scm` — 18 declarative extraction queries
- [x] `maat/offline/ir_builder.py` — facts → validated `Symbol` / `Relationship` / `Evidence` / `SemanticChunk`
- [x] Documentation (docstring / doc-comment) extraction
- [x] Candidate call relationships for the fixture chain
- [x] AC1–AC3 covered by `tests/offline/test_extractor.py` (16) and `test_ir.py` (31)

**Superseded:** `extractors/python_extractor.py` was never built. One query-driven
extractor serves every language; a language is added by dropping in a `.scm` file.

### M1.6 — Milestone verification — DONE
- [x] `maat/offline/pipeline.py` — snapshot → changes → parse → extract → IR, one call
- [x] End-to-end M1 test over `demo_repo`
- [x] Fault-injection: broken file yields `PARTIAL`/`FAILED`, other files unaffected
- [x] Determinism: two runs produce byte-identical IR
- [x] `docs/walkthrough-offline-parser.md` — code walkthrough with a 12-bug record

### M1 verified behaviour (re-measured, not copied from docs)

**137 tests pass** — `python tests/run_all.py`

| Repository | Scanned | Symbols | Relationships | Chunks | Notes |
|---|---|---|---|---|---|
| `demo_repo` | 7 | 26 | 42 | 34 | 82 ms · `mv_9abbbfdfc700ea1e` · 6 OK + 1 PARTIAL |
| `edgecase_repo` | 142 of 156 | 5,044 | 5,398 | — | 18 grammars · 128 OK / 3 PARTIAL / 6 FAILED / 3 EMPTY / 2 UNSUPPORTED · 23 diagnostics · model valid |

Breakdowns worth knowing:
- `demo_repo` symbols: 7 `MODULE` + 7 `CLASS` + 12 `METHOD`
- `demo_repo` relationships: 12 `CALLS` + 19 `CONTAINS` + 11 `IMPORTS`
- `demo_repo` chunks: 7 module + 7 class + 12 method + 7 imports + **1 `parse_error`**
- `edgecase_repo` exclusions: 10 `IGNORED` + 3 `GENERATED` + 1 `BINARY`
- Every `Evidence` row carries `retrieval_source="offline.ast"`

Incremental behaviour (verified on a temp copy, fixture untouched):

```text
run 1  (cold)        parsed 7   reused 0   version mv_9abb…  (no new version)
run 2  (no change)   parsed 0   reused 7   same version
run 3  (touch 1)     parsed 1   reused 6   changed 1, version changed, parent mv_9abb…
run 4  (no change)   parsed 0   reused 7   same version as run 3
```

---

## 3. What M1 established (the invariants M2 must not break)

1. **Three tiers, one rule.** No language-specific shape may cross the Tier 2 → Tier 3
   boundary. Tier 3 sees only `SymbolFact` / `ImportFact` / `CallFact` / `InheritFact` /
   `BindingFact`. This is why 18 languages cost one extractor.
2. **M1 observes; it does not infer.** Only `CONTAINS` is `RESOLVED_EXACT`. Every
   `IMPORTS` / `CALLS` / `INHERITS` edge is `UNRESOLVED` with confidence `0.0` and an
   `unresolved:` placeholder target, with the raw text kept in `target_name`.
3. **IDs are content-addressed and version-free.** `sha1(path, type, qualified_name)`,
   16 hex, `\x1f`-joined. `model_version` is deliberately not an input — otherwise an
   unchanged symbol would get a new ID on every reindex and reuse would be impossible.
4. **Failure is data, never an exception.** Nothing in the offline path raises on bad
   input; every degraded file carries a machine-readable reason.
5. **Determinism is a tested property**, not an aspiration. Two runs produce a
   byte-identical `ir.json`.
6. **The model is the source of truth.** Graph / FTS5 / vector stores are projections.
   No index may become authoritative.

---

## 4. M2 — Resolution & Canonical Model (ACTIVE, BLOCKED)

Plan: [`docs/implementation-plan-resolution.md`](docs/implementation-plan-resolution.md)

- [ ] **Stage 6** Symbol & relationship resolution — import resolver, qualified-name
      resolver, receiver resolution, call-target resolution, ambiguity handling,
      confidence; states `RESOLVED_EXACT / RESOLVED_HEURISTIC / AMBIGUOUS / UNRESOLVED`
- [ ] **Stage 7** Relationship validation — duplicate detector, orphan detector,
      confidence policy, machine-readable validation report
- [ ] **Stage 8** Canonical semantic model — CRUD/query interface, version management,
      lookup by ID / qualified name / source-target-type / evidence

### Blocking decisions

- [!] **D23 — consume and persist `BindingFact`.**
  The **capture half is already done**: `BindingFact` exists in `extractors/base.py`, all
  18 `.scm` files emit `@bind.*`, and `query_extractor.py` produces them. Verified live —
  `services/payment_service.py` yields 4 bindings:

  ```text
  {bound_name: "repository", type_name: "PaymentRepository", scope: PARAMETER}
  {bound_name: "repository", type_name: "repository",       scope: INSTANCE}
  {bound_name: "payment",    type_name: "Payment",          scope: PARAMETER}  (×2)
  ```

  Note the INSTANCE binding's `type_name` is *another name*, not a type — resolving
  `self.repository.save` requires following INSTANCE → PARAMETER one hop.

  The **missing half** is everything downstream, and it is larger than it looks:
  - `ir_builder.build_file_ir()` never reads `facts.bindings`. Bindings are silently
    dropped at the Tier 3 boundary.
  - `SemanticIR` has no collection for bindings, so there is nowhere to persist them.
  - `pipeline._group_by_file()` does not bucket bindings, so incremental reuse would
    lose them even once they exist.

  Consequence: **bindings do not survive into `ir.json`.** M2 Stage 6 cannot resolve a
  single member call until this path exists. This is the first real task of M2, and it
  touches the persisted schema, so it must be decided before Stage 6 begins.

  4 of the 12 `demo_repo` `CALLS` edges need this; 3 of those 4 are in the spec's own §7
  expected chain.
- [!] **D27 — version identity must gain a pipeline fingerprint.**
  `model_version_id` is currently a pure function of file content. That was correct for
  M1 but breaks in M2: resolution changes the model *without changing any file*, so one
  content hash would map to two different models sharing a version ID. Fix:
  `model_version_id(file_hashes_digest, pipeline_fingerprint)` where the fingerprint
  covers the content hashes of the `.scm` query files plus a
  `RESOLUTION_POLICY_VERSION` constant.

### Planned architecture
New `maat/semantic/` package — a sibling of `offline/`, not inside it:
`names.py`, `bindings.py`, `symbol_index.py`, `strategies.py`, `resolve.py`,
`validation.py`, `canonical.py`.

### Other decisions already taken
D24 resolution is a precedence ladder (S1–S9), not a score, so the status *is* the
explanation. D25 `target_name` is retained forever — `relationship_id` is keyed on it, so
clearing it would renumber every resolved edge. D26 `candidate_symbol_ids` on
`Relationship` for `AMBIGUOUS`. D28 ambiguous edges keep the `unresolved:` placeholder.
D29 unresolved edges are reported as `info`, never failed.

---

## 5. Full Stage Roadmap (M3–M6)

### M3 — Index Projections
- [ ] **Stage 9** Graph projection — node/edge creation, `find_callers`, `find_callees`, direct dependency, transitive traversal, cycle detection (AC1–AC5)
- [ ] **Stage 10** FTS5 projection — symbol/path/doc indexing, search API, ranking; exact / qualified / partial / path / doc search
- [ ] **Stage 11** Vector projection — chunking strategy, embedding interface, similarity retrieval, metadata + version filtering
- [ ] **Stage 12** Atomic index publication — version manager, validation gate, atomic active-version pointer, rollback (AC1–AC4)

### M4 — Online Query Pipeline
- [ ] **Stage 13** Intent classifier — 7-intent taxonomy, `QueryIntent` contract, confidence, routing, ambiguity handling
- [ ] **Stage 14** Retrieval & context engine — retrieval planner, 3 retrievers, normalize, dedupe, rank, expand, compress, token budget (AC1–AC6)
- [ ] **Stage 15** Deterministic reasoning — query handlers, traversal ops, symbol lookup, result formatter, evidence attachment (AC1–AC5)
- [ ] **Stage 16** Small-model reasoning — model interface, structured prompt, evidence-aware generation, failure handling
- [ ] **Stage 17** Answer validation — claim extractor, evidence matcher, grounding/citation/completeness validators, `ValidationResult` (AC1–AC5)
- [ ] **Stage 18** Model router & escalation — strategy selector, escalation + retry policy, failure classification, cost/latency instrumentation (AC1–AC5)

### M5 — Agent Layer
- [ ] **Stage 19** MCP tool layer — `search_symbol`, `search_code`, `find_callers`, `find_callees`, `trace_dependencies`, `get_file`; tool contracts, error contracts, evidence-preserving responses (AC1–AC7)
- [ ] **Stage 20** ReAct agent — state machine, ReAct loop, observation handling, evidence accumulation, loop detection, iteration limits, token budget, termination (AC1–AC8)

### M6 — Hardening & Delivery
- [ ] **Stage 21** Incremental relationship invalidation — dependency-aware invalidation, re-resolution queue, stale detection, minimal recomputation planner (AC1–AC6)
- [ ] **Stage 22** Fault tolerance — file-level isolation, parse quarantine, degraded-state metadata, recovery on reindex (AC1–AC5)
- [ ] **Stage 23** API / CLI — `maat index`, `maat query`, `maat status`, `maat inspect`, JSON output mode (AC1–AC4)
- [ ] **Stage 24** End-to-end integration — full pipeline, integration suite, demo script, metrics, failure demonstrations (E001–E005)

---

## 6. Known technical debt and open issues

### Blocking or high-value
- [ ] **Bindings are extracted but never persisted.** `ir_builder.py` does not read
      `facts.bindings`, `SemanticIR` has no collection for them, and `_group_by_file()`
      does not bucket them. See §4 D23 — this is the first task of M2.
- [ ] **D27 — editing a `.scm` changes the model but not the version.** A latent M1
      defect. Fixing it is part of M2 (see §4).
- [ ] **`maat/core/` has no dedicated test module.** 1,161 lines covered only
      indirectly through `tests/offline/`. Grep-verified untested invariants:
      `combine_hashes` order-independence, `_StrEnum.__str__` returning the bare value,
      `FileRecord.problems()` path validation (POSIX-only, repo-relative — the
      cross-platform guard, and this project is developed on Windows),
      `SourceSpan.whole_file` / `point` / `is_zero_width` / `contains_line`, and the
      absence of derived relationship types (`DEPENDS_ON`, `TRANSITIVELY_DEPENDS_ON`,
      `IMPACTED_BY`, `REACHABLE_FROM`) from `RelationshipType`.
- [ ] **No git repository initialised.** `git rev-parse` fails at the project root.

### Documentation drift
- [ ] `docs/walkthrough-offline-parser.md` §3 records `max_depth=7` for
      `services/payment_service.py`; measured **9**. Probably a grammar-version
      difference — confirm which version produced 7 before editing the doc.
- [ ] `docs/walkthrough-offline-parser.md` §7 bug 4 states the `edgecase_repo` tally
      reconciles as "142 scanned + 13 exclusion entries (5 directories + 8 files)".
      Measured: **14** exclusion entries (`10 IGNORED` + `3 GENERATED` + `1 BINARY`),
      which reconciles as 142 + 14 = 156. The doc's tally is off by one.
- [ ] `docs/walkthrough-offline-parser.md` §2 lists `ir_builder.py` as 483 lines and
      `contracts.py` as 654; re-check if the line counts matter.
- [ ] `docs/m1-tour.md` §5 decision 5 and §3 both state the relationship ID keys on the
      raw target text — accurate — but neither notes that `_relationship()` falls back to
      `target_symbol_id` when `target_name` is `None`.
- [ ] Durations in the docs (`demo_repo` 111 ms, `edgecase_repo` 497 ms) are not
      comparable across machines or cold/warm grammar caches. Measured here: 82 ms and
      4,457 ms — the edge-case figure includes first-run grammar loading for 18 languages.
      Treat any single-run duration as indicative only.

### Housekeeping
- [ ] `tests/fixtures/demo_repo/.maat/` is a leftover index directory from an earlier
      `demo_offline.py` run. Harmless (correctly pruned as `IGNORED`) but it is stale
      state inside a fixture and should not be committed.
- [ ] `tools/demo_offline.py --touch <file>` dirties a fixture file and does not revert
      it. Prefer copying to a temp dir first, or strip the appended comment afterwards.
- [ ] Declared-but-unused contract members, reserved for later stages — do **not**
      delete without a decision: `ChangeKind`, `RECOVERY_STATEMENT`,
      `SymbolType.PARAMETER` / `VARIABLE` / `IMPORT`,
      `RelationshipType.REFERENCES` / `IMPLEMENTS`.
- [ ] `languages.py` advertises 61 registered languages but `registry_summary` is
      untested; the extractable count is derived from the filesystem and can drift from
      the README's stated split (18 extractable + 39 parse-only + 4 data/config).

---

## 7. How to run this project

```bash
# Dependencies. NOTE: tree-sitter is not installed by default and the offline
# package imports it at module scope — nothing runs without it.
pip install tree-sitter tree-sitter-language-pack

# Full suite (~12 s). Must print 137 tests and PASS.
python tests/run_all.py
python tests/run_all.py -v            # verbose
python tests/run_all.py offline       # only tests matching a pattern

# Index a repository and print what came out
python tools/demo_offline.py tests/fixtures/demo_repo
python tools/demo_offline.py tests/fixtures/edgecase_repo

# Watch incremental reindexing (WARNING: mutates the fixture file — see §6)
python tools/demo_offline.py tests/fixtures/demo_repo --touch services/payment_service.py
```

From Python:

```python
from maat.offline import index_repository

result = index_repository("path/to/repo")   # writes <repo>/.maat/{manifest,ir}.json
print(result.version.id)                     # mv_9abbbfdfc700ea1e
print(result.ir.problems())                  # [] means the model is valid
```

Pass `persist=False` to index without writing anything — the right choice in tests and
experiments, because it cannot dirty a fixture.

### Conventions
- **Tests:** stdlib `unittest` only. **No pytest.** Discovered by `tests/run_all.py` with
  `start_dir=tests`, `pattern="test_*.py"`, `top_level_dir=PROJECT_ROOT`. A new
  `tests/<pkg>/` directory needs its own `__init__.py` to be importable.
- **Test fixtures:** use `tests/support.py` — `TempRepository` (a disposable copy that
  never touches the committed fixture) or `temp_repo(files)` for a synthetic repo from an
  explicit file map. Bytes values are written verbatim, which matters for NUL/BOM/CRLF cases.
- **Adding a language:** drop `<grammar-key>.scm` into `maat/offline/queries/`. Zero
  Python changes. `extractable_languages()` discovers it from the filesystem.
- **Validation never raises.** New entities expose `problems() -> list[str]`; they do not
  throw on invalid input.
- **Style:** `from __future__ import annotations`; dataclasses for data; module
  docstrings explain *why*, and cite the spec section each rule serves.

---

## 8. Cross-Cutting Tracks (apply to every milestone)

### Edge-case matrix (§36)
- [x] **Parser** — empty file, malformed syntax, partial AST, unsupported language, large file, generated file
- [ ] **Resolution** — same symbol name, ambiguous receiver, overloaded method, alias import, missing import, dynamic dispatch, unknown symbol *(M2)*
- [x] **Incremental** — new, modified, deleted, renamed, unchanged, interrupted update
- [ ] **Incremental** — changed dependency target, stale cache *(M6 / Stage 21)*
- [x] **Semantic model** — duplicate symbol (overloads), duplicate relationship, orphan relationship, invalid location, mixed versions
- [ ] **Retrieval** — exact / partial / no result / ambiguous / conflicting / stale *(M3–M4)*
- [ ] **Reasoning** — unsupported claim, missing evidence, wrong answer type, incomplete answer, model timeout, model unavailable *(M4)*
- [ ] **Agent** — tool failure, repeated tool, cycle, no progress, max iterations, token exhaustion, missing evidence *(M5)*

### Critical failure conditions (§34) — must never silently succeed
- [ ] LLM unavailable → deterministic queries continue working *(M4)*
- [ ] Small model fails validation → escalate *(M4)*
- [ ] Complex model fails → return insufficient evidence *(M4)*
- [x] Broken file → repository remains queryable
- [x] Unknown symbol → do not hallucinate
- [ ] Ambiguous relationship → mark ambiguous *(M2; `AMBIGUOUS` exists in the enum but nothing emits it yet)*
- [ ] Agent loop → terminate *(M5)*
- [ ] Tool failure → structured failure *(M5)*
- [x] Mixed index versions → never expose as one state
- [x] Missing evidence → do not claim certainty
- [x] Deleted symbol → remove stale active relationships
- [x] Failed indexing → keep previous valid version active

### Quality gates (§33)
- [ ] All 26 gates pass — see §33 of the spec for the full checklist

### Architectural invariants (§41) — the three rules
- [x] **Rule 1** — the LLM must not become the source of repository truth *(structurally: the offline path contains no model call)*
- [ ] **Rule 2** — the agent must not replace deterministic repository capabilities *(M4–M5)*
- [x] **Rule 3** — no generated answer is trusted merely because a model generated it *(evidence is eager; entities without provenance are rejected)*

---

## 9. Definition of Done

MAAT is complete for the prototype when a single workflow runs end-to-end (§40) **and**
the test suite proves: correctness, incremental updates, fault isolation, retrieval
correctness, context control, model escalation, answer grounding, evidence provenance,
agent termination, version consistency.
