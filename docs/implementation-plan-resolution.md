# Implementation Plan — M2: Resolution, Validation & Canonical Model

**Milestone:** M2 — Stages 6, 7, 8
**Status:** For review. No code written yet.
**Depends on:** M1 (complete — 137 tests passing, `maat/offline/` produces a `SemanticIR`)
**Supersedes:** nothing. Continues the M1 decision log from D22.

---

## 1. Scope

M1 produced a `SemanticIR` in which **every reference is `UNRESOLVED`** — that was
deliberate (spec §4.2). M2 turns those references into resolved edges, validates
them, and gives the result a canonical query surface.

| Stage | Deliverable | Input → Output |
|---|---|---|
| **6** | Symbol & relationship resolution | `SemanticIR` with unresolved edges → `SemanticIR` with resolved edges |
| **7** | Relationship validation | resolved `SemanticIR` → `ValidationReport` + a publishable-or-not verdict |
| **8** | Canonical semantic model | validated `SemanticIR` → `CanonicalModel` with lookup indexes |

M2 is still entirely offline and deterministic. **No model is reachable from any
module in this milestone** — that is what makes §13 AC5 ("no hallucinated
relationship") structural rather than a promise.

---

## 2. The acceptance oracle

Spec §7 defines the fixture and its **expected graph**. This is the binding
acceptance test for Stage 6, not a suggestion:

```text
CheckoutController → CheckoutService → PaymentService → PaymentRepository
RefundService      → PaymentService
```

`RefundService → PaymentService` matters twice: it is what makes
`find_callers(PaymentService)` return two results (M3), and it is the only case
in the fixture where two distinct callers reach the same target.

---

## 3. Finding: Stage 6 has a prerequisite M1 did not build

I traced all 12 `CALLS` edges M1 emits for `demo_repo` and classified what each
one needs in order to resolve. This is the single most important input to the
plan, so it is stated in full rather than summarised.

| # | Edge as emitted by M1 | What resolution needs | Have it? |
|---|---|---|---|
| 1 | `CheckoutController.handle` → `CheckoutService` | import table | ✅ |
| 2 | `CheckoutController.handle` → `service.checkout` | **local var type** (`service = CheckoutService()`) | ❌ |
| 3 | `CheckoutService.__init__` → `PaymentService` | import table | ✅ |
| 4 | `CheckoutService.__init__` → `PaymentRepository` | import table | ✅ |
| 5 | `CheckoutService.checkout` → `Payment` | import table | ✅ |
| 6 | `CheckoutService.checkout` → `self.payment_service.process` | **field type** (assigned in `__init__`) | ❌ |
| 7 | `PaymentService.process` → `self.validate` | same-class member lookup | ✅ |
| 8 | `PaymentService.process` → `self.repository.save` | **field type from ctor param annotation** | ❌ |
| 9 | `PaymentRepository.save` → `self._write` | same-class member lookup | ✅ |
| 10 | `RefundService.__init__` → `PaymentService` | import table | ✅ |
| 11 | `RefundService.__init__` → `PaymentRepository` | import table | ✅ |
| 12 | `RefundService.refund` → `self.payment_service.process` | **field type** | ❌ |

**Four of twelve edges require type information that M1 never captured — and
every single edge of the spec's expected graph is among them.**

This is the decisive fact of the milestone, so it is stated in full. Each of the
four edges in §7's chain resolves through a receiver whose type is only knowable
from a binding, never from a name:

| §7 expected edge | Call site | Receiver is | Needs |
|---|---|---|---|
| `CheckoutController` → `CheckoutService` | `service.checkout(request.cart)` | local variable | local binding |
| `CheckoutService` → `PaymentService` | `self.payment_service.process(payment)` | instance field | field binding (constructed) |
| `PaymentService` → `PaymentRepository` | `self.repository.save(payment)` | instance field | field binding (**from a parameter annotation**) |
| `RefundService` → `PaymentService` | `self.payment_service.process(payment)` | instance field | field binding (constructed) |

Without binding facts, Stage 6 resolves **none** of the four edges the spec
explicitly requires — so §7's acceptance criterion fails outright, and M3's
`find_callers(PaymentService)` returns 0 results where the fixture documents 2.

Concretely, satisfying §7 requires inferring:

```python
class CheckoutService:
    def __init__(self) -> None:
        self.payment_service = PaymentService(PaymentRepository())   # field ← constructed type
    def checkout(self, cart) -> bool:
        payment = Payment(cart.total)
        return self.payment_service.process(payment)                 # resolve through the field

class PaymentService:
    def __init__(self, repository: PaymentRepository) -> None:
        self.repository = repository                                 # field ← parameter annotation
    def process(self, payment: Payment) -> bool:
        self.repository.save(payment)                                # resolve through the field
```

`CallFact` records `receiver="self.payment_service"` as **raw text** and nothing
more. There is no binding information anywhere in the model.

### Why this cannot be worked around

Three tempting shortcuts, all rejected:

- **Regex the method body at resolve time.** Language-specific, fragile, and it
  breaks the Tier 2 → Tier 3 boundary that M1's whole architecture rests on.
- **Resolve `self.x` to any symbol named `x`.** Would resolve
  `self.payment_service.process` to the first `process` in the repository —
  producing a *confidently wrong* edge, which §4.2 explicitly forbids.
- **Leave these edges `UNRESOLVED` and declare Stage 6 done.** Fails §7, which
  is an acceptance criterion, and would make `find_callers(PaymentService)`
  return 0 results instead of 2.

### The fix: `BindingFact` — a new Stage 4 capture family

Add a fourth fact type alongside `SymbolFact` / `ImportFact` / `CallFact`:

```python
@dataclass
class BindingFact:
    """A name bound to a type within a scope."""
    bound_name: str          # "service"  or  "self.payment_service"
    type_name: str           # "CheckoutService"  (raw, unresolved)
    span: SourceSpan
    enclosing_qualified_name: str | None   # the method the binding occurs in
    scope: BindingScope      # LOCAL | INSTANCE | PARAMETER
```

Captured in each `.scm` by a new `@bind.*` family, from three sources:

| Source | Example | Scope |
|---|---|---|
| Constructed assignment | `x = Type(...)` / `self.x = Type(...)` | LOCAL / INSTANCE |
| Annotated parameter | `def f(self, repo: PaymentRepository)` | PARAMETER |
| Annotated assignment | `x: Type = ...` | LOCAL |

This is the same extension mechanism M1 already established: **one new capture
family per query file, no change to any language-neutral module.** `type_name`
stays raw and unresolved — it is resolved later by the same import-table logic
that resolves any other name, so `from a.b import C` makes `C(...)` resolvable
from anywhere.

**Cost:** 18 query files × ~3 patterns, plus `BindingFact` plumbing through
`ExtractionFacts`. **Benefit:** the §7 graph becomes satisfiable, and field/local
inference stops being a special case — it becomes one more lookup in the same
ladder.

> **This is Decision D23 and it needs your approval**, because it means M2
> touches Stage 4 code that M1 considered finished. The alternative is to ship
> Stage 6 without the §7 graph, which I do not recommend.

---

## 4. Architecture

New package, sitting beside `maat/offline/` rather than inside it. `offline/` is
the *syntax* tier and knows about grammars; `semantic/` is the *meaning* tier and
must not.

```text
maat/semantic/
    __init__.py
    names.py         name normalisation, dotted-name splitting, instance-receiver vocabulary
    bindings.py      BindingFact → per-scope type environments
    symbol_index.py  the lookup substrate: every index the resolver queries
    strategies.py    the resolution ladder — one function per strategy
    resolve.py       Stage 6 orchestrator: resolve_ir(ir) -> SemanticIR
    validation.py    Stage 7: validate_ir(ir) -> ValidationReport
    canonical.py     Stage 8: CanonicalModel with lookup indexes
```

**Layering rule, mirroring M1's:** `symbol_index.py` is the only module that
knows how the model is stored; `strategies.py` is the only module that decides
what a reference means; `resolve.py` is the only module that mutates the IR.
A strategy receives an index and a query and returns candidates — it never
touches the IR directly, which is what keeps resolution testable one strategy at
a time.

### The lookup substrate

Built once per resolution run, in one pass over the IR:

| Index | Key → Value | Serves |
|---|---|---|
| `by_id` | symbol id → `Symbol` | O(1) fetch |
| `by_qualified_name` | `"a.b:C"` → `Symbol` | exact resolution |
| `by_name` | `"C"` → `[Symbol, ...]` | lexical + suffix lookup |
| `by_module` | `"a.b"` → module `Symbol` | import resolution |
| `imports_by_module` | module → `{local_name: (module_path, original_name)}` | import tables |
| `members_by_parent` | parent qualified name → `[Symbol, ...]` | `self.x` member lookup |
| `type_env_by_scope` | method qualified name → `{name: type_name}` | **binding resolution** |

Every index stores **sorted** lists so that candidate ordering — and therefore
ambiguity decisions — cannot depend on dict or set iteration order.

---

## 5. The resolution ladder

Resolution is a **precedence-ordered ladder**, not a single algorithm. Each rung
either produces a confident answer or declines and passes to the next. The first
rung that yields candidates decides the outcome.

| # | Strategy | Resolves | Status | Conf. |
|---|---|---|---|---|
| S1 | **Exact qualified name** — target text is already a qualified name present in the index | `models.payment:Payment` | `EXACT` | 1.0 |
| S2 | **Lexical scope** — enclosing symbol, then enclosing class, then module | `self.validate` → own class | `EXACT` | 1.0 |
| S3 | **Binding environment** — receiver is a bound name whose recorded type resolves | `self.repository.save` | `EXACT` | 1.0 |
| S4 | **Import table** — name is imported; follow `(module, original_name)` | `Payment` via `from models.payment import Payment` | `EXACT` | 1.0 |
| S5 | **Module path** — target is a module path in the index (for `IMPORTS`) | `models.payment` | `EXACT` | 1.0 |
| S6 | **Inherited member** — `self.x` not on this class, found on a resolved base | `self.name` → `Base1.name` | `HEURISTIC` | 0.7 |
| S7 | **Unique repository-wide name** — exactly one symbol with that bare name | `process` if unique | `HEURISTIC` | 0.6 |
| S8 | **Multiple candidates** — several equally plausible targets | — | `AMBIGUOUS` | 0.0 |
| S9 | **Nothing** — no candidate | — | `UNRESOLVED` | 0.0 |

**Why a ladder rather than a scoring function.** A score-and-threshold design
would let a heap of weak signals outvote one decisive one, and it makes
"why did this resolve to X?" unanswerable. With a ladder, the resolution status
*is* the explanation, and `strategy` is recorded on the edge for auditability.

**Instance receivers.** `self`, `this`, `cls`, `Me`, `$this`, `self::` all mean
"the current instance". They are handled by one documented frozenset in
`names.py` — a linguistic fact about object-oriented languages, not a per-language
branch. A receiver in this set routes to S2/S3/S6; any other receiver must be
found in the binding environment or the edge stays unresolved.

**Confidence is a policy, not a computation.** The table above *is* the policy,
declared in one place. This keeps `Relationship.problems()`'s existing
invariants (`EXACT ⇒ 1.0`, `UNRESOLVED ⇒ 0.0`) satisfiable by construction
rather than by hoping a formula lands on the right value.

---

## 6. Contract changes

Three, all additive or identity-preserving except the third.

### 6.1 `BindingFact` and `@bind.*` captures — additive

New fact type; `ExtractionFacts` gains a `bindings` list. Existing consumers
ignore it.

### 6.2 `Relationship.candidate_symbol_ids` — additive

AC3 requires an ambiguous edge to be "marked ambiguous rather than assigned an
arbitrary target". Marking alone loses information — we would know it was
ambiguous but not *between what*. So:

```python
candidate_symbol_ids: list[str] = field(default_factory=list)   # sorted, populated when AMBIGUOUS
```

`target_symbol_id` stays the `unresolved:` placeholder for ambiguous edges. This
is strictly better than emitting N ambiguous edges for one call site, which would
inflate relationship counts and break `find_callers` in M3.

### 6.3 `model_version_id` gains a pipeline fingerprint — **identity change**

This one is subtle and important.

Today: `model_version_id(file_hashes_digest)` — derived from file content only.
That was correct for M1, where the model was a pure function of file content.

M2 breaks that premise. Resolution changes the IR **without changing any file**.
So the same content hash would map to two genuinely different models — an
unresolved M1 IR and a resolved M2 IR — that share one version ID. The version
would stop being a faithful identity, and Stage 12's atomic publication (which
keys on version) would have nothing trustworthy to key on.

```python
def model_version_id(file_hashes_digest: str, pipeline_fingerprint: str) -> str:
    return VERSION_PREFIX + _digest(f"{file_hashes_digest}\x1f{pipeline_fingerprint}")
```

`pipeline_fingerprint` is a digest over:

1. the **content hashes of the extraction query files** — editing a `.scm` changes
   the model, so it must change the version;
2. a **`RESOLUTION_POLICY_VERSION`** integer constant, bumped whenever the ladder
   or confidence table changes.

Properties preserved and gained:

- unchanged content + unchanged pipeline → same version → **idempotence kept**
  (§9 AC2: a no-change run still reparses nothing and mints no new version);
- M1-only vs M1+resolve → different versions → **correctness gained**;
- edited query file → new version → **correctness gained** (this is a latent bug
  in M1 today: editing `python.scm` changes the model but not the version).

M1's existing published artifacts will be regenerated. Pre-release, so no
migration path is needed — but the change should be noted in the walkthrough.

---

## 7. Data flow

```text
SemanticIR (all references UNRESOLVED)
      │
      │  symbol_index.build_index(ir)      one pass, sorted lists
      ▼
SymbolIndex  +  type environments (from BindingFact)
      │
      │  resolve.resolve_ir(ir)
      │    for each relationship, in sorted order:
      │        for rung in LADDER:                 S1 … S9
      │            candidates = rung(index, query)
      │            if candidates: decide status/confidence; break
      ▼
SemanticIR (edges resolved; ids unchanged; target_name retained)
      │
      │  validation.validate_ir(ir)
      ▼
ValidationReport { publishable: bool, counts, issues[] }
      │
      │  canonical.CanonicalModel(ir)
      ▼
CanonicalModel  with by_id / by_qualified_name / by_source_target_type / evidence lookups
```

### Worked trace — `PaymentService.process → self.repository.save`

```text
1. Edge in M1's IR
   source    services.payment_service:PaymentService.process
   target    unresolved:<digest>          target_name "self.repository.save"
   status    UNRESOLVED   confidence 0.0

2. names.split_receiver("self.repository.save")
   → receiver "self.repository", member "save"
   → receiver head "self" ∈ INSTANCE_RECEIVERS  → instance member

3. symbol_index.members_by_parent["services.payment_service:PaymentService"]
   → {__init__, process, validate}   ✗ "save" absent  → S2 declines

4. type_env_by_scope["services.payment_service:PaymentService.process"]
   → {}                              ✗ no local binding    → S3 declines
   (fallback: the enclosing class's __init__ env)
   type_env_by_scope["...:PaymentService.__init__"]
   → {"repository": "PaymentRepository"}          ← from the @bind.parameter capture

5. resolve type_name "PaymentRepository" via S4 import table of module
   services.payment_service
   → imports {Payment: models.payment, PaymentRepository: repositories.payment_repository}
   → module repositories.payment_repository

6. members_by_parent["repositories.payment_repository:PaymentRepository"]["save"]
   → exactly one → repositories.payment_repository:PaymentRepository.save

7. Result
   target_symbol_id  repositories.payment_repository:PaymentRepository.save
   status            RESOLVED_EXACT      confidence 1.0
   strategy          "binding.parameter"   (recorded for audit)
   id                UNCHANGED  ← keyed on target_name, which is retained
   target_name       "self.repository.save"  ← retained
```

Step 7 is load-bearing: `relationship_id` is keyed on `target_name`, so
**`target_name` must never be cleared on resolution**. Clearing it would renumber
every resolved edge, making a resolved model look like an unrelated one to the
change detector. This is now an invariant, and it is why M1's choice to key the
ID on the raw observed text was the right one.

---

## 8. Stage 7 — relationship validation

Validation runs between resolution and publication, and is the gate that makes
"invalid semantic data cannot be published" true.

| Check | Rule | Failure action |
|---|---|---|
| Entity existence | source and resolved target must exist in the model | **reject** the edge |
| Source location | span must be valid and within its file | **reject** the edge |
| Resolution consistency | `EXACT ⇒ 1.0`, `UNRESOLVED ⇒ 0.0` | **reject** the edge |
| Status validity | status ∈ the four declared states | **reject** the edge |
| Version consistency | every entity shares one `model_version` | **reject** the model |
| Duplicate detection | key `(source, type, target, line, col)` unique | **remove** the later duplicate, record it |
| Orphan detection | unresolved edges are legal but reported | **report** (never silently dropped) |
| Ambiguity preservation | `AMBIGUOUS` edges must carry ≥2 candidates | **downgrade** to `UNRESOLVED` |

Two design points worth stating:

- **Reject vs remove.** A duplicate is a *representation* artifact — removing it
  loses nothing. A missing entity is a *correctness* failure — it must be
  rejected and counted, never quietly dropped. Conflating the two is how
  validation reports become decorative.
- **Orphans are data, not errors.** §4.2 prefers an explicit unresolved edge, so
  an unresolved edge is a *successful* observation. It is counted and reported,
  never treated as a validation failure. Otherwise the incentive is to resolve
  things that should not resolve.

`ValidationReport` is machine-readable (JSON, canonical). Shape, with numbers
from `demo_repo` (42 edges: 12 `CALLS`, 19 `CONTAINS`, 11 `IMPORTS`) — note that
`demo_repo` is expected to resolve **completely**, so the ambiguous and unresolved
counts are exercised by `edgecase_repo`, not here:

```json
{
  "publishable": true,
  "counts": {"relationships": 42, "exact": 42, "heuristic": 0, "ambiguous": 0, "unresolved": 0},
  "issues": [{"code": "ORPHAN_RELATIONSHIP", "severity": "info", "subject": "rel_…", "detail": "…"}],
  "by_check": {"duplicate": 0, "missing_entity": 0, "invalid_location": 0}
}
```

If `demo_repo` does **not** come out fully resolved, that is a Stage 6 defect, not
an acceptable outcome — which makes this report a useful second oracle alongside
the §7 graph.

---

## 9. Stage 8 — canonical semantic model

`CanonicalModel` wraps a **validated, immutable** `SemanticIR` and adds the
lookups Stage 8's ACs demand:

| AC | Method |
|---|---|
| retrieve by stable ID | `symbol(id)`, `file(id)`, `relationship(id)`, `chunk(id)` |
| symbols by qualified name | `symbols_by_qualified_name(qn)` |
| relationships by source/target/type | `relationships(source=…, target=…, type=…)` — all optional |
| evidence for an entity | `evidence_for(entity_id)` |
| reconstruct from persistence | `CanonicalModel.load(index_dir)` |

**Immutability.** `ModelVersion` is frozen after publication (spec §15). The
store exposes no mutators; a new model is a new object with a new version. This
is enforced by not defining mutating methods, and by `ModelStore.publish()`
refusing to overwrite an existing version ID.

`ModelStore` holds versions and an active pointer. The **atomic pointer switch
and rollback are Stage 12 (M3)** — M2 provides the immutable version object and
the store that can hold several, and deliberately stops there.

---

## 10. Determinism and idempotence

Resolution must not weaken M1's guarantees:

1. **Deterministic.** Edges are processed in sorted order; every candidate list is
   sorted; no set or dict iteration influences a decision. Two runs produce an
   identical `model_digest`.
2. **Idempotent.** `resolve_ir(resolve_ir(ir)) == resolve_ir(ir)`. Already-resolved
   edges are skipped by the ladder (they short-circuit at S1 on their own ID), so
   re-running resolution is a no-op — including for `AMBIGUOUS` edges, which must
   not drift to a different candidate set.
3. **Stable IDs.** Resolution never changes a relationship ID (§7, step 7).
4. **No new nondeterminism from bindings.** Type environments are built from
   sorted facts; where two bindings of the same name exist in one scope (rebinding),
   the **last write in source order** wins, deterministically.

Verified by new tests mirroring M1's: `test_two_runs_identical`,
`test_resolution_is_idempotent`, `test_resolved_ids_match_unresolved_ids`.

---

## 11. Design decisions log (continuing from D22)

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| D23 | Extend Stage 4 with `BindingFact` | §7's expected graph is unsatisfiable without field/local type info (§3) | M2 touches M1's extractor; 18 query files gain ~3 patterns |
| D24 | Resolution as a precedence ladder, not a score | Status *is* the explanation; auditable; confidence stays a declared policy | Ordering is a judgement call and must be documented |
| D25 | `target_name` retained forever | Keeps `relationship_id` stable across resolution (§7 step 7) | Redundant storage; a resolved edge carries both raw text and ID |
| D26 | `candidate_symbol_ids` on `Relationship` | AC3 wants ambiguity *marked*, but the candidates are the useful part | One more list on a hot contract |
| D27 | Version identity gains a pipeline fingerprint | Resolution changes the model without changing files (§6.3) | Existing version IDs change; regenerating artifacts |
| D28 | Ambiguous edges keep the `unresolved:` placeholder target | Avoids inflating edge counts and breaking M3's `find_callers` | Callers must check `resolution_status` before using `target_symbol_id` |
| D29 | Unresolved edges are reported, never failed | §4.2 treats an explicit unresolved edge as correct behaviour | Validation reports are noisier; severity distinguishes info from error |
| D30 | `maat/semantic/` as a sibling of `offline/` | Keeps the syntax tier free of meaning, mirroring M1's tier boundary | One more package |
| D31 | Instance receivers as one shared frozenset | `self`/`this`/`cls` is a linguistic fact, not a grammar rule | A hardcoded vocabulary in one file |
| D32 | Stage 8 stops short of atomic publication | Pointer switch and rollback are explicitly Stage 12 | `ModelStore` is a stepping stone, not the final store |

---

## 12. Test plan (RED → GREEN)

`tests/semantic/`, stdlib `unittest`, same shape as `tests/offline/`.

### Stage 6 — `test_resolve.py`
- **AC1** exact resolution: every edge in §7's expected chain resolves, with the
  exact expected target IDs — *the primary acceptance test*
- **AC2** namespace separation: `_edge/duplicate_names_a.py:Shared` and
  `duplicate_names_b.py:Shared` stay distinct; neither resolves to the other
- **AC3** ambiguity: a crafted two-candidate call resolves to `AMBIGUOUS` with
  both candidates recorded, and **not** to an arbitrary one
- **AC4** unknown target: `_edge/dynamic_dispatch.py`'s
  `getattr(module, 'handle')` stays `UNRESOLVED`
- **AC5** no hallucination: assert the resolver is a pure function of the index —
  resolving a model twice, and resolving with the index shuffled, give identical
  results; assert no model/network import is reachable from `maat/semantic/`
- **AC6** provenance: every resolved edge has a source location inside its
  source symbol's file, and an evidence row exists for it
- import resolution: `from x import Y as Z` resolves `Z`
- star import: `from pkg.module1 import *` does **not** resolve bare names
  (`_edge/star_import.py`) — explicitly `UNRESOLVED`, not guessed
- inheritance: `Service1(Base1)` → `INHERITS` resolved; Java
  `extends Base1 implements Handler1` → both, with correct types
- inherited member: `self.x` found on a resolved base → `HEURISTIC`, not `EXACT`
- overloads: `_edge/overloads.java` resolves to one of the overloads
  deterministically, and does not merge them
- deep nesting / 197 KB file: resolution completes without recursion errors
- idempotence: `resolve_ir` twice → identical digest
- ID stability: every resolved edge's ID equals its pre-resolution ID

### Stage 7 — `test_validation.py`
- duplicate edges removed, counted, and reported
- missing entity → rejected, model not publishable
- invalid source location → rejected
- `AMBIGUOUS` with fewer than 2 candidates → downgraded to `UNRESOLVED`
- mixed versions → model rejected
- unresolved edges reported as `info`, never as failures
- report is valid JSON and stable across runs

### Stage 8 — `test_canonical.py`
- lookup by ID for every entity kind
- `symbols_by_qualified_name` returns the right symbol, and both `Shared`s for
  the duplicate-name case
- relationship queries by source, by target, by type, and by combination
- `evidence_for` returns the backing evidence
- **reconstruct from persistence**: write, reload, assert the digest matches
- immutability: publishing an existing version ID is refused

### Regression
M1's 137 tests must stay green. The only expected M1 changes are the
`BindingFact` additions and the `model_version_id` signature — both covered by
existing tests that will need their expectations updated.

---

## 13. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `@bind.*` patterns mis-capture across 18 grammars | Medium | Same method that worked in M1: dump real trees, verify per language, iterate. `tools/verify_queries.py` already exists |
| Ladder ordering produces surprising resolutions | Medium | Record `strategy` on every edge; assert the expected strategy per fixture edge in tests, not just the expected target |
| Rebindings (`x = A(); x = B()`) | Low | Last-write-in-source-order wins; covered by an explicit test |
| Field type declared in one method, used in another | Low (fixtures cover it) | Type env falls back from method scope to the class's `__init__` env — documented as the one heuristic in S3 |
| M1 regressions from the extractor change | Medium | Run the full M1 suite after every query-file change; the edge-case repo is the canary |

---

## 14. Non-goals

- **No derived relationships.** `DEPENDS_ON`, `TRANSITIVELY_DEPENDS_ON`,
  `IMPACTED_BY`, `REACHABLE_FROM` are Stage 9's graph projection (§4.3). Writing
  them into the semantic model would be exactly the mistake §4.3 warns against.
- **No graph, FTS5 or vector indexes** — M3.
- **No cross-language resolution.** A Python call to a Go symbol stays unresolved.
- **No whole-program type inference.** Only declared annotations and constructed
  assignments, which is what the fixtures require and what the ladder encodes.
- **No retrieval, reasoning, or agent layers** — M4/M5.

---

## 15. Proposed order of work

1. **D23 first**, in isolation: add `BindingFact` + `@bind.*` to all 18 query
   files, verify with the existing query tooling, keep M1's 137 tests green.
   Nothing else can be trusted until this lands.
2. `names.py` + `symbol_index.py` + `strategies.py` with S1/S2/S4/S5 only
   (no bindings) — this resolves 8 of the 12 `CALLS` edges and all 11 `IMPORTS`
   edges, **but none of the four §7 chain edges**, which is exactly why step 3
   is not optional.
3. Add S3 (bindings) and S6/S7/S8/S9 — completes the §7 graph. **Checkpoint: the
   expected graph test passes.**
4. `validation.py` (Stage 7) + `canonical.py` (Stage 8).
5. Run the edge-case repo; confirm determinism, idempotence, and that the 9
   degraded files still isolate cleanly.
6. Update the plan/walkthrough docs and `TODO.md`.

---

## 16. What I need from you

1. **Approve D23** (extend the extractor with `BindingFact`)? Without it, the
   spec's own §7 expected graph cannot be met.
2. **Approve D27** (version identity gains a pipeline fingerprint)? It changes
   existing version IDs, which is the correct behaviour but is a visible break.
3. Anything you want reordered, or any part of the ladder you disagree with —
   the precedence order in §5 is the part most worth arguing about.
