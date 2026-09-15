# Verification

How the acceptance criteria are discharged by the test suite — and which ones
are not, and why.

For the criteria themselves, see [`../SPEC.md`](../SPEC.md). For the decisions
behind the behaviour under test, see [`decisions.md`](decisions.md).

---

## 1. The criteria come in four layers

Conflating these is the main source of confusion when reading the spec:

| Layer | Where | Count | Nature |
|---|---|---:|---|
| **Numbered ACs** | `### ACn` in §8–§31 | **83** | Per-stage, testable — the working contract |
| **Unnumbered bullets** | §7, §11, §12, §14, §15, §17, §18, §21, §24 | **43** | Same force, simply not numbered |
| **Named scenarios** | §32 `E001`–`E005` | **5** | End-to-end queries the whole system must answer |
| **Summary layers** | §33, §34, §40, §41 | **51** | 26 quality gates + 12 failure conditions + 10 DoD properties + 3 rules |

That is **131 stage-level criteria** plus 51 summary statements. Verified by
counting the spec directly: 83 `### ACn` headings, 5 `### E00n` headings, 41
top-level sections.

The 131 are not 131 independent checks — they are instances of **eight recurring
demands**: determinism, honesty, isolation, version coherence, provenance,
boundedness, minimality, replaceability. Recognising which family a criterion
belongs to tells you what kind of test can prove it.

---

## 2. Suite shape

**137 tests, 33 classes, 6 files.** `python tests/run_all.py`, ~15 s, stdlib
`unittest` only.

| File | Tests | Classes | Covers |
|---|---:|---:|---|
| `tests/offline/test_snapshot.py` | 16 | 4 | §8 Stage 1 |
| `tests/offline/test_changes.py` | 19 | 3 | §9 Stage 2 |
| `tests/offline/test_parser.py` | 20 | 6 | §10 Stage 3 |
| `tests/offline/test_extractor.py` | 16 | 8 | §11 Stage 4 |
| `tests/offline/test_ir.py` | 31 | 7 | §12 Stage 5 |
| `tests/offline/test_pipeline.py` | 35 | 5 | end-to-end, incremental, publication, §30 |

Shared support lives in `tests/support.py`: `TempRepository` (a disposable copy of
a fixture) and `temp_repo(files)` (a synthetic repository from an explicit file
map). See [`testing.md`](testing.md).

---

## 3. Coverage by stage

| Spec stage | ACs | Directly covered | Notes |
|---|---:|---:|---|
| §7 Stage 0 | 7 | 7 | expected graph inlined in the test, not a separate fixture |
| §8 Stage 1 | 5 | 5 | |
| §9 Stage 2 | 6 | 6 | AC6 split across two files |
| §10 Stage 3 | 6 | 6 | |
| §11 Stage 4 | 3 | 3 | `REFERENCES` / `IMPLEMENTS` not produced — see §5 |
| §12 Stage 5 | 6 | 6 | `maat/core/` itself has no test module — see §5 |
| §13 Stage 6 | 6 | 0 | M2 — AC4/AC5 pre-satisfied only |
| §16 Stage 9 | 5 | 0 | M3 — preconditions only |
| §19 Stage 12 | 4 | 1 | AC3 only; M1 publishes atomically but there is no version pointer yet |
| §30 Stage 22 | 5 | 5 | fully covered |
| §36 edge matrix | 6 groups | 3 groups | resolution / retrieval / reasoning / agent groups are M2+ |

**M1's acceptance surface is fully covered.** Every numbered AC belonging to §8,
§9, §10, §11 and §30 has at least one direct test.

**Overall: 39 of 131 stage-level criteria (30%) are covered** — the remainder
belong to stages that are not built. This is a milestone boundary, not a gap.

The three genuine gaps inside M1's own scope are:

1. one untested defect in the model *loader* (below),
2. `maat/core/` having no home in the test tree,
3. spec items M1 legitimately defers.

---

## 4. Cross-cutting properties

| Property | How it is proven |
|---|---|
| **Determinism** | Two runs over unchanged content produce a byte-identical `ir.json` and an identical `model_digest` |
| **Idempotence** | Reindexing unchanged content mints no new version |
| **Version coherence** | Every published artifact references one `model_version`; no entity carries a version other than the model's |
| **Isolation** | A malformed file is degraded and named; the other 133 files in `edgecase_repo` are unaffected |
| **Provenance** | Every `Evidence` row carries `retrieval_source="offline.ast"`; entities without provenance are rejected |
| **Atomicity** | No `.tmp-` file survives a write; an invalid build leaves the previous version intact |
| **Honesty** | Every reference is `UNRESOLVED` with confidence `0.0` — the model never claims a resolution it has not performed |

---

## 5. Known gaps and defects

### The model loader is not defensive

`load_previous_ir` guards the JSON parse but not the rehydration that follows it,
so a **structurally** invalid previous model raises `KeyError`, `ValueError` or
`TypeError` out of the index call instead of triggering a full rebuild. An empty
object is silently accepted as an empty model.

No test covers reading a malformed `ir.json`. Full analysis in
[`decisions.md`](decisions.md) and [`../SECURITY.md`](../SECURITY.md).

### `maat/core/` has no test module

1,161 lines covered only indirectly. Verified-untested: `combine_hashes`
order-independence, `model_digest`, `_StrEnum.__str__`, `FileRecord.problems()`
path validation, `SourceSpan.whole_file` / `point` / `is_zero_width` /
`contains_line`, and `read_json` / `write_json`.

`combine_hashes` is the sharpest case: it derives every `version_id` and exists
purely for order-independence, and it has **zero** references in `tests/`.

### `REFERENCES` and `IMPLEMENTS` are neither produced nor tested

Spec §11 asks the extractor for "References" and "Implementations".
`RelationshipType.REFERENCES` and `IMPLEMENTS` exist but have zero references in
`maat/offline/` and zero in `tests/`. This needs an explicit decision — either
produce them or record why they are not needed.

### Relationship invalidation is unimplemented

Spec §36's "changed dependency target" and §4.6's relationship invalidation have
no implementation: incremental reuse re-stamps only `model_version` and `file_id`.
Defensible for M1, because there are no resolved cross-file edges to invalidate.
It must be an explicit M2 item, since §29 is §9's direct successor and deferring
it past M2 will constrain M2's design.

### The expected semantic graph is inlined

Spec §7 names "Expected semantic graph" as a deliverable. It lives as constants
inside `tests/offline/test_pipeline.py` rather than a standalone fixture. Asserting
it directly is arguably better than a separate file, but the divergence from the
spec should be recorded rather than silent.

### The prescribed test tree is not followed

Spec §35 describes a per-stage tree (`tests/offline/snapshot/`, …). The actual
layout is flat `tests/offline/test_*.py`. Functionally equivalent; the divergence
is intentional and recorded here.

### `languages.py` counts are prose, not assertions

61 registered languages is asserted nowhere. `registry_summary` is untested, and
the extractable count is derived from the filesystem, so it can drift from any
number written in documentation.

### Fixture bytecode

`tests/fixtures/edgecase_repo/__pycache__/cached.cpython-313.pyc` is committed
**deliberately** — the scanner's exclusion rules are tested against it. It is
protected from `.gitignore` by an explicit negation. Do not remove it.

---

## 6. Where the criteria are weak

Eight criteria **cannot be falsified as written**. These are specification gaps,
not implementation gaps, and each should be sharpened before the stage that
depends on it is built.

| Criterion | Problem | Sharper form |
|---|---|---|
| **§9 AC5** Rename | Conditional on "where supported" and "when cache policy allows reuse" — satisfiable vacuously by declaring a restrictive policy | "A rename must not change any entity ID that survives the move, and must not require reparsing file contents" |
| **§16 AC3** Transitive traversal | "within depth N" — N is never fixed | State N, or state that N is caller-supplied and that the bound is enforced |
| **§13 AC3** Ambiguous resolution | "Ambiguous" is undefined — ambiguity is a policy decision, not a fact | Define the predicate (for example: more than one candidate at equal confidence) |
| **§21** Intent ambiguity | "must not silently route to an arbitrary strategy" — no threshold for when a query counts as ambiguous | Define the confidence threshold and the clarification response |
| **§25 AC4** Exact relationship validation | "within the defined response policy" — the policy is never defined | Define the policy (for example: exact set equality for `FIND_REFERENCES`) |
| **§13 AC5** No hallucinated relationship | Constrains a mechanism rather than an output; not directly observable | Test the proxy: every relationship carries evidence (§13 AC6) and confidence matches status |
| **§11 AC3** No AST leakage | Structural and negative; only checkable by absence | Enumerate the allowed fact vocabulary exhaustively |
| **§10 AC6** Partial parsing | "Where Tree-sitter provides a usable partial tree" — "usable" is undefined | Define usable as at least one clean top-level statement — **the implementation already does this** |

**§10 AC6 is the model to follow.** The implementation made the undefined word
concrete — "usable" became "at least one clean top-level statement" — and the
behaviour became testable as a result. The other seven deserve the same treatment.

---

## 7. Running the checks

```bash
python tests/run_all.py            # 137 tests, exit 1 on failure
python tests/run_all.py -v         # verbose
python tests/run_all.py offline    # substring filter on the test id

python tools/verify_queries.py     # all 18 .scm compile and fire their captures
python tools/verify_bindings.py    # per-language @binding coverage
```

CI runs all three. `verify_queries.py` matters more than it looks: a malformed
query does not crash the pipeline, it silently degrades extraction.
