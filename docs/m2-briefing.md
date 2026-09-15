# M2 Briefing — What to Know and Prepare Before Pairing

**For:** the project owner, before starting M2 with an AI implementation partner.
**Companions:** `docs/implementation-plan-resolution.md` (design, D23–D32),
`docs/m2-implementation-plan.md` (execution, WP1–WP8).
**Purpose:** the things you need *in your head and on your machine* before the
first pairing session — including two findings that block M2 and are not yet in
either plan.

---

## 1. What M2 actually is

M1 produced a `SemanticIR` in which **every reference is `UNRESOLVED`**, by design
(spec §4.2). M2 turns those references into resolved edges, validates them, and
gives the result a query surface.

| Stage | Input → Output | Spec |
|---|---|---|
| **6** Resolution | unresolved edges → resolved edges | §13 AC1–AC6 |
| **7** Validation | resolved IR → `ValidationReport` + publishable verdict | §14 (6 criteria) |
| **8** Canonical model | validated IR → `CanonicalModel` with lookups | §15 (6 criteria) |

**M2 is entirely offline and deterministic.** No model, no network, from any
module. That is what makes §13 AC5 ("no hallucinated relationship") a structural
property rather than a promise — worth protecting deliberately, because it is the
one milestone where it is cheap to keep.

### The single gate

```
CheckoutController → CheckoutService → PaymentService → PaymentRepository
RefundService      → PaymentService
```

That is spec §7's expected graph. **`test_expected_graph_from_section_7` passing
is the milestone.** Everything before it exists to make it possible; everything
after it assumes it passes.

---

## 2. The one fact that determines the whole milestone

**Four of the twelve `CALLS` edges in `demo_repo` cannot be resolved without type
information M1 never captured — and all four of the §7 chain edges are among
them.**

| §7 expected edge | Call site | Receiver is | Needs |
|---|---|---|---|
| `CheckoutController` → `CheckoutService` | `service.checkout(...)` | local variable | local binding |
| `CheckoutService` → `PaymentService` | `self.payment_service.process(...)` | instance field | field binding (constructed) |
| `PaymentService` → `PaymentRepository` | `self.repository.save(...)` | instance field | field binding (**from a parameter annotation**) |
| `RefundService` → `PaymentService` | `self.payment_service.process(...)` | instance field | field binding (constructed) |

`CallFact` records `receiver="self.payment_service"` as **raw text and nothing
more**. There is no type information anywhere in the M1 model.

**Why this matters for you as the owner:** the tempting shortcut — resolve
`self.x` to any symbol named `x` — produces a *confidently wrong* edge, which
§4.2 explicitly forbids and which is the exact failure mode the whole honesty
family of criteria exists to prevent. The only honest options are to capture
binding facts (D23) or to leave the §7 edges unresolved and fail the milestone.
There is no third option. This is the decision the milestone rests on.

---

## 3. Current state — more advanced than "M1 done, M2 not started"

M2 implementation **has begun**. Precisely:

| | State |
|---|---|
| M1 (Stages 1–5) | **Complete.** 137 tests passing |
| M2 design plan (D23–D32) | **Written** — `docs/implementation-plan-resolution.md` |
| M2 execution plan (WP1–WP8) | **Written** — `docs/m2-implementation-plan.md` |
| **D23 binding capture** | **Python done and verified. 17 languages remain** |
| **D27 version identity** | **Not started — still needs your call** |
| Stages 6/7/8 code | **Not started** |

### What D23 has already produced (verified in the code, not just claimed)

| Artifact | State |
|---|---|
| `BindingScope` enum (LOCAL / INSTANCE / PARAMETER) in `core/enums.py` | ✅ |
| `BindingFact` in `extractors/base.py:145` | ✅ |
| `ExtractionFacts.bindings` at `base.py:217` | ✅ |
| `@bind.*` patterns in `queries/python.scm` | ✅ **7 patterns**, 5 capture names (`@bind.assign` / `.name` / `.param` / `.receiver` / `.type`), 23 capture mentions including the doc comment |
| `@bind.*` patterns in the other 17 `.scm` files | ❌ **zero** |
| `tools/probe_bindings.py`, `tools/verify_bindings.py` | ✅ new |

All four bindings §7 needs are captured from `demo_repo`:

```text
LOCAL      service           -> CheckoutService      in CheckoutController.handle
INSTANCE   payment_service   -> PaymentService       in CheckoutService.__init__
PARAMETER  repository        -> PaymentRepository    in PaymentService.__init__
INSTANCE   repository        -> repository           in PaymentService.__init__   (2-hop)
INSTANCE   payment_service   -> PaymentService       in RefundService.__init__
```

**Note the 2-hop case.** The INSTANCE binding's `type_name` is *another name*
(`repository`), not a type. Resolving `self.repository.save` requires following
INSTANCE → PARAMETER one hop. The design plan accounts for this; keep it in mind
because it is the kind of thing that looks like a bug when it surfaces.

---

## 4. Two findings that block M2 and are not in either plan

### 4.1 The plans are internally inconsistent about where bindings live

This is the most important thing in this document.

The resolver needs `type_env_by_scope`, built from `BindingFact`s. But look at
the signatures both plans specify:

| Plan | Specifies | Problem |
|---|---|---|
| design §4 | `resolve.py` — `resolve_ir(ir) -> SemanticIR` | takes **only** an `ir` |
| design §7 data flow | `symbol_index.build_index(ir)` → "SymbolIndex + type environments (**from BindingFact**)" | receives only `ir`, must produce something derived from `BindingFact` |
| execution WP3 | `bindings.py` — `BindingFact` list → per-scope type environments | input is a `BindingFact` list |
| execution WP5 | `resolve_ir(ir) -> SemanticIR` | takes **only** an `ir` |
| execution §3 contract changes | lists `BindingScope`, `BindingFact`, `ExtractionFacts.bindings`, `INSTANCE_RECEIVER_TOKENS`, `@bind` patterns, `model_version_id`, `candidate_symbol_ids` | **`SemanticIR` gains no bindings collection** |

So: `build_index(ir)` and `resolve_ir(ir)` must build and consume type
environments from `BindingFact`s, but a `SemanticIR` contains no `BindingFact`s
and neither plan adds any. **The data has no path from the extractor to the
resolver.**

This is not hypothetical — three consequences land immediately:

1. **`resolve_ir(ir)` cannot perform a first resolution.** The design plan's own
   §12 test plan requires `resolve_ir` to be callable on a bare IR (idempotence
   test). That works on the *second* call — already-resolved edges short-circuit
   at S1 — but the first call has no type environments to consult.
2. **Incremental runs lose bindings.** `pipeline.index()` reuses an unchanged
   file's entities by carrying them forward from the previous IR
   (`_reuse`, `pipeline.py:507`). Bindings are not carried, because they are not
   in the IR. Any edge on a reused file that needs resolution cannot get it.
3. **`SemanticIR`'s own docstring becomes false.** It currently states: *"this
   object must be sufficient on its own to reconstruct them"* (the indexes).
   If bindings are required to build `type_env_by_scope` and are not in the IR,
   that claim does not hold.

**Three ways to resolve it — this is a decision you own:**

| Option | Change | Cost | Verdict |
|---|---|---|---|
| **A** | Add `bindings: list[BindingFact]` to `SemanticIR` | IR digest changes; `ir.json` grows; `BindingFact` must become a persisted contract type with `problems()` / `to_dict()` | **Recommended** — the only option that keeps §4.1 ("the semantic model is the source of truth") true |
| **B** | Keep bindings transient; `resolve_ir(ir, bindings_by_file)` | Resolution is no longer reproducible from the IR alone; `CanonicalModel.load()` cannot re-resolve; §12's `resolve_ir` tests must construct facts | Workable, but weakens the model's self-sufficiency |
| **C** | Persist bindings in a side artifact (`bindings.json`) | A second artifact to version atomically — §19 AC1/AC3, which is M3 work pulled forward | Worst of the three |

I recommend **A**, and I recommend deciding it *before* WP1c — because if bindings
become a persisted contract type, the `@bind.*` patterns for the remaining 17
languages should be written against a settled shape rather than retrofitted.

### 4.2 `load_previous_ir` aborts on a structurally corrupt `ir.json`

A defect in M1, discovered while mapping the test suite. It is recorded in
`docs/test-acceptance-matrix.md` §F1 but not in `TODO.md`, and — worse —
`docs/walkthrough-offline-parser.md:515` documents the *opposite* behaviour:

> | Corrupt previous model | `pipeline.load_previous_ir` | Treated as absent; full rebuild |

That promise holds only for **syntactically** invalid JSON. The guard
(`pipeline.py:129`) wraps `json.load`, but `_ir_from_payload(payload)` at line 145
is **outside** the `try`. Probed behaviour:

| Malformation | Result |
|---|---|
| missing required field on an entity | `KeyError: 'path'` |
| unknown enum value | `ValueError` |
| entity is not a dict | `TypeError` |
| collections are the wrong type | `TypeError` |
| `{}` | silently accepted as an empty model |

All propagate out of `index()`. Contrast `load_manifest` (`changes.py:30`), which
is defensive at every level.

**Why it matters now:** the realistic trigger is **schema drift across code
versions** — an `ir.json` written before M2 read by a build after M2. M2 is about
to change the persisted schema (§4.1 option A) *and* the version-ID function
(D27), which is precisely the scenario. It also contradicts `_ir_from_payload`'s
own docstring, which says it *should* break loudly.

Small, isolated, testable, and it belongs **before** the M2 schema changes rather
than after. This is my recommendation for the first vertical slice.

---

## 5. The two decisions you must make before pairing starts

### D23 — how far does binding capture go?

**Already partially built.** The open question is scope, not direction:

- **Narrow:** finish Python only (WP1b tests), build Stages 6/7/8 on one language,
  backfill the other 17 later. Faster feedback on the ladder; leaves a known
  coverage hole in the tree.
- **Broad:** complete all 17 remaining languages first (WP1c batches A–F), then
  build Stages 6/7/8 against 18 languages. Slower to first signal; no hole.

Note `bash` is legitimately **N/A** — shell scripts do not declare typed
variables. Document it; do not force patterns onto it.

Reversing D23 entirely still costs only one file's patterns plus the `BindingFact`
type, so it remains cheap — but the §7 graph becomes unsatisfiable if you do.

### D27 — version identity gains a pipeline fingerprint

Currently `model_version_id(file_hashes_digest)` — a pure function of file
content. That was correct for M1. **M2 breaks the premise**: resolution changes
the model *without changing any file*, so one content hash would map to two
genuinely different models (an unresolved M1 IR and a resolved M2 IR) sharing one
version ID. The version stops being a faithful identity, and §19's atomic
publication has nothing trustworthy to key on.

Proposed fix: `model_version_id(file_hashes_digest, pipeline_fingerprint)`, where
the fingerprint covers the content hashes of the `.scm` query files plus a
`RESOLUTION_POLICY_VERSION` constant.

**This also fixes a latent M1 defect:** editing `python.scm` changes the model but
*not* the version ID today. So the same content hash can already correspond to two
different models — M2 makes it certain rather than possible.

The cost is that existing version IDs change (`mv_9abbbfdfc700ea1e` and friends).
Pre-release, so no migration path is needed, but it should be noted in the
walkthrough.

**Ask for the concrete failure case walked through if you want it before
deciding** — that is a reasonable thing to require, and it is cheap.

---

## 6. Spec gaps that will bite during M2

From `docs/acceptance-criteria-explained.md` Part VI, filtered to the criteria M2
has to satisfy:

| Criterion | Problem | What to settle before coding |
|---|---|---|
| **§13 AC3** ambiguous resolution | "Ambiguous" is **undefined** — it is a policy decision, not a fact | Define the predicate. The plan implies ">1 candidate at the same rung", but that is not written down as the rule |
| **§13 AC5** no hallucinated relationship | Constrains a *mechanism*, not an output — not directly observable | Agree the testable proxy up front: every relationship carries evidence (§13 AC6), confidence matches status, and `maat/semantic/` imports no model |
| **§13 AC2** namespace separation | Clear as written, but the *ladder* can break it — S7 ("unique repository-wide name") is exactly the rung that would merge two `Shared` classes | Assert the expected *strategy* per fixture edge, not just the expected target |
| **§9 AC5** rename | Already bit in M1 — satisfied vacuously because symbol IDs are path-derived | Not M2's problem, but note that M2 adds a *second* reason to schedule a rename: resolved edges are path-dependent |
| **§16 AC3** depth N | N never fixed in the spec | M3's problem — but the ladder's determinism guarantees are what make a bounded traversal well-defined, so keep candidate lists sorted |

**§13 AC3 is the one to settle first.** Everything in WP4 (the ladder) and WP5
(ambiguity handling) depends on where the ambiguity line is drawn, and the design
plan's §5 confidence table is the part most worth arguing about.

---

## 7. What to prepare

### Environment

```bash
# tree-sitter is NOT installed by default; the offline package imports it at
# module scope, so nothing runs without it.
pip install tree-sitter tree-sitter-language-pack

# Baseline: must print 137 tests and PASS
python tests/run_all.py
```

Verified working interpreter in this environment:

```text
C:/Users/MOTOROLA/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe
```

The bare `python` on `PATH` lacks tree-sitter. Confirm the partner uses a working
interpreter **before** trusting any "tests pass" claim.

### Baseline to record before touching anything

| Fact | Value |
|---|---|
| Tests | 137, PASS |
| `demo_repo` | 7 files, 26 symbols, 42 relationships (12 CALLS / 19 CONTAINS / 11 IMPORTS), 26 evidence, 34 chunks |
| `demo_repo` version | `mv_9abbbfdfc700ea1e` (will change under D27 — expect it) |
| `edgecase_repo` | 142 scanned, 5,044 symbols, 5,398 relationships, 18 languages, 23 diagnostics |
| Status mix | 128 OK / 3 PARTIAL / 6 FAILED / 3 EMPTY / 2 UNSUPPORTED |
| Excluded | 14 (10 IGNORED + 3 GENERATED + 1 BINARY); 142 + 14 = 156 |

Write these down. D27 changes the version ID, and WP1c touches 17 query files —
you want to be able to tell a real regression from an expected change.

### Oracles to have open

1. **Spec §7 expected graph** — the milestone gate. Five edges.
2. **`demo_repo` resolves completely** — 42/42 EXACT. A second, independent
   oracle: if the graph passes but this does not, something is resolving
   *accidentally*.
3. **The negative cases** — `_edge/star_import.py` and `_edge/dynamic_dispatch.py`
   must stay `UNRESOLVED`. **These are as important as the positive ones.** A
   resolver that resolves everything is worse than one that resolves nothing,
   and only the negative oracles catch it.

### Tooling

| Tool | Use |
|---|---|
| `tools/probe_bindings.py` | Dump a grammar's real node shapes for the four binding constructs |
| `tools/verify_bindings.py` | Per-language coverage; reports `NEEDS PATTERNS` |
| `tools/dump_trees.py` | Cross-language tree dumps |
| `tools/verify_queries.py` | Query-file sanity |
| `tools/demo_offline.py` | End-to-end pipeline demo |
| `tests/run_all.py` | Suite runner |

**The per-language loop is: probe → write patterns → verify → repeat.** Never
guess a grammar node name. That is the M1 lesson that cost the most time, and it
is the top-ranked risk in both M2 plans.

### Housekeeping worth doing first

- [ ] **`git init` and make the baseline commit.** `git rev-parse` currently
      fails. M2 touches 17 query files, a core contract, and the version-ID
      function; without version control, a bad batch of patterns is not
      recoverable. **This is the single highest-value preparation step.**
- [ ] Remove `tests/fixtures/demo_repo/.maat/` (stale index dir inside a fixture).
- [ ] Confirm the 137-test baseline passes on your machine, not just in the docs.

---

## 8. How to judge the partner's work

M2 has an unusually high ratio of *plausible-looking wrong answers* to obviously
wrong ones. Specific things to watch for:

| Symptom | Why it is wrong |
|---|---|
| "All tests pass" without showing the command and its output | The count and the PASS line are the evidence; the claim is not |
| A resolution result with no recorded *strategy* | The ladder's whole value is that the status *is* the explanation. Without the winning rung recorded, "why did this resolve to X?" is unanswerable |
| `demo_repo` resolves 42/42 but `star_import` also resolves | Over-resolving. The negative oracles exist precisely to catch this |
| Grammar node names written without running `probe_bindings.py` | Fails silently as zero captures — the worst kind of failure, because the pattern looks correct |
| Ambiguity "resolved" to the first candidate | Directly violates §13 AC3. The first candidate is an arbitrary target |
| `target_name` cleared on resolution | Renumbers every relationship ID (it is keyed on `target_name`), making a resolved model look unrelated to the change detector |
| A reordered ladder presented as a refactor | S6/S7 order changes what counts as ambiguous — it is a semantic change and needs a decision |
| Confidence computed rather than declared | §12's invariants (`EXACT ⇒ 1.0`, `UNRESOLVED ⇒ 0.0`) must hold by construction, not by hoping a formula lands right |

### Two things to require explicitly

1. **Probe before pattern.** For each of the 17 remaining languages, the partner
   must show `probe_bindings.py` output for the actual grammar before writing
   `.scm` patterns.
2. **Strategy assertions, not just target assertions.** Every ladder test should
   assert *which rung* fired, including — especially — the tests where a rung must
   **decline**. A strategy that answers when it should decline is the failure mode
   that matters in WP4.

---

## 9. The milestone gate, restated as a checklist

- [ ] `tools/verify_bindings.py` reports no language needing patterns (`bash` N/A, documented)
- [ ] `test_expected_graph_from_section_7` passes — **the gate**
- [ ] `demo_repo` resolves 42/42 EXACT
- [ ] `star_import` and `dynamic_dispatch` stay `UNRESOLVED`
- [ ] Resolution is deterministic and idempotent; relationship IDs unchanged by resolution
- [ ] Validation rejects an invalid model, machine-readably
- [ ] `CanonicalModel` round-trips through persistence with a matching digest
- [ ] M1's 137 tests still pass
- [ ] Edge-case repo: 18 languages, degraded files still isolated, model valid
- [ ] Docs and `TODO.md` updated

---

## 10. Suggested first three sessions

Deliberately small, each ending in a verifiable checkpoint:

1. **Session 1 — decide, don't build.** Settle §4.1 (where bindings live: A/B/C),
   §13 AC3 (the ambiguity predicate), and D27. Run `git init` and commit the
   baseline. No code.
2. **Session 2 — the `ir.json` loader defect** (§4.2). Small, isolated, has no
   test today, and it must land before M2 changes the persisted schema. This is
   the ideal first vertical slice: it exercises the whole pairing loop on
   something low-risk.
3. **Session 3 — WP1b + WP1c batch A** (javascript, typescript, tsx). Closes the
   dead `BindingScope` import in `test_extractor.py` and proves the
   probe → pattern → verify loop before committing to the other twelve languages.

Then WP2 (D27) in isolation, and only then the `maat/semantic/` package.

**Do not start WP3–WP5 until §4.1 is decided.** Building the lookup substrate
against an unsettled binding shape means writing `bindings.py` twice.
