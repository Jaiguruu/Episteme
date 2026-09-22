# Roadmap

Where the project is, where it is going, and where you can help.

For the normative specification see [`SPEC.md`](SPEC.md); for design rationale see
[`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 1. Status at a glance

| | |
|---|---|
| **Current milestone** | M3 — M2 complete (Stages 6–8 done) |
| **Test suite** | 440 tests, all passing (`python tests/run_all.py`, ~15 s) |
| **Package version** | `0.1.0` |
| **Languages** | 61 registered · **18 extractable** · 39 parse-only · 4 data/config |
| **Next** | Stage 9 (graph projection) |

`demo_repo` (7 files) produces 26 symbols, 42 relationships and 15 bindings.
With Stage 6 enabled (`resolve=True`) all 42 edges are `RESOLVED_EXACT` and none
are left unresolved, so the spec's §7 dependency chain is walkable as real
`CALLS` edges; without it every reference stays `UNRESOLVED` as M1 emitted it.
`edgecase_repo` (142 scanned files, 18 grammars) produces 5,044 symbols and 5,398
relationships, with 9 deliberately malformed files isolated rather than fatal;
resolution there reports 0 validation problems.

---

## 2. Milestones

The spec defines 25 stages; they are grouped into six delivery milestones. The
ordering is strict — each milestone depends on the artifacts of the previous one.

| Milestone | Stages | Theme | Status |
|---|---|---|---|
| **M1** | 0–5 | Foundations & offline parser | **done** |
| **M2** | 6–8 | Resolution & canonical model | **done** |
| **M3** | 9–12 | Index projections (graph, FTS5, vector) | not started |
| **M4** | 13–18 | Online query pipeline | not started |
| **M5** | 19–20 | Agent layer (MCP tools, ReAct) | not started |
| **M6** | 21–24 | Invalidation, fault tolerance, CLI, end-to-end | not started |

### M1 — done

Snapshot → change detection → tree-sitter parsing → semantic extraction → IR,
with deterministic IDs, atomic publication, incremental reuse and a failure model
that isolates a broken file instead of aborting the run. Bindings are captured in
Tier 2 and persisted as the model's seventh collection, which is the raw material
Stage 6 will consume.

### M2 — done

**Stages 6 and 7 are done.** Stage 6 landed in the new sibling package
`maat/semantic/`, so the syntax tier stays free of meaning. It resolves observed
references through a precedence ladder (D24), so an edge's `resolution_status`
is a statement of *which fact* justified it rather than an opaque score, and it
reads only the language-neutral model — symbols, relationships, bindings — never
a grammar, so it covers all 18 extractable languages without a per-language
branch.

Resolution is opt-in: `index(..., resolve=True)`. Off by default, M1's output
stays reproducible bit for bit. Section 4.2 governs it — an edge that cannot be
placed stays explicitly `UNRESOLVED`, and one with several equally plausible
targets is marked `AMBIGUOUS` with a bounded candidate list, never guessed.
Measured on `demo_repo`, all 42 edges are `RESOLVED_EXACT` and none remain
unresolved; `edgecase_repo` resolves with 0 validation problems.

**Stage 7 is done too.** `maat/core/validation.py` validates a model before it
is published and writes the report to `validation.json`, alongside `ir.json` and
`manifest.json`. It aggregates `SemanticIR.problems()` rather than re-deriving
it, and adds what `problems()` does not cover: duplicate-**edge** detection, an
orphan check on `evidence.entity_id`, cross-entity `model_version` consistency,
and a machine-readable report. The severity policy is the whole of it — only a
structural defect blocks publication; unresolved and ambiguous edges are
reported as INFO and the model still publishes (D29, D37).

**Stage 8 is done, and M2 with it.** `maat/semantic/store.py` holds `ModelStore`,
which builds every index once at open: retrieval by stable ID is O(1) and a
source/target/type query is O(k), where `SemanticIR`'s own lookups are all linear
scans. Version management is an append-only `versions.jsonl`, so immutability is a
property of the *file format* rather than a convention (§19, D38). An index
directory now holds four artifacts. A prerequisite refactor moved rehydration and
the artifact names into `maat/core/serialization.py` so the store can read a model
without importing the syntax tier — and in doing so fixed a latent bug: the old
rehydration never restored `candidate_symbol_ids`, so reloading a model that had
ambiguous edges produced 62 validation problems on `edgecase_repo`.

**Both Stage 6 prerequisites are now closed** (see
[`docs/decisions.md`](docs/decisions.md)):

1. **Bindings captured but never persisted** — **closed**. `ir_builder` emits
   them, `SemanticIR` carries a `bindings` collection, and incremental reuse
   buckets and re-stamps them (D34).
2. **Version identity needs a pipeline fingerprint** — **closed**. `model_version_id`
   now takes a `pipeline_fingerprint`, and `maat/core/ids.py` carries two
   constants: `PIPELINE_FINGERPRINT` (`offline.stages=0-5;semantic=absent`) and
   `PIPELINE_FINGERPRINT_RESOLVED` (`offline.stages=0-5;semantic=stages6-8`). A
   resolved model and an unresolved one built from identical bytes now get
   different version IDs (D27), so a run that resolves cannot be served a stale
   unresolved model by reuse. The consequence: every version ID changes once, so
   an existing `.maat/` index rebuilds on first use.

### M3–M6 — not started

* **M3** graph projection, FTS5 projection, vector projection, atomic publication
  of all three as one version
* **M4** intent classification, retrieval and context, deterministic reasoning,
  small-model reasoning, answer validation, model routing and escalation
* **M5** the MCP tool layer and the ReAct agent
* **M6** incremental relationship invalidation, fault tolerance, the CLI, and
  end-to-end integration

---

## 3. Where to contribute

Ordered roughly by how self-contained the work is.

### Good first issues

| Task | Why it is approachable |
|---|---|
| **Add `@bind.*` patterns to a language** | Pure `.scm` work, no Python. See [`docs/adding-a-language.md`](docs/adding-a-language.md). |
| **Add a new extractable language** | Drop in a `.scm` file. `tools/dump_trees.py` shows you real parse trees to write against. |
| **Extend `@bind.*` patterns past Python** | Only `python.scm` carries the binding family today; the other 17 extractable languages do not. See below. |

**Binding capture is the highest-value gap.** `@bind.*` exists in **one** query
file — `python.scm`. The other 17 extractable languages have no binding patterns,
which `tools/verify_bindings.py` reports as `NEEDS PATTERNS`. Adding them is
mechanical: probe the tree, write the patterns, verify.

### Known technical debt

* **`languages.py` advertises 61 registered languages** but `registry_summary` is
  untested, and the extractable count is derived from the filesystem so it can
  drift from any number written in prose.
* **`tools/demo_offline.py --touch <file>` mutates a committed fixture** and does
  not revert it. It should copy to a temp directory first.
* **Declared-but-unused contract members**, reserved for later stages. Do **not**
  delete these without a decision: `ChangeKind`, `RECOVERY_STATEMENT`,
  `SymbolType.PARAMETER` / `VARIABLE` / `IMPORT`,
  `RelationshipType.REFERENCES` / `IMPLEMENTS`.
* **Duration figures in prose are not comparable** across machines or cold/warm
  grammar caches. Treat any single-run number as indicative only.

### Known spec weaknesses

Eight acceptance criteria cannot be falsified as written, because they constrain a
mechanism rather than an observable output, or reference a threshold that is never
fixed. The clearest example is "a usable partial tree" — the implementation made
it concrete (at least one clean top-level statement), which is why it is testable.
Stage 6's two criteria (§13 AC3 and §13 AC5) were sharpened when it was built; the
other five deserve the same treatment before their stage is built. See
[`docs/verification.md`](docs/verification.md).

---

## 4. Architectural rules that constrain every milestone

These are non-negotiable; see
[`ARCHITECTURE.md` §9](ARCHITECTURE.md#9-invariants-a-change-must-not-break).

1. No language-specific shape crosses the Tier 2 → Tier 3 boundary.
2. The semantic model is the source of truth; indexes are projections.
3. Never turn an ambiguous relationship into a confident one without evidence.
4. Failure is data, never an exception.
5. Determinism is a tested property.
6. `model_version` is never an input to an entity ID.

**The three rules from spec §41**, which the whole system is built around:

1. The LLM must not become the source of repository truth.
2. The agent must not replace deterministic repository capabilities.
3. No generated answer is trusted merely because a model generated it.

---

## 5. Getting started

```bash
pip install -e ".[dev]"
python tests/run_all.py
python tools/demo_offline.py tests/fixtures/demo_repo
```

Then read [`ARCHITECTURE.md`](ARCHITECTURE.md), and
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the workflow and conventions.
