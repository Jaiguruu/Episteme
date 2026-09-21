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

**355 tests, 71 classes, 13 files.** `python tests/run_all.py`, ~15 s, stdlib
`unittest` only.

| File | Tests | Classes | Covers |
|---|---:|---:|---|
| `tests/core/test_enums.py` | 9 | 4 | the closed vocabularies |
| `tests/core/test_locations.py` | 18 | 5 | `SourceSpan` conventions and validation |
| `tests/core/test_contracts.py` | 63 | 8 | entity contracts, referential integrity |
| `tests/core/test_serialization.py` | 24 | 6 | canonical JSON, atomic writes, hash combining |
| `tests/offline/test_snapshot.py` | 16 | 4 | §8 Stage 1 |
| `tests/offline/test_changes.py` | 19 | 3 | §9 Stage 2 |
| `tests/offline/test_parser.py` | 20 | 4 | §10 Stage 3 |
| `tests/offline/test_extractor.py` | 16 | 5 | §11 Stage 4 |
| `tests/offline/test_ir.py` | 47 | 7 | §12 Stage 5, identity, bindings |
| `tests/offline/test_pipeline.py` | 62 | 8 | end-to-end, incremental, publication, §30, model loader, resolution |
| `tests/semantic/test_ladder.py` | 21 | 4 | §13 Stage 6 — the resolution ladder |
| `tests/semantic/test_resolver.py` | 37 | 12 | §13 Stage 6 — resolution end to end |
| `tests/test_docs.py` | 3 | 1 | documentation hygiene guard (D33) |

Counts are measured, not carried over: the per-file figures in this table were wrong
before, so treat any number here as something to re-derive rather than trust. The
current figures come from an AST walk (count `ast.ClassDef` at module level and
`FunctionDef` named `test_*` anywhere) — `python tools/count_tests.py` — which is
what caught the class counts that were stale.

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
| §12 Stage 5 | 6 | 6 | `maat/core/` now has its own module — see §2 |
| §13 Stage 6 | 6 | 6 | `maat/semantic/` — the resolver and the ladder; see §6 |
| §14 Stage 7 | 6 | 0 | M2, not started — the report and severity policy |
| §15 Stage 8 | 6 | 0 | M2, not started — `ModelStore` |
| §16 Stage 9 | 5 | 0 | M3 — preconditions only |
| §19 Stage 12 | 4 | 1 | AC3 only; M1 publishes atomically but there is no version pointer yet |
| §30 Stage 22 | 5 | 5 | fully covered |
| §36 edge matrix | 6 groups | 3 groups | retrieval / reasoning / agent groups are M4+ |

**M1's acceptance surface is fully covered.** Every numbered AC belonging to §8,
§9, §10, §11 and §30 has at least one direct test.

**Overall: 45 of 131 stage-level criteria (34%) are covered** — the remainder
belong to stages that are not built. This is a milestone boundary, not a gap.

The gaps that were inside a built stage's own scope have all been closed:
`maat/core/` now has a test module (§2), the model loader is defensive and
tested (§5), and Stage 6's six acceptance criteria are covered by
`tests/semantic/`. Spec items belonging to stages that do not exist yet — §14
Stage 7 onward — are not gaps; their acceptance criteria belong to stages with
no code in this tree.

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

### The model loader was not defensive — fixed

`load_previous_ir` guarded the JSON parse but not the rehydration that followed it, so a
**structurally** invalid previous model raised `KeyError`, `ValueError` or `TypeError`
out of the index call instead of triggering a full rebuild. The guard now wraps
rehydration too and reports absence, which is what its docstring always promised.

`PreviousModelLoaderTests` in `tests/offline/test_pipeline.py` covers four malformed
shapes, unparseable JSON, a non-object payload, the empty-object case, and — importantly
— that a valid previous model still enables reuse. The four malformed shapes were
measured escaping before the fix, so the tests were written against a real failure.

The empty object is now *measured* benign rather than assumed: it loads, yields nothing
reusable, and every unchanged file is reparsed. Full analysis in
[`decisions.md`](decisions.md) and [`../SECURITY.md`](../SECURITY.md).

### `maat/core/` now has a test module — closed

It previously had none: 1,161 lines covered only indirectly. `tests/core/` now covers
the pieces that were verified-untested, each named explicitly because each was
grep-confirmed as having no direct test:

* `combine_hashes` order-independence — the sharpest case, since it derives every
  `version_id`, exists purely for order-independence, and had **zero** references in
  `tests/`. Also asserted: duplicates still affect the result, so sorting does not
  silently deduplicate.
* `model_digest`, including that it excludes the derived `counts` block.
* `_StrEnum.__str__` returning the bare value, for every member of every vocabulary.
* `FileRecord.problems()` path validation — POSIX-only and repo-relative, which
  matters because this project is developed on Windows.
* `SourceSpan.whole_file` / `point` / `is_zero_width` / `contains_line`.
* `read_json` / `write_json` round trip, atomicity, and that a failed serialisation
  leaves the previous file intact.

Writing these also surfaced that the per-file class counts in this document had been
wrong, which is why §2 now says the counts are measured.

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
not implementation gaps. Stage 6 is now built, so its two criteria — §13 AC3 and
§13 AC5 — have been sharpened below; the rest should be sharpened before the
stage that depends on them is built.

| Criterion | Problem | Sharper form |
|---|---|---|
| **§9 AC5** Rename | Conditional on "where supported" and "when cache policy allows reuse" — satisfiable vacuously by declaring a restrictive policy | "A rename must not change any entity ID that survives the move, and must not require reparsing file contents" |
| **§16 AC3** Transitive traversal | "within depth N" — N is never fixed | State N, or state that N is caller-supplied and that the bound is enforced |
| **§13 AC3** Ambiguous resolution | "Ambiguous" is undefined — ambiguity is a policy decision, not a fact | **Sharpened when Stage 6 was built.** Ambiguity means more than one candidate at equal confidence; the resolver marks the edge `AMBIGUOUS`, records a bounded candidate list (`MAX_CANDIDATES = 8`), and keeps the placeholder target rather than picking one |
| **§21** Intent ambiguity | "must not silently route to an arbitrary strategy" — no threshold for when a query counts as ambiguous | Define the confidence threshold and the clarification response |
| **§25 AC4** Exact relationship validation | "within the defined response policy" — the policy is never defined | Define the policy (for example: exact set equality for `FIND_REFERENCES`) |
| **§13 AC5** No hallucinated relationship | Constrains a mechanism rather than an output; not directly observable | **Sharpened when Stage 6 was built.** Test the proxy: every resolved target exists in the model, the edge count is unchanged by resolution, and confidence agrees with status (exact ⇒ 1.0, ambiguous and unresolved ⇒ 0.0) |
| **§11 AC3** No AST leakage | Structural and negative; only checkable by absence | Enumerate the allowed fact vocabulary exhaustively |
| **§10 AC6** Partial parsing | "Where Tree-sitter provides a usable partial tree" — "usable" is undefined | Define usable as at least one clean top-level statement — **the implementation already does this** |

**§10 AC6 is the model to follow.** The implementation made the undefined word
concrete — "usable" became "at least one clean top-level statement" — and the
behaviour became testable as a result. The other five deserve the same treatment.

---

## 7. Running the checks

```bash
python tests/run_all.py            # 355 tests, exit 1 on failure
python tests/run_all.py -v         # verbose
python tests/run_all.py offline    # substring filter on the test id

python tools/verify_queries.py     # all 18 .scm compile and fire their captures
python tools/verify_bindings.py    # per-language @binding coverage
python tools/count_tests.py        # the 355 / 71 / 13 figures quoted in §2
```

CI runs the first two. `verify_queries.py` matters more than it looks: a malformed
query does not crash the pipeline, it silently degrades extraction.

`count_tests.py` is not a gate — it exists because the figures in §2 are quoted in
several documents, and hand-copied counts drifted twice. Run it before editing a
count, and paste its output rather than adjusting a number by hand.
