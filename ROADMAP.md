# Roadmap

Where the project is, where it is going, and where you can help.

For the normative specification see [`SPEC.md`](SPEC.md); for design rationale see
[`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 1. Status at a glance

| | |
|---|---|
| **Current milestone** | M1 — complete and verified |
| **Test suite** | 137 tests, all passing (`python tests/run_all.py`, ~15 s) |
| **Package version** | `0.1.0` |
| **Languages** | 61 registered · **18 extractable** · 39 parse-only · 4 data/config |
| **Next milestone** | M2 — resolution, validation, canonical model |

`demo_repo` (7 files) produces 26 symbols and 42 relationships.
`edgecase_repo` (156 files, 18 grammars) produces 5,044 symbols and 5,398
relationships, with 9 deliberately malformed files isolated rather than fatal.

---

## 2. Milestones

The spec defines 25 stages; they are grouped into six delivery milestones. The
ordering is strict — each milestone depends on the artifacts of the previous one.

| Milestone | Stages | Theme | Status |
|---|---|---|---|
| **M1** | 0–5 | Foundations & offline parser | **done** |
| **M2** | 6–8 | Resolution & canonical model | **next** |
| **M3** | 9–12 | Index projections (graph, FTS5, vector) | not started |
| **M4** | 13–18 | Online query pipeline | not started |
| **M5** | 19–20 | Agent layer (MCP tools, ReAct) | not started |
| **M6** | 21–24 | Invalidation, fault tolerance, CLI, end-to-end | not started |

### M1 — done

Snapshot → change detection → tree-sitter parsing → semantic extraction → IR,
with deterministic IDs, atomic publication, incremental reuse and a failure model
that isolates a broken file instead of aborting the run.

### M2 — next

Stages 6, 7 and 8. M1 emits **every** reference as `UNRESOLVED` by design; M2
turns those into resolved edges, validates them, and gives the result a canonical
query surface.

* **Stage 6** — symbol and relationship resolution: import resolver, qualified-name
  resolver, receiver resolution, call-target resolution, ambiguity handling
* **Stage 7** — relationship validation: duplicate and orphan detection, a
  confidence policy, a machine-readable validation report
* **Stage 8** — canonical semantic model: a CRUD/query interface, version
  management, lookup by ID / qualified name / source-target-type / evidence

It lands in a new sibling package `maat/semantic/`, so the syntax tier stays free
of meaning.

**Two prerequisites are known and must be settled before Stage 6 starts.** Both
are described in [`docs/decisions.md`](docs/decisions.md):

1. **Bindings are captured but never persisted.** `BindingFact` exists and the
   extractor produces it, but `ir_builder` never reads `facts.bindings`,
   `SemanticIR` has no collection for them, and incremental reuse does not carry
   them. Without this path, Stage 6 cannot resolve a single member call.
2. **Version identity needs a pipeline fingerprint.** `model_version_id` is
   currently a pure function of file content. That is correct for M1 but breaks in
   M2, because resolution changes the model *without changing any file* — so one
   content hash would map to two different models sharing a version ID.

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
| **Add tests for `maat/core/`** | 1,161 lines of contracts currently covered only indirectly through `tests/offline/`. |

**Binding capture is the highest-value gap.** `@bind.*` exists in **one** query
file — `python.scm`. The other 17 extractable languages have no binding patterns,
which `tools/verify_bindings.py` reports as `NEEDS PATTERNS`. Adding them is
mechanical: probe the tree, write the patterns, verify.

### Known technical debt

* **`maat/core/` has no dedicated test module.** Verified-untested: `combine_hashes`
  order-independence, `_StrEnum.__str__`, `FileRecord.problems()` path validation
  (POSIX-only, repo-relative — and this project is developed on Windows),
  `SourceSpan.whole_file` / `point` / `is_zero_width` / `contains_line`.
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
