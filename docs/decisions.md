# Design Decisions

Why the system is shaped the way it is. Each entry records the decision, the
reason, and **what was traded away** — the last column is the one that matters
when you are deciding whether a decision still holds.

This is the durable record extracted from the M1 and M2 implementation plans.
Entries D1–D22 shipped in M1; D23–D32 were taken during M1 planning and D23, D24,
D25, D26, D27, D28, D29, D30 and D31 are now implemented in M2 (Stage 6); D33–D36
were taken after M1 shipped.

---

## Part 1 — Technology and extraction

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| **D1** | Tree-sitter + `tree-sitter-language-pack` | ~400 grammars with no build step | An external dependency; superseded the original no-dependency constraint |
| **D2** | Keep a `ParserBackend` protocol | Spec §10 lists "parser abstraction" as a deliverable | One indirection with a single implementer |
| **D3** | Extraction via declarative `.scm` queries, not per-language Python | Adding a language becomes a data change, not a code change | Query syntax is a second language to learn |
| **D4** | Two captures per definition pattern (`@def.*` + `@name.*`) | The name node's parent is often *not* the declaration node (C, Go) | Slightly noisier queries |
| **D5** | Nesting derived from **span containment**, not a per-language container list | No language metadata to maintain; works for every grammar | O(n log n) per file |
| **D6** | Methods reclassified by enclosing container | Kotlin, Swift, Scala, Dart, C++ and Python cannot distinguish this in the query | One rule instead of six |

---

## Part 2 — Identity and data

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| **D9** | `sha256` over raw bytes for content hashing | Encoding-independent; catches line-ending changes | Cannot detect "reformatted but equivalent" |
| **D10** | Entity IDs exclude `model_version` | §12 AC1 wants stable IDs; Stage 21 needs incremental reuse. Including the version would renumber every symbol on every reindex | Moving a symbol changes its ID |
| **D11** | Version ID derived from content hashes **only**, never from the parent | Makes an unchanged reindex idempotent (§9 AC2) | Two identical repositories share a version ID (harmless, scoped to the index directory) |
| **D12** | Overload collisions disambiguated by signature hash | Java and C# overloads share a qualified name | IDs differ from the simple case only where collisions exist |
| **D13** | `CONTAINS` is `RESOLVED_EXACT`; every reference is `UNRESOLVED` | Containment is structural, not a reference (§4.2) | The graph is not connected until M2 |
| **D14** | Relationship ID includes line **and** column | `f(); g()` on one line are two distinct call sites | None |
| **D15** | Evidence produced eagerly at build time | §13 AC6 and §41 Rule 3 | A larger model |
| **D19** | `dataclasses` + explicit `problems()`, not pydantic | Avoids a dependency; §12 AC6 wants rejection *before* indexing | Hand-written validation |

---

## Part 3 — Failure, determinism and change

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| **D7** | `ParseStatus` as data, never exceptions | §30 AC1 requires file-level isolation | Callers must check status |
| **D8** | `PARTIAL` / `FAILED` split on "did any top-level statement parse?" | §10 AC6 wants a usable partial tree, not just a flag. This makes "usable" concrete and therefore testable | Recovery can mis-attribute a diagnostic |
| **D16** | Renamed files **are** reparsed | Symbol IDs are path-derived, so a rename changes identity | Deviates from §9 AC5's *permission* to reuse; the recomputation is necessary, not gratuitous |
| **D17** | Pruned directories are recorded as exclusions | "Why is my file missing?" must be answerable | A larger snapshot payload |
| **D18** | Generated-path markers kept conservative (`/gen/` removed) | A false positive silently drops real source code | Some generated code stays in the model |
| **D20** | `unittest`, not pytest | No third-party test dependency | Less ergonomic assertions |
| **D21** | Index written atomically (temp file + `os.replace`) | §9 AC6, §19 AC2, §34 | None |

---

## Part 4 — Model shape

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| **D22** | The module is modelled as the root declaration | Gives top-level symbols a parent and module docstrings a home, with no special cases | One synthetic symbol per file |

---

## Part 5 — M2 decisions (taken during M1 planning, implemented in Stage 6)

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| **D23** | Extend Stage 4 with `BindingFact` | §7's expected graph is unsatisfiable without field and local type information | M2 reaches back into M1's extractor; 17 query files still need `@bind.*` patterns |
| **D24** | Resolution as a precedence ladder (S1–S9), not a score | The status *is* the explanation; auditable; confidence stays a declared policy | The ordering is a judgement call and must be documented |
| **D25** | `target_name` retained forever | Keeps `relationship_id` stable across resolution | Redundant storage — a resolved edge carries both raw text and an ID |
| **D26** | `candidate_symbol_ids` on `Relationship` | §13 AC3 wants ambiguity *marked*, but the candidates are the useful part | One more list on a hot contract |
| **D27** | Version identity gains a pipeline fingerprint | Resolution changes the model without changing any file, so one content hash would map to two different models sharing a version ID | Existing version IDs change; artifacts must be regenerated |
| **D28** | Ambiguous edges keep the `unresolved:` placeholder target | Avoids inflating edge counts and breaking M3's `find_callers` | Callers must check `resolution_status` before using `target_symbol_id` |
| **D29** | Unresolved edges are reported, never failed | §4.2 treats an explicit unresolved edge as correct behaviour | Validation reports are noisier; severity distinguishes info from error |
| **D30** | `maat/semantic/` as a sibling of `offline/` | Keeps the syntax tier free of meaning, mirroring M1's tier boundary | One more package |
| **D31** | Instance receivers as one shared frozenset | `self` / `this` / `cls` is a linguistic fact, not a grammar rule | A hardcoded vocabulary in one file |
| **D32** | Stage 8 stops short of atomic publication | The pointer switch and rollback are explicitly Stage 12 | `ModelStore` is a stepping stone, not the final store |

Implemented so far: **D23–D31** (Stage 6). Still open: **D32** (Stage 8, in progress).

---

## Part 6 — Bugs found during M1

Recorded because each one changed the design or the tests, and because the
distribution is the argument for having more than one way of finding bugs.

| # | Bug | How it surfaced | Fix |
|---|---|---|---|
| 1 | `QueryCursor.matches()` was iterated as flat `(node, name)` pairs | `ValueError: too many values to unpack` | Rewrote against the real shape: `(pattern_index, {capture: [nodes]})` |
| 2 | Taking only the first node per capture | Review of the fix for #1 — it would have dropped every base class after the first | Iterate the node lists where multiplicity is real |
| 3 | `/gen/` treated as a generated-code marker | A histogram showed 2 Java files instead of 10 | Removed the ambiguous marker; conservative by default (D18) |
| 4 | Pruned directories were not reported | Exclusion counts did not add up: 156 files on disk, 142 scanned, but only 8 exclusions — 5 directories had been pruned silently | Record pruned directories as exclusions (D17) |
| 5 | Early `return` when a file had no declarations | `import ujson as json` alone yielded zero imports | Removed the guard; the module root is a valid attachment point |
| 6 | Version ID included the parent | An unchanged reindex produced a new version | Content-only version identity (D11) |
| 7 | Parser diagnostics never reached the model | `test_broken_file_error_is_persisted` | Propagate `outcome.diagnostics` into the IR |
| 8 | `parse_error` set only for `FAILED` | Degraded `PARTIAL` files had no recorded reason | Set it for any degraded status |
| 9 | Parse status and diagnostics lost on incremental reuse | `test_index_files_are_written_and_reloaded` — the degraded count went 1 → 0 | Carry the previous `FileRecord`'s outcome and the file's diagnostics forward |
| 10 | `self._current_root` referenced but never assigned | Reading the code back while writing tests | Threaded `root` through as a parameter instead of instance state |
| 11 | Dead validation branch (`X and not X`) | Review | Replaced with real confidence/status consistency checks |
| 12 | Module docstrings had nowhere to attach | A smoke test showed only the class docstring | Module modelled as the containment root (D22) |

Bugs 1–5 were found by running the code against real inputs; 6–9 by the test
suite; 10–12 by reading the code back. That distribution is the argument for
having all three.

---

## Part 7 — Defects

Known and measured. Three were found during or after M1 and are now **fixed**; the rest
are open. Listed here rather than only in an issue tracker because one of them
constrains M2's design.

### The `load_previous_ir` guard was incomplete — fixed

`load_previous_ir` promised that a corrupt previous model is treated as absent and
triggers a full rebuild. That held for **syntactically** invalid JSON, but the guard
wrapped only the parse — the rehydration step sat outside it. A missing field raised
`KeyError`, an unknown enum value raised `ValueError`, and a malformed entity raised
`TypeError`; all of them propagated out of the index call. The asymmetry was the defect:
`load_manifest` in the same codebase is defensive at every level.

**The fix** wraps rehydration in the same contract, catching narrowly
(`AttributeError`, `KeyError`, `TypeError`, `ValueError`) so a drifted model degrades to
absence and triggers a rebuild. Measured before the fix, all four shapes escaped;
measured after, all four rebuild. `PreviousModelLoaderTests` in
`tests/offline/test_pipeline.py` covers it — including one test guarding the opposite
failure, that a *valid* previous model still enables reuse, because a guard that
over-catches would be a worse and quieter defect than the one it fixed.

**A correction to the original analysis.** This entry used to claim that an empty object
`{}` "is silently accepted as an empty model", implying harm. That is now measured and
false: `{}` is structurally valid so it does load, but it yields no reusable entities,
so every unchanged file falls through to the parse branch and is rebuilt. The outcome is
identical to treating the model as absent, and it is asserted as benign rather than left
as an assumption.

The realistic trigger remains **schema drift across versions**, not a truncated write —
publication is atomic, so a half-written `ir.json` cannot be observed. See
[`../SECURITY.md`](../SECURITY.md).

### Bindings are captured but never persisted — fixed

The capture half of D23 was done first: `BindingFact` existed, `python.scm` emitted the
`@bind.*` patterns, and the extractor produced them. The missing half was everything
downstream, and it was closed by D34:

* `ir_builder.build_file_ir()` now reads `facts.bindings` and emits a `Binding` per
  resolvable fact, dropping unresolvable ones with an `ir.invalid_binding` diagnostic
  rather than raising
* `SemanticIR.bindings` is the collection they persist into
* `pipeline._group_by_file()` buckets them, so incremental reuse re-stamps them instead
  of losing them

Consequence, now measured: **bindings survive into `ir.json`.** The `demo_repo` extractor
produces 15 facts, the model holds 15, and 15 are written to disk. Four of the twelve
`demo_repo` `CALLS` edges still need Stage 6 resolution, and three of those four are in
the spec's own §7 expected chain — persisting the facts is the prerequisite for that
work, not the work itself.

### `maat/core/` has no dedicated test module — closed

Was 1,161 lines covered only indirectly through `tests/offline/`. Now has
`tests/core/` (four modules, 114 tests): `test_enums.py`, `test_locations.py`,
`test_contracts.py`, `test_serialization.py`. The previously grep-verified untested
behaviours are now asserted directly — `combine_hashes` order-independence,
`_StrEnum.__str__` returning the bare value, `FileRecord.problems()` path validation
(POSIX-only and repo-relative, the cross-platform guard that matters on this Windows
checkout), `SourceSpan.whole_file` / `point` / `is_zero_width` / `contains_line`, and
the absence of derived relationship types from `RelationshipType`.

Measuring the coverage revealed two documented per-file class counts were themselves
wrong (`docs/verification.md` claimed 6 classes for `test_parser.py` and 8 for
`test_extractor.py`; the real counts are 4 and 5). They are corrected there, and the
counts in both docs are now AST-measured rather than hand-maintained.

### `tools/demo_offline.py --touch` mutates a committed fixture

It appends to a fixture file and does not revert it. It should copy to a temporary
directory first.

### Reserved contract members

Declared but unused, reserved for later stages. **Do not delete these without a
decision:** `ChangeKind`, `RECOVERY_STATEMENT`, `SymbolType.PARAMETER` /
`VARIABLE` / `IMPORT`, `RelationshipType.REFERENCES` / `IMPLEMENTS`.

---

## Part 8 — Documentation

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| **D33** | Do not quote concrete `model_version` values in documentation | A version ID is a digest of the raw bytes of every scanned file (D9), so it varies with line-ending policy and with any fixture edit. Quoted values went stale without anything being wrong: the IDs in `README.md` and `docs/testing.md` did not reproduce on a `core.autocrlf=true` checkout, while the symbol and relationship counts printed beside them did. A number a reader cannot reproduce is worse than no number — it invites distrust of the figures that *are* correct | The docs lose a concrete example of what an ID looks like, and a future version-compatibility table must identify versions some other way. `tests/test_docs.py` enforces this, so documenting one now fails the suite |
| **D34** | Persist bindings as a first-class collection on `SemanticIR` | D23 captured bindings in Tier 2 but nothing carried them across the Tier 3 boundary, so Stage 6 could not resolve a member call and the whole path was unbuildable. A `Binding` entity with a `bind_*` content-addressed ID (same scheme and same never-input-`model_version` rule as every other entity) closes it without putting any language-specific shape in `ir_builder.py` — the builder consumes `BindingFact` like any other fact | `SemanticIR` grows from six collections to seven, so the persisted shape changes and `EXPECTED_COLLECTIONS` now guards the loader against a payload written by an earlier build. That guard matters more than the collection: without it a 0.1.0 model loads, is reused, and silently yields a new model missing a whole collection while carrying the *identical* `model_version` ID. The guard treats any payload missing a collection as stale and rebuilds |

---

## Part 9 — M2 implementation (taken and implemented)

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| **D35** | Resolution is opt-in (`index(..., resolve=False)` by default) | M1's output must stay reproducible bit-for-bit, and resolution changes the version ID (D27). Making it opt-in keeps "what does the offline pipeline produce" a stable question, makes the stage boundary visible at the call site, and lets every existing test keep asserting M1 behaviour without a flag. A separate `PIPELINE_FINGERPRINT_RESOLVED` constant records which pipeline ran, so a model is self-describing | Two fingerprints to maintain, and a caller who wants the resolved model must know to ask for it. A default of `True` would have been friendlier and would have silently changed every documented figure in the repository |
| **D36** | Follow an unannotated alias one hop when resolving a receiver's type | The common constructor-injection shape records two bindings under one name: the parameter (annotated, `repository: PaymentRepository`) and the attribute (an alias, `self.repository = repository`, recorded as `repository: repository`). Taking the first match by emission order is arbitrary; refusing to follow the alias loses a genuinely resolvable edge (`PaymentService.process → PaymentRepository.save`). The rule is language-neutral — "a type name that is also a bound name is an alias" — and bounded to one hop, so it cannot loop | A resolver that follows aliases can, in principle, follow a wrong one. Bounded to a single hop within the same two scopes (caller body, then constructor), and confirmed by a test that the resulting edge lands on the right method |