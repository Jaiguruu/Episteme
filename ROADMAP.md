# Roadmap

Where the project is, where it is going, and where you can help.

For the normative specification see [`SPEC.md`](SPEC.md); for design rationale see
[`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 1. Status at a glance

| | |
|---|---|
| **Current milestone** | M2 — Stage 6 not started; Stages 6–8 next |
| **Test suite** | 278 tests, all passing (`python tests/run_all.py`, ~15 s) |
| **Package version** | `0.1.0` |
| **Languages** | 61 registered · **18 extractable** · 39 parse-only · 4 data/config |
| **Next** | Stage 6 (symbol and relationship resolution), then Stages 7 and 8 |

`demo_repo` (7 files) produces 26 symbols, 42 relationships and 15 bindings;
every relationship is still `UNRESOLVED` by design, so the spec's §7 dependency
chain is not yet walkable as real `CALLS` edges. `edgecase_repo` (142 scanned
files, 18 grammars) produces 5,044 symbols and 5,398 relationships, with 9
deliberately malformed files isolated rather than fatal.

---

## 2. Milestones

The spec defines 25 stages; they are grouped into six delivery milestones. The
ordering is strict — each milestone depends on the artifacts of the previous one.

| Milestone | Stages | Theme | Status |
|---|---|---|---|
| **M1** | 0–5 | Foundations & offline parser | **done** |
| **M2** | 6–8 | Resolution & canonical model | **in progress** — not started |
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

### M2 — in progress

M2 has not started. M1 emits **every** reference as `UNRESOLVED` by design; M2
turns those into resolved edges, validates them, and gives the result a canonical
query surface.

* **Stage 6** — symbol and relationship resolution: import resolver, qualified-name
  resolver, receiver resolution, call-target resolution, ambiguity handling
* **Stage 7** — relationship validation: duplicate and orphan detection, a
  confidence policy, a machine-readable validation report
* **Stage 8** — canonical semantic model: a CRUD/query interface, version
  management, lookup by ID / qualified name / source-target-type / evidence

Stage 6 lands in a new sibling package `maat/semantic/`, so the syntax tier stays
free of meaning. It will resolve observed references through a precedence ladder
(D24), so an edge's `resolution_status` is a statement of *which fact* justified
it rather than an opaque score, and it will read only the language-neutral
model — symbols, relationships, bindings — never a grammar, so it can cover all
18 extractable languages without a per-language branch.

Section 4.2 governs it: an edge that cannot be placed stays explicitly
`UNRESOLVED`, and one with several equally plausible targets is marked `AMBIGUOUS`
with those candidates listed, never guessed.

**Two prerequisites must be settled before Stage 6 starts.** Both are described
in [`docs/decisions.md`](docs/decisions.md):

1. **Bindings captured but never persisted** — **closed**. `ir_builder` now emits
   them, `SemanticIR` carries a `bindings` collection, and incremental reuse
   buckets and re-stamps them (D34). Stage 6 has its raw material.
2. **Version identity needs a pipeline fingerprint** — **not started**. A version
   ID is currently a pure function of file content, which is correct for M1 but
   breaks in M2, because resolution changes the model *without changing any
   file* — so one content hash would map to two different models sharing a version
   ID (D27).

> Adding the `bindings` collection made the second prerequisite concrete rather
> than hypothetical: a model written before it existed and a model written after,
> over identical file content, shared a version ID while differing in content.
> `load_previous_ir` now treats a payload missing a collection as stale and
> rebuilds, which removes the silent-gap case — but the version ID itself still
> collides, so the fingerprint is still needed.

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
The others deserve the same treatment before their stage is built. See
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
