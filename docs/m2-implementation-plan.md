# M2 Implementation Plan — work breakdown

**Milestone:** M2 — Stages 6, 7, 8
**Companion to:** `docs/implementation-plan-resolution.md` (the *design* plan:
architecture, ladder, tradeoffs, decision log D23–D32). This document is the
*execution* plan: what gets built, in what order, and how each step is verified.

---

## 0. Where we are right now

| | State |
|---|---|
| M1 (Stages 1–5) | **Complete.** 137 tests passing, deterministic, ~5,000 symbols on the polyglot fixture |
| M2 design plan | **Written** — `docs/implementation-plan-resolution.md` |
| M2 implementation | **Started** — D23 only, Python only |
| D23 (binding capture) | Python done and verified. **16 languages remain** |
| D27 (version identity) | **Not started** — still needs your call |
| Stages 6, 7, 8 code | **Not started** |

### What D23 has already produced

| File | Change | Verified |
|---|---|---|
| `maat/core/enums.py` | `BindingScope` (LOCAL / INSTANCE / PARAMETER) | ✅ |
| `maat/offline/extractors/base.py` | `BindingFact`, `INSTANCE_RECEIVER_TOKENS`, `ExtractionFacts.bindings` | ✅ |
| `maat/offline/queries/python.scm` | 7 `@bind.*` patterns | ✅ compiles |
| `maat/offline/extractors/query_extractor.py` | binding capture + build phase | ✅ |
| `tools/probe_bindings.py` | new — dumps grammar node shapes | ✅ |
| `tools/verify_bindings.py` | new — per-language coverage report | ✅ |

All four bindings the spec's §7 graph needs are captured from `demo_repo`:

```text
LOCAL      service           -> CheckoutService      in CheckoutController.handle
INSTANCE   payment_service   -> PaymentService       in CheckoutService.__init__
PARAMETER  repository        -> PaymentRepository    in PaymentService.__init__
INSTANCE   repository        -> repository           in PaymentService.__init__   (2-hop)
INSTANCE   payment_service   -> PaymentService       in RefundService.__init__
```

### Known loose ends

- `tests/offline/test_extractor.py` imports `BindingScope` but has no test using
  it yet — WP1b below closes this.
- Binding coverage is 1 of 18 languages. `bash` is legitimately N/A (shell
  scripts do not declare typed variables); the other 16 need patterns.

---

## 1. Work packages

Ordered. Each ends in a verifiable checkpoint. Nothing later starts before the
previous checkpoint passes.

### WP1 — Finish D23: binding capture across all languages

The prerequisite for everything else. Until this lands, Stage 6 cannot satisfy
the spec's §7 expected graph.

- [ ] **WP1a — Python** ✅ *done* — patterns, extractor wiring, 4/4 required bindings verified
- [ ] **WP1b — tests for the binding behaviour** (closes the loose end)
  - `test_parameter_annotation_is_captured`
  - `test_instance_attribute_from_constructor_is_captured`
  - `test_instance_attribute_aliasing_a_parameter_is_captured` (the 2-hop case)
  - `test_local_binding_is_captured`
  - `test_binding_records_the_enclosing_method`
  - `test_annotation_wins_over_constructed_type` — proves the `!type` negation
    keeps patterns mutually exclusive (one binding, not two)
  - `test_binding_on_a_foreign_object_is_not_recorded` — `other.field = Service()`
  - `test_complex_annotation_is_skipped` — `Optional[Repo]` is not a name
  - `test_rebinding_is_kept_in_source_order` — `x = A(); x = B()` yields both
  - `test_module_level_binding_attaches_to_the_module`
- [ ] **WP1c — roll out patterns to the remaining 16 languages**, in grammar families so each batch reuses what the last one learned:

  | Batch | Languages | Fixture files | What differs |
  |---|---|---|---|
  | A | javascript, typescript, tsx | 10 + 9 + 0 | `const x = new T()`; `this.x`; TS adds `x: T` annotations |
  | B | java, csharp, dart, kotlin, swift, scala | 10+6+5+6+6+5 | `T x = new T()`; `this.x`; Kotlin/Scala `val`/`var` |
  | C | c, cpp | 7 + 6 | `T x = ...`; pointer declarators are a distinct node |
  | D | go | 10 | `x := NewT()` and `var x T` — no `new` keyword |
  | E | rust | 9 | `let x: T = ...` — annotation is the common case |
  | F | php, ruby, lua | 6 + 7 + 5 | dynamically typed; `$x = new T()`, `x = T.new`, `local x = T.new()` |
  | — | bash | 5 | **N/A** — no typed bindings; document, do not force |

  Per language: probe the grammar with `tools/probe_bindings.py`, write the
  patterns, verify with `tools/verify_bindings.py`. **Never guess node names** —
  that is the M1 lesson that cost the most time.
- [ ] **WP1d — verify coverage**
  - `python tools/verify_bindings.py` reports **zero** languages needing patterns
  - full suite still green
  - **Checkpoint: `bash` documented as N/A; every other language produces bindings**

### WP2 — D27: version identity gains a pipeline fingerprint

Small, isolated, and blocking for correct publication later. Do it before
Stage 6 so that resolved models get sane version IDs from the first run.

- [ ] Add `RESOLUTION_POLICY_VERSION` constant (bumped when the ladder changes)
- [ ] `pipeline_fingerprint()` = digest over the `.scm` file content hashes + that constant
- [ ] `model_version_id(file_hashes_digest, pipeline_fingerprint)` — signature change
- [ ] Update `pipeline.index()` to compute and pass the fingerprint
- [ ] Tests:
  - unchanged content + unchanged pipeline → **same** version (idempotence preserved)
  - edit a `.scm` file → **new** version (the latent M1 bug, now fixed)
  - different policy version → **new** version
- [ ] **Checkpoint: `test_single_file_edit_reparses_exactly_one` still yields 1 parsed / 6 reused**

### WP3 — Stage 6, part 1: the lookup substrate

New package `maat/semantic/`. No resolution logic yet — just the indexes and
name handling everything else will query.

- [ ] `maat/semantic/__init__.py`
- [ ] `maat/semantic/names.py` — dotted-name splitting; instance-receiver
      vocabulary (importing `INSTANCE_RECEIVER_TOKENS` so there is one definition)
- [ ] `maat/semantic/bindings.py` — `BindingFact` list → per-scope type environments
      (`{method_qualified_name: {scope: {name: type_name}}}`), with the documented
      fallback from a method scope to its class's `__init__` scope
- [ ] `maat/semantic/symbol_index.py` — the seven indexes from the design plan §4,
      every list sorted so candidate order cannot depend on dict iteration
- [ ] Tests: index construction, duplicate names, type-env construction, the
      `__init__` fallback, rebinding (last-write-wins)
- [ ] **Checkpoint: indexes built from `demo_repo` contain exactly the expected keys**

### WP4 — Stage 6, part 2: the resolution ladder

- [ ] `maat/semantic/strategies.py` — one function per rung, S1–S9, each returning
      candidates or declining. Strategies receive an index and a query; they never
      touch the IR
- [ ] S1 exact qualified name · S2 lexical scope · S3 binding environment ·
      S4 import table · S5 module path · S6 inherited member · S7 unique
      repository-wide name · S8 multi-candidate · S9 nothing
- [ ] Confidence is a **declared table**, not a computed score
- [ ] Tests per rung, including the declines — a strategy that answers when it
      should decline is the failure mode that matters here
- [ ] **Checkpoint: each rung tested in isolation, including its refusal path**

### WP5 — Stage 6, part 3: orchestration

- [ ] `maat/semantic/resolve.py` — `resolve_ir(ir) -> SemanticIR`
  - process edges in sorted order
  - short-circuit already-resolved edges at S1 (makes re-running a no-op)
  - **never clear `target_name`** — it keys the relationship ID
  - record the winning strategy on the edge for auditability
- [ ] `Relationship.candidate_symbol_ids` added to `maat/core/contracts.py` for
      AMBIGUOUS edges; update `problems()` and `to_dict()`
- [ ] Wire resolution into `OfflinePipeline.index()` as a phase after IR build
- [ ] Tests:
  - **`test_expected_graph_from_section_7`** — the primary acceptance test:
    `CheckoutController → CheckoutService → PaymentService → PaymentRepository`
    and `RefundService → PaymentService`, asserted on resolved target IDs
  - **`test_demo_repo_resolves_completely`** — 42/42 EXACT, a second oracle
  - namespace separation (the two `Shared` classes stay distinct)
  - ambiguity produces AMBIGUOUS + candidates, never an arbitrary pick
  - `_edge/star_import.py` and `_edge/dynamic_dispatch.py` stay UNRESOLVED
  - resolved edge IDs equal their pre-resolution IDs (stability)
  - `resolve_ir` twice → identical digest (idempotence)
- [ ] **Checkpoint: the §7 expected graph test passes. This is the milestone gate.**

### WP6 — Stage 7: relationship validation

- [ ] `maat/semantic/validation.py` — `validate_ir(ir) -> ValidationReport`
- [ ] Checks: entity existence, source location, resolution/confidence
      consistency, status validity, version consistency, duplicate detection,
      orphan detection, ambiguity preservation
- [ ] **Reject vs remove kept strictly distinct** — a duplicate is a
      representation artifact (remove); a missing entity is a correctness failure
      (reject and count)
- [ ] Unresolved edges reported as `info`, never as failures
- [ ] `ValidationReport` — canonical JSON, `publishable` flag, issues with codes
- [ ] Tests per check, plus: report is stable across runs, invalid model is not publishable
- [ ] **Checkpoint: a deliberately corrupted IR is rejected with the right codes**

### WP7 — Stage 8: canonical model

- [ ] `maat/semantic/canonical.py` — `CanonicalModel` + `ModelStore`
- [ ] Lookups: by ID (all entity kinds), by qualified name, by
      source/target/type combination, evidence for an entity
- [ ] Immutability: no mutators; `publish()` refuses an existing version ID
- [ ] `CanonicalModel.load(index_dir)` — reconstruct from persistence
- [ ] Tests: every lookup; both `Shared` symbols returned by qualified-name
      lookup; round-trip write → reload → identical digest; publish refuses duplicates
- [ ] **Checkpoint: full model reconstructed from `ir.json` with a matching digest**

### WP8 — Integration, docs, memory

- [ ] Run the edge-case repo: determinism, idempotence, degraded-file isolation intact
- [ ] Confirm resolution statistics are sane across 18 languages
- [ ] Update `README.md`, `TODO.md` (tick M2 items), `docs/implementation-plan-resolution.md`
      (mark decisions as implemented), and write the M2 walkthrough
- [ ] Append to `.workbuddy-ai/memory/2026-09-14.md`
- [ ] **Checkpoint: full suite green, edge-case repo clean, docs current**

---

## 2. Dependency order

```text
WP1  binding capture ──────────┐
                               ├──► WP5  resolve_ir ──► WP6  validation ──► WP7  canonical ──► WP8
WP2  version identity ─────────┘         ▲
                                         │
                        WP3  indexes ────┤
                                         │
                        WP4  ladder ─────┘
```

WP1 and WP2 are independent and both block WP5. WP3 and WP4 are independent of
each other and both feed WP5. WP6 → WP7 → WP8 are strictly sequential.

**The single gate that matters:** WP5's `test_expected_graph_from_section_7`.
Everything before it exists to make that test possible; everything after it
assumes it passes.

---

## 3. Contract changes, exactly

| Change | File | Kind | Risk |
|---|---|---|---|
| `BindingScope` enum | `core/enums.py` | ✅ done | none — additive |
| `BindingFact` + `ExtractionFacts.bindings` | `extractors/base.py` | ✅ done | none — additive |
| `INSTANCE_RECEIVER_TOKENS` | `extractors/base.py` | ✅ done | one shared vocabulary |
| `@bind.*` patterns × 18 | `queries/*.scm` | WP1c | **medium** — grammar shapes must be probed, not guessed |
| `model_version_id(hashes, fingerprint)` | `core/ids.py` | WP2 | **high visibility** — existing version IDs change |
| `Relationship.candidate_symbol_ids` | `core/contracts.py` | WP5 | low — additive, changes the IR digest |
| New package `maat/semantic/` | — | WP3–WP7 | none |

---

## 4. Verification assets

| Asset | Purpose | Status |
|---|---|---|
| `tools/probe_bindings.py` | Dump a grammar's real node shapes for the four binding constructs | ✅ new |
| `tools/verify_bindings.py` | Per-language binding coverage; flags languages needing patterns | ✅ new |
| `tools/demo_offline.py` | End-to-end pipeline demo with incremental mode | existing |
| `tools/dump_trees.py` | Cross-language tree dumps (M1's original probing tool) | existing |
| `tests/run_all.py` | Stdlib unittest runner | existing |

The rollout loop for each language is: **probe → write patterns → verify → repeat.**
`tools/verify_bindings.py` is the arbiter; it reports `NEEDS PATTERNS` for any
language with files but zero bindings.

---

## 5. Definition of done for M2

- [ ] `tools/verify_bindings.py` reports no language needing patterns
- [ ] `test_expected_graph_from_section_7` passes — the spec's own graph
- [ ] `demo_repo` resolves 42/42 EXACT
- [ ] Unresolvable cases (`star_import`, `dynamic_dispatch`) stay UNRESOLVED
- [ ] Resolution is deterministic and idempotent; relationship IDs are stable
- [ ] Validation rejects an invalid model and reports why, machine-readably
- [ ] `CanonicalModel` round-trips through persistence with a matching digest
- [ ] M1's 137 tests still pass
- [ ] Edge-case repo: 18 languages, degraded files still isolated, model valid
- [ ] Docs updated; M2 walkthrough written

---

## 6. Risks, ranked

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Grammar shapes guessed, not probed** | The single biggest time sink in M1; wrong node names fail silently as zero captures | `probe_bindings.py` before every language; `verify_bindings.py` as the gate |
| **Ladder ordering is a judgement call** | Reordering S6/S7 changes what counts as ambiguous | Assert the expected *strategy* per fixture edge, not just the target |
| **Version-ID change breaks an expectation** | Existing IDs change | Do WP2 early and in isolation, before Stage 6 muddies the signal |
| **Field type declared in one method, used in another** | `self.repository` is bound in `__init__`, read in `process` | Documented `__init__` fallback in WP3; covered by a dedicated test |
| **Over-resolving** | A wrong-but-confident edge is worse than an unresolved one (§4.2) | Strategies decline by default; assert UNRESOLVED cases explicitly |
| **M1 regressions from extractor changes** | M2 touches Stage 4 code | Full suite after every query-file change; edge-case repo as canary |

---

## 7. Open decisions

**D23 — binding capture.** Taken as approved on your "proceed", and partially
built. **Confirm or reverse now** — reversing costs one file's patterns plus the
`BindingFact` type, so it is still cheap.

**D27 — version identity.** **Still open, and I have not touched it.** It changes
existing version IDs, which is correct but visible. Options: approve, or ask me
to walk the concrete failure case first.

---

## 8. Suggested next action

**WP1b + WP1c batch A** (javascript, typescript, tsx) in one pass: close the test
loose end, then take the three JS-family languages together since they share a
grammar lineage. That gets binding coverage from 1 to 4 languages and proves the
rollout loop before committing to the other twelve.

If you would rather see the payoff sooner, the alternative is to jump to **WP3 +
WP4 + WP5 with Python only** and get the §7 graph test passing on one language,
then backfill the rest. Faster feedback, but it leaves a known coverage gap in
the tree while Stage 6 is being built.
