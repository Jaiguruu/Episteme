# Test → Acceptance-Criteria Matrix

**Status:** M1 complete. 137 tests, 26 classes, 6 files, all passing
(`python tests/run_all.py`, ~14.5 s).

This document answers one question: **for every test in the suite, which
acceptance criterion does it discharge — and which acceptance criteria have no
test at all?**

It is a reference, not a plan. Findings that fall out of the mapping are in
§12 and are the actionable part.

---

## 1. How to read this

The spec (`Problem_doc.md`) numbers acceptance criteria **per stage**, so `AC3`
is ambiguous on its own. Every reference below is written as `§N ACk` where `N`
is the spec section. Where a test guards an invariant that the spec states in
prose rather than as a numbered AC, the mapping names the section and quotes the
line.

Three kinds of row appear:

| Kind | Meaning |
|---|---|
| **AC** | The test is the direct discharge of a numbered acceptance criterion. |
| **Deliverable** | The test covers something the spec lists as a stage *deliverable* but never numbers. |
| **Invariant** | The test guards a cross-cutting guarantee (determinism, honesty, no-leakage) that no single stage owns. |

A test can appear in more than one row. That is normal — `test_ac6_partial_parse_retains_valid_regions`
discharges §10 AC6 *and* supports §30 AC1.

---

## 2. Suite shape

| File | Lines | Tests | Classes |
|---|---:|---:|---|
| `tests/offline/test_snapshot.py` | 182 | 16 | 4 |
| `tests/offline/test_changes.py` | 237 | 19 | 3 |
| `tests/offline/test_parser.py` | 205 | 20 | 4 |
| `tests/offline/test_extractor.py` | 279 | 16 | 5 |
| `tests/offline/test_ir.py` | 357 | 31 | 5 |
| `tests/offline/test_pipeline.py` | 386 | 35 | 5 |
| **Total** | **1 646** | **137** | **26** |

Supporting, not counted as tests:

- `tests/support.py` — `TempRepository` (copy-to-temp with `write`/`append`/`delete`/`rename`),
  `empty_temp_dir()`, `temp_repo(files)` (writes bytes verbatim, so NUL/BOM/CRLF
  fixtures are exact).
- `tests/fixtures/demo_repo/` — the §7 fixture, 7 files.
- `tests/fixtures/edgecase_repo/` — 142 scanned files, 18 languages, 5 044 symbols.
- `tests/run_all.py` — `unittest` discovery, `top_level_dir=PROJECT_ROOT`.

There is **no `tests/core/`**. See finding **F3**.

---

## 3. §7 Stage 0 — Fixtures and Contracts

The spec's Stage-0 acceptance criteria are unusually testable, because two of
them are *about* tests.

| §7 criterion | Discharged by |
|---|---|
| Fixture contains at least one complete call chain | `test_pipeline.py::DemoRepositoryTests::test_expected_chain_is_reachable` (BFS over the produced import graph) |
| Fixture contains direct and transitive dependencies | same, plus `test_expected_module_dependency_graph_is_present` |
| Fixture contains an intentionally broken file | `test_pipeline.py::FaultIsolationTests::test_broken_file_is_degraded_not_fatal` |
| Expected symbols are explicitly defined | `test_pipeline.py::DemoRepositoryTests::test_payment_service_is_a_symbol_with_methods` |
| Expected relationships are explicitly defined | `EXPECTED_MODULE_EDGES` (6 edges) in `test_pipeline.py`, asserted by `test_expected_module_dependency_graph_is_present` |
| Tests can compare produced data against expected data | the whole `DemoRepositoryTests` class |
| No implementation accepted without a behavioral test | structural — see §12 **F3** for the one place this is violated |

**How the expected graph is encoded.** `test_pipeline.py` declares it twice, on
purpose:

- `EXPECTED_MODULE_EDGES` — six module-level `IMPORTS` edges, asserted as a set
  difference so the failure message lists exactly what is missing.
- `EXPECTED_CHAIN` — the four-node path
  `api.checkout_controller → services.checkout_service → services.payment_service → repositories.payment_repository`,
  asserted by reachability rather than by adjacency, so it proves *transitivity*
  instead of re-asserting the edge set.

Note the indirection: the fixture's imports are the module-level statement of the
call chain the spec names. §7's expected graph is drawn with `CheckoutService ↓
PaymentService`; the test asserts the *import* edges and the *call sites* (see
§16 below) separately, because M1 does not resolve calls. That split is
deliberate and is the honest reading of §4.2.

---

## 4. §8 Stage 1 — Repository Snapshot (AC1–AC5)

| §8 AC | Test | What it actually pins |
|---|---|---|
| **AC1** Complete discovery | `SnapshotDiscoveryTests::test_finds_every_source_file` | The exact sorted list of 7 fixture paths. Not "at least N" — the literal set, so an accidentally-included file fails too. |
| **AC1** | `SnapshotDiscoveryTests::test_language_detected_for_every_source_file` | Every record has `language == "python"` and `file_kind == SOURCE`. |
| **AC2** Stable hashes | `SnapshotHashTests::test_hashes_are_stable_across_runs` | Two scans under *different* `model_version` values produce identical `path → content_hash` maps. Version is not part of the content hash. |
| **AC3** Content sensitivity | `test_content_change_changes_the_hash` | `value = 1` → `value = 2` changes it. |
| **AC3** | `test_line_ending_change_changes_the_hash` | `\n` → `\r\n` changes it. This is the one that justifies **raw-byte** hashing: the parser sees different bytes, so treating it as unchanged would let the model drift from disk. |
| **AC3** | `test_whitespace_only_edit_changes_the_hash` | Trailing newline changes it. |
| **AC4** Non-source filtering | `SnapshotFilteringTests::test_binary_generated_and_ignored_files_are_excluded` | Nine-file matrix. Asserts both the kept set and the *reason* for each exclusion, per category. |
| **AC4** | `test_pruned_directories_are_reported` | `node_modules` appears in `excluded`. A silently-skipped directory is indistinguishable from a missing one. |
| **AC4** | `test_non_code_language_is_unsupported_not_source` | `.json` → `FileKind.UNSUPPORTED` + `ParseStatus.UNSUPPORTED`. |
| **AC4** | `test_unknown_extension_is_unsupported` | `.xyzzy` → `language is None`, status `UNSUPPORTED`. |
| **AC4** | `test_empty_source_file_is_empty_not_failed` | Empty `.py` → `EMPTY`, **not** `FAILED`. Also a precondition for §10 AC3. |
| **AC4** | `test_ignoring_can_be_disabled` | `SnapshotOptions(ignore_directories=frozenset())` keeps `node_modules/x/y.js`. Proves filtering is *configuration*, not hard-coded. |
| **AC5** Deterministic snapshot | `SnapshotDeterminismTests::test_manifest_is_byte_identical_across_runs` | Compares `canonical_json(manifest_payload(...))` across runs — byte-level, not structural. |
| **AC5** | `test_files_are_sorted_by_path` | `paths == sorted(paths)`. |
| — Deliverable | `test_records_carry_the_requested_version` | `model_version` field is honoured per-record (§8 field list). |
| — Invariant | `test_non_directory_raises` | `NotADirectoryError` on a file path. Guard, not an AC. |

**The `README.md` nuance.** `test_binary_generated_and_ignored_files_are_excluded`
asserts `README.md` is *kept* while asserting it is non-code. §8 AC4 says
"ignored/generated/binary files are excluded" — it does not say "non-source files
are excluded". The test encodes that distinction explicitly, so the two
categories (`UNSUPPORTED` but present, vs. `excluded`) can never be conflated.

---

## 5. §9 Stage 2 — Incremental Change Detection (AC1–AC6)

The fixture is three files `a.py`, `b.py`, `c.py`, each one line.

| §9 AC | Test | What it actually pins |
|---|---|---|
| **AC1** Initial indexing | `ChangeDetectionTests::test_ac1_initial_index_schedules_everything` | `previous=None` → 3 new, 3 scheduled, `changed == []`. |
| **AC2** No-change run | `test_ac2_no_change_schedules_nothing` | `is_empty`, `scheduled_for_parse == []`, 3 unchanged. |
| **AC3** Single modification | `test_ac3_single_modification_schedules_one` | Exactly `["b.py"]` in both `changed` and `scheduled_for_parse`; other 2 unchanged. |
| **AC4** Deletion | `test_ac4_deletion_is_detected` | `deleted == ["c.py"]`, and **nothing is scheduled** — a deletion requires no parse. |
| **AC5** Rename | `test_ac5_rename_detected_by_content` | `renamed == [("c.py", "renamed.py")]`, not double-counted as delete+add, **and scheduled for parse**. |
| **AC5** | `test_rename_with_edited_content_is_not_a_rename` | Editing then moving yields `renamed == []`, `deleted == ["c.py"]`, `new == ["renamed.py"]`. Only byte-identical moves count — a similarity heuristic would lie. |
| **AC5** | `test_rename_pairing_is_deterministic_with_duplicate_content` | Two files with identical content, both renamed. Two runs must produce the *same* pairing. Guards the sorted one-to-one pairing in `_detect_renames`. |
| **AC6** Interrupted update | `ManifestPersistenceTests` (5 tests) | See below. |
| — Deliverable | `test_statistics_are_reported` | `statistics()` returns `new`/`changed`/`unchanged`/`scheduled` consistently. |

### AC6 — the read half and the write half

§9 AC6 says an interrupted indexing operation must not publish an incomplete
semantic version. It is discharged in **two files**, and the split is worth
knowing:

| Half | Test | Mechanism |
|---|---|---|
| Read: never trust a half-written manifest | `test_round_trip` | Write `manifest_payload` → `load_manifest` → 3 entries, `manifest_version == "mv_1"`. |
| | `test_missing_manifest_is_treated_as_initial_index` | Missing → `None`. |
| | `test_truncated_manifest_is_treated_as_absent` | `'{"entries": [{"path": "a.py", "conte'` → `None` for both `load_manifest` and `manifest_version`. |
| | `test_wrong_shape_is_treated_as_absent` | `[1, 2, 3]` → `None`. |
| | `test_corrupt_manifest_makes_everything_new` | `"not json"` → everything is `new`. Safe direction: rebuild, never abort. |
| Write: never leave a partial artifact | `test_pipeline.py::PersistenceTests::test_atomic_write_leaves_no_temporary_files` | No `.tmp-*` residue after `index()`. |

**The asymmetry this creates is a real defect — see F1.**

### §39 Step 3 counters — `PipelineChangeIntegrationTests` (6 tests)

This class exists to assert the numbers §39 Step 3 expects to *see*, end to end
rather than at the `diff_snapshot` level.

| Test | Asserts |
|---|---|
| `test_first_run_parses_everything` | `files_parsed == 7`, `files_reused == 0` |
| `test_second_run_reparses_nothing` | `files_parsed == 0`, `files_reused == 7`, `changes.is_empty` |
| `test_single_file_edit_reparses_exactly_one` | `parsed == 1`, `reused == 6`, `changed == ["services/payment_service.py"]`, new version id, `parent_id == first.version.id` |
| `test_unchanged_repository_keeps_the_same_version` | Idempotent reindex must **not** manufacture a new version |
| `test_reused_entities_are_restamped_to_the_new_version` | No entity in symbols/relationships/evidence/chunks carries a stale `model_version` (§19 AC3) |
| `test_deleted_file_entities_disappear` | After deleting `refund_service.py`, neither the file record nor any `RefundService` symbol survives (§9 AC4's "entities become stale") |

---

## 6. §10 Stage 3 — Tree-sitter Parsing (AC1–AC6)

| §10 AC | Test | What it actually pins |
|---|---|---|
| **AC1** Valid file | `ParserStatusTests::test_ac1_valid_file_parses_ok` | `OK`, `has_tree`, `error_node_count == 0`, `missing_node_count == 0`. |
| **AC2** Syntax error | `test_ac2_syntax_error_does_not_raise` | Wholly-broken source yields `PARTIAL` or `FAILED` and non-empty diagnostics. |
| **AC2** | `test_wholly_broken_file_is_failed` | The `FAILED` end of the ladder, with diagnostic code `parse.no_clean_statements`. |
| **AC3** Empty file | `test_ac3_empty_file_is_handled` | `EMPTY`, `has_tree` false, `node_count == 0`. |
| **AC3** | `test_ac3_whitespace_only_file_is_empty` | Whitespace-only is also `EMPTY`. |
| **AC4** Unsupported language | `test_ac4_unknown_grammar_is_unsupported` | `UNSUPPORTED`, no tree, diagnostic `parse.grammar_unavailable`. |
| **AC5** Source locations | `test_ac5_locations_are_preserved` | The `class_definition` node maps to `start_line == 4` (1-based, matching editors), `start_col == 0`, `end_line >= start_line`, `is_valid()`. |
| **AC6** Partial parsing | `test_ac6_partial_parse_retains_valid_regions` | `PARTIAL`, with `node_count > 0` **and** `error_node_count > 0` — i.e. the valid region survives alongside the error. |

### Diagnostics — §10 deliverable "Parse error capture"

| Test | Asserts |
|---|---|
| `test_diagnostics_name_the_file_and_language` | Every diagnostic carries `file_path` and `language`. |
| `test_diagnostics_carry_a_location` | Located diagnostics exist and have `start_line >= 1`. |
| `test_diagnostic_count_is_bounded` | 500 broken lines with `max_diagnostics=10` → at most 11 emitted. A catastrophically broken file must not produce unbounded output. |

### §36 Parser edge-case matrix

§36 lists: empty file, malformed syntax, partial AST, unsupported language, large
file, generated file.

| §36 item | Test | Note |
|---|---|---|
| empty file | `test_ac3_empty_file_is_handled` (+ whitespace variant) | |
| malformed syntax | `test_ac2_syntax_error_does_not_raise`, `test_wholly_broken_file_is_failed` | |
| partial AST | `test_ac6_partial_parse_retains_valid_regions` | |
| unsupported language | `test_ac4_unknown_grammar_is_unsupported` | |
| large file | `test_large_file_parses` | 3 000 functions, `node_count > 10 000`. |
| **generated file** | — | Covered at the **snapshot** layer (`test_binary_generated_and_ignored_files_are_excluded`), not the parser layer. Consistent with the design: generated files are excluded before a parser ever sees them. |

Extra robustness not named in §36 but present:

| Test | Guards |
|---|---|
| `test_deep_nesting_does_not_exhaust_recursion` | 300 nested blocks → tree >600 deep, `max_depth > 300`, status `OK`. This is the test that forces the explicit-stack walk in `_walk_iteratively`; a recursive walk raises `RecursionError`. |
| `test_unicode_identifiers_parse` | `π`, `café`, `Données` |
| `test_utf8_bom_does_not_break_parsing` | BOM prefix |
| `test_crlf_line_endings_parse` | `\r\n` source |
| `test_missing_trailing_newline_parses` | no final newline |
| `test_invalid_utf8_bytes_do_not_raise` | `\xff\xfe` in a comment |

### §10 deliverable "Parser abstraction" / "Language registry"

| Test | Asserts |
|---|---|
| `test_every_registered_code_language_has_a_loadable_grammar` | Iterates `LANGUAGE_SPECS`, calls `load_grammar` on every code language, collects failures. This is the test that proves the 18 extractable + 39 parse-only grammars actually load. |
| `test_grammar_objects_are_cached` | `load_grammar("python") is load_grammar("python")`. |

---

## 7. §11 Stage 4 — Language Extractors

§11's criteria are unnumbered. Three sentences:

> `PaymentService` must be extracted as a symbol.
> The system must identify `CheckoutService → PaymentService` and
> `RefundService → PaymentService` as candidate call relationships.
> No language-specific AST structure should leak into the canonical semantic model.

| §11 criterion | Test | What it actually pins |
|---|---|---|
| `PaymentService` extracted as a symbol | `ExtractorSymbolTests::test_payment_service_is_extracted_as_a_symbol` | `services.payment_service:PaymentService` present in the fact set. |
| Two call edges as candidates | `ExtractorRelationshipTests::test_call_candidates_are_identified` | Both call sites produce `target_name == "self.payment_service.process"`, and each is attributed to its **enclosing method** (`CheckoutService.checkout`, `RefundService.refund`). |
| No AST structure leaks | `NoLeakageTests::test_facts_expose_no_tree_sitter_objects` | `repr(facts.to_dict())` contains none of `Node`, `tree_sitter`, `start_byte`, `end_byte`, `type=`. |
| No AST structure leaks | `test_fact_vocabulary_is_language_neutral` | Every fact field is a plain Python type / enum; `not hasattr(symbol, "node")`. |

### Deliverable coverage

| §11 deliverable | Test |
|---|---|
| Symbol extraction | `test_module_symbol_is_always_present` (MODULE is always symbol[0]), `test_methods_are_distinguished_from_functions` (METHOD vs FUNCTION), `test_nesting_produces_parent_links` (method→class→module chain), `test_signature_skips_decorators` (`def helper` present, `@staticmethod` absent) |
| Documentation extraction | `test_docstring_is_attached` |
| Import extraction | `test_imports_are_grouped_per_statement` (one fact per statement, `names == ["Payment"]`, `alias == "Pay"`), `test_bare_import_with_alias_promotes_module` (`import ujson as json`) |
| Class/interface extraction (inheritance) | `test_multiple_base_classes_are_all_captured` (`class A(Base, Mixin, Serializable)` → all three; a single capture binds a list) |
| Call/reference hygiene | `test_expression_receivers_are_dropped` (`obj.first().second()` — a non-identifier receiver is dropped) |
| Interface replaceability | `test_all_extractable_languages_yield_symbols_and_calls` (every language with a `.scm` yields ≥2 symbols and ≥1 import), `test_language_without_query_reports_a_diagnostic` (`extract.no_query` diagnostic, exactly 1 symbol — no invented declarations) |
| Module naming | `ModuleNamingTests::test_module_path_derivation` (`pkg/__init__.py → pkg`, `src/api/index.ts → src.api`, `rust/src/mod.rs → rust.src`) |

**`test_all_extractable_languages_yield_symbols_and_calls` is the load-bearing
one.** It derives the language list from the filesystem
(`languages.extractable_languages()`), pulls each sample from
`tools/dump_trees.SAMPLES`, and asserts every language produces facts. Because
the list is derived rather than hard-coded, **dropping a new `.scm` into
`maat/offline/queries/` automatically extends this test's coverage** — and
fails if the new query is inert.

**Gap:** §11 lists *References* and *Implementations* as extraction targets.
Neither is produced. See **F4**.

---

## 8. §12 Stage 5 — Semantic IR

Six unnumbered criteria. Also the core entities (Symbol, Relationship,
SemanticChunk, Evidence) each get a class.

| §12 criterion | Test | What it actually pins |
|---|---|---|
| Identical source → stable entity IDs | `IdentityTests::test_identical_source_produces_identical_ids` | Same source twice → same `qualified_name → id` map. |
| Different symbols do not collide | `test_different_symbols_do_not_collide` | `len({s.id}) == len(symbols)` |
| | `test_same_name_in_different_files_does_not_collide` | Path is part of the ID preimage. |
| | `test_same_name_different_kind_does_not_collide` | Symbol type is part of the ID preimage. |
| | `test_overloads_are_disambiguated` | Two `process` methods → 2 distinct IDs. |
| | `test_overload_disambiguation_is_stable` | …and the disambiguation is reproducible. |
| | `test_qualified_names_are_well_formed` | Non-module symbols contain `:`. |
| Relationships reference valid entities | `test_relationship_pointing_at_a_missing_symbol_is_rejected` | `sym_missing` → "does not exist". |
| | `test_relationship_ids_are_unique` | |
| | `test_two_calls_on_one_line_get_distinct_ids` | `return g(); g()` — line alone is not enough to identify a call site; the column is in the ID. |
| Evidence references valid source locations | `test_every_symbol_has_evidence` | Every symbol ID appears in `evidence.entity_id`. |
| | `test_evidence_points_at_real_lines` | `1 <= start_line <= end_line <= line_count`. |
| | `test_evidence_is_labelled_as_offline_provenance` | `retrieval_source == "offline.ast"`. |
| | `test_evidence_belongs_to_the_model_version` | |
| Every semantic entity belongs to a model version | `test_ids_are_independent_of_model_version` | Version is an *attribute*, not part of identity — otherwise incremental reuse is impossible. |
| | `test_pipeline.py::DemoRepositoryTests::test_no_entity_references_another_version` | |
| | `test_changes.py::PipelineChangeIntegrationTests::test_reused_entities_are_restamped_to_the_new_version` | |
| Invalid objects rejected before indexing | `ValidationTests` (6 tests) | See below. |
| — SemanticChunk entity | `ChunkTests` (6 tests) | See below. |
| — **The M1 "never guess" invariant** | `RelationshipTests` (6 tests) | See below. |

### `RelationshipTests` — the §4.2 / §13 AC4–AC5 foundation

This class is where M1's central honesty guarantee is pinned. It is *not* a §13
test — §13 is M2 — but it is the thing that makes §13 AC5 satisfiable later.

| Test | Asserts |
|---|---|
| `test_contains_is_resolved_exactly` | Every `CONTAINS` is `RESOLVED_EXACT` with `confidence == 1.0`. Containment is structural, so it is known with certainty. |
| `test_references_are_unresolved` | Every **non**-`CONTAINS` relationship is `UNRESOLVED`, `confidence == 0.0`, and carries a `target_name`. |
| `test_unresolved_targets_use_the_placeholder_scheme` | Their target IDs satisfy `is_unresolved_target` — the `unresolved:` prefix. |
| `test_calls_are_recorded_with_their_site` | `self.validate` is present as a `CALLS` target. |

The pairing of `test_contains_is_resolved_exactly` with `test_references_are_unresolved`
is what makes "M1 emits only `CONTAINS` as resolved" a *tested* claim rather than
a comment. Combined with `ValidationTests::test_confidence_must_match_resolution_status`,
the status↔confidence contract is enforced from both directions: the builder
never produces an inconsistent pair, and the contract rejects one if it appears.

### `ValidationTests` — "invalid objects rejected before indexing"

| Test | Rejects |
|---|---|
| `test_built_model_has_no_problems` | (control) a real built model yields `problems() == []` |
| `test_relationship_pointing_at_a_missing_symbol_is_rejected` | referential integrity |
| `test_symbol_referencing_a_missing_file_is_rejected` | referential integrity |
| `test_invalid_symbol_is_rejected_before_indexing` | empty `name`, malformed `qualified_name` |
| `test_invalid_location_is_reported` | `start_line 5 > end_line 2` → "precedes" |
| `test_duplicate_ids_are_detected` | duplicate detection |
| `test_confidence_must_match_resolution_status` | `UNRESOLVED` with `confidence 0.8` |

### `ChunkTests` — the SemanticChunk entity

| Test | Asserts |
|---|---|
| `test_symbols_produce_chunks` | Every chunk's `symbol_id` is a real symbol. |
| `test_imports_chunk_is_always_present` | An `imports` chunk exists even when there are no imports. |
| `test_imports_chunk_says_when_there_are_none` | …and its text says "no imports" rather than being silently empty. |
| `test_parse_error_chunk_appears_for_degraded_files` | A `parse_error` chunk appears for broken files. |
| `test_chunk_text_is_the_symbol_source` | The `class` chunk for `PaymentService` contains `class PaymentService`. |
| `test_token_counts_are_positive` | Non-empty chunks have `token_count > 0`. |

---

## 9. §13 Stage 6 — Resolution (AC1–AC6) — **M2, not covered**

Explicitly out of M1 scope. Recorded here so the boundary is unambiguous: **no
test in this suite discharges a §13 acceptance criterion.**

| §13 AC | Status in M1 |
|---|---|
| AC1 Exact resolution | Not implemented. No resolver exists. |
| AC2 Namespace separation | *Half* covered — `test_same_name_in_different_files_does_not_collide` and `test_duplicate_class_names_across_files_stay_distinct` prove two same-named classes get distinct IDs. That is the **identity** half. The **resolution** half (a reference to `Shared` picks the right one) is M2. |
| AC3 Ambiguous resolution | Not implemented. |
| AC4 Unknown target | *Pre-satisfied by construction* — M1 emits every reference as `UNRESOLVED` with a placeholder target, which `test_references_are_unresolved` and `test_unresolved_targets_use_the_placeholder_scheme` pin. M1 satisfies AC4 trivially; M2 must satisfy it *selectively* (resolve what is knowable, leave the rest unresolved). |
| AC5 No hallucinated relationship | *Pre-satisfied by construction* — M1 creates no relationship it did not observe, and `test_confidence_must_match_resolution_status` rejects a confident-but-unresolved pair. Same caveat: M2 must preserve this while adding resolution. |
| AC6 Relationship provenance | Partially — every entity has `Evidence` (`test_every_symbol_has_evidence`), but no test asserts that a *resolved relationship* points at its source evidence, because no resolved relationship exists. |

**Reading AC4/AC5 as "already done" would be a mistake.** They are satisfied at
M1 only because M1 resolves nothing. They are the constraints M2 must not break,
not criteria M2 can inherit as met.

---

## 10. §16 Stage 9 — Graph Projection (AC1–AC5) — **M3, preconditions only**

No graph projection exists. But three tests deliberately stop one step short of
it, asserting that the *data* the projection will need is already present.

| §16 AC | Precondition test | Why it is not AC coverage |
|---|---|---|
| AC1 Direct callers | `test_both_callers_of_payment_service_are_visible` | Asserts both call **sites** exist as unresolved `CALLS` facts with `target_name == "self.payment_service.process"`. The docstring is explicit: "M1 does not resolve the edges, but both call sites must already be present as facts or the resolver would have nothing to work with." `find_callers` does not exist. |
| AC2 Direct callees | — | Same fact set as AC1; no separate test. |
| AC3 Transitive traversal | `test_expected_chain_is_reachable` | Performs a BFS **inside the test** over the import graph. This proves the graph *supports* the traversal; it does not exercise a traversal API. |
| AC4 Cycles | `test_cyclic_imports_are_represented_without_hanging` | Asserts `a→b` and `b→a` both exist as edges and that indexing terminates. Terminating on a cycle is not the same as *traversing* one. |
| AC5 Version consistency | `test_no_entity_references_another_version`, `test_published_artifacts_agree_on_the_version` | The semantic-model half of version consistency. The graph-projection half (graph version == model version) has no graph to check. |

---

## 11. §19 Stage 12 — Atomic Index Publication, and §30 Stage 22 — Fault Tolerance

### §19 (AC1–AC4)

| §19 AC | Status |
|---|---|
| AC3 All published indexes reference the same model version | **Covered.** `PersistenceTests::test_published_artifacts_agree_on_the_version` compares `manifest["model_version"]` against `ir.json`'s and against every file record. Reinforced by `test_reused_entities_are_restamped_to_the_new_version` and `test_no_entity_references_another_version`. |
| AC1 No query observes mixed versions | Not covered — there is one artifact (`ir.json`), not a set of indexes. |
| AC2 Failed validation leaves V1 active | Not covered. |
| AC4 Active version identifiable by one lookup | Not covered as an AC, but `manifest_version()` reads it in one call. |

### §30 Fault Tolerance (AC1–AC5) — fully covered

The `broken/broken_service.py` fixture exists for this stage.

| §30 AC | Test |
|---|---|
| **AC1** One malformed file does not stop indexing | `FaultIsolationTests::test_broken_file_is_degraded_not_fatal` + `test_other_files_remain_healthy_and_queryable` + `EdgeCaseRepositoryTests::test_malformed_files_are_isolated` |
| **AC2** Broken file marked `FAILED` or `PARTIAL` | `test_broken_file_is_degraded_not_fatal` |
| **AC3** Error is persisted | `test_broken_file_error_is_persisted` (diagnostics **or** `parse_error` survives into the model) + `test_every_degraded_file_is_reported_with_a_reason` |
| **AC4** Other files remain queryable | `test_other_files_remain_healthy_and_queryable` (exactly 6 healthy, all `OK`) |
| **AC5** Fixing the file allows successful reindex | `test_fixing_the_file_clears_the_degradation` (rewrite → `OK`, `files_parsed == 1`) |

Supporting:

| Test | Guards |
|---|---|
| `test_valid_regions_of_the_broken_file_are_kept` | §10 AC6 at pipeline level — `BrokenService` is still extracted from a broken file. |
| `test_reindexing_a_binary_corrupted_file_keeps_the_model_valid` | A source file that turns binary mid-project is *excluded*, not crashed on. Asserts `excluded["models/payment.py"] == "BINARY"` and `file_by_path` returns `None`. |
| `EdgeCaseRepositoryTests::test_malformed_files_are_isolated` | ≥5 degraded, but `< 20 %` of all files — degradation stays a minority. |

### Determinism (cross-cutting, §4.1)

| Test | Asserts |
|---|---|
| `test_two_runs_produce_an_identical_model` | `model_digest` equality. |
| `test_two_runs_produce_identical_json` | `canonical_json` equality — stronger, catches key-order and float-formatting drift. |
| `test_serialised_model_contains_no_timestamps` | None of `created_at`, `taken_at`, `2026-`, `T00:` appear. |
| `test_edgecase_repository_is_deterministic` | Same guarantee at 142 files / 18 languages. |
| `test_index_directory_is_not_scanned` | `.maat` is in `IGNORED_DIRECTORIES` — otherwise the index would grow every run. |

---

## 12. Findings

These are the actionable output of the mapping. Nothing here is fixed yet.

### F1 — Structurally corrupt `ir.json` aborts the whole index run (defect)

`load_previous_ir` (`pipeline.py:129`) documents:

> A corrupt file is treated as absent, matching the manifest policy: the safe
> direction to fail is to rebuild from scratch rather than to abort.

That promise holds only for **syntactically** invalid JSON. The guard is

```python
try:
    with open(path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
except (OSError, ValueError):
    return None
if not isinstance(payload, dict):
    return None
return _ir_from_payload(payload)   # <-- outside the guard
```

`_ir_from_payload` does raw `raw["start_line"]`, enum construction, and
attribute access. Probed behaviour:

| Malformation | Result |
|---|---|
| missing required field on an entity | `KeyError: 'path'` |
| unknown enum value | `ValueError: 'BOGUS' is not a valid ParseStatus` |
| entity is not a dict | `TypeError: string indices must be integers` |
| collections are the wrong type | `TypeError: 'int' object is not iterable` |
| `{}` | **accepted** — returns an empty `SemanticIR` |

Every one of those propagates out of `index()`.

Contrast `load_manifest` (`changes.py:30`), which is defensive at *every* level:
bad JSON → `None`, non-dict → `None`, `entries` not a list → `None`, and
individual entries filtered by `isinstance(entry, dict) and "path" in entry and
"content_hash" in entry`.

**Consequences.**

1. `load_previous_ir`'s docstring contradicts `_ir_from_payload`'s docstring,
   which says a silent field rename *should* "break loudly here rather than
   corrupt a model". Both cannot be true. One of them is wrong.
2. The realistic trigger is not mid-write truncation (`os.replace` is atomic) but
   **schema drift across code versions** — an `ir.json` written by an older build,
   then read by a newer one. That is exactly the upgrade path M2 will exercise
   when the persisted schema grows.
3. `index()` calls it at `pipeline.py:361`, gated on `previous_manifest` being
   truthy. So a corrupt manifest is safe, but a *good* manifest plus a
   structurally-corrupt `ir.json` takes the process down — which is precisely
   what §30's isolation principle forbids.
4. `{}` being accepted as a valid empty model is a smaller issue: the
   `else` branch at `pipeline.py:390` re-parses files that are absent from the
   model, so it degrades to a full reparse rather than losing entities. But
   `files_reused` would report `0` while the manifest says "unchanged", so the
   statistics would be misleading rather than wrong.

**No test covers any of this.** `PersistenceTests` tests atomic *writes* and
never a malformed *read*.

### F2 — `maat/core/` has no test module

`maat/core/` is 1 161 lines (`enums`, `locations`, `ids`, `contracts`,
`serialization`) and is only ever exercised transitively through `tests/offline/`.
Grep-verified untested surface:

| Symbol | Coverage |
|---|---|
| `combine_hashes` | **zero references in `tests/`** — yet it derives every `version_id`, and its entire purpose is order-independence. |
| `model_digest` | used only for two-run equality; the "pop `counts`" behaviour is untested. |
| `FileRecord.problems()` | never called directly — the absolute-path / Windows-separator guard is untested. |
| `SourceSpan.whole_file` / `is_zero_width` / `contains_line` | never referenced. |
| `read_json` / `write_json` | never referenced directly; atomic round-trip is only implied by pipeline tests. |
| `_StrEnum.__str__` (bare value) | never asserted. |

The `tests/core/` slice is planned but not started. Given §35's "no implementation
accepted without a corresponding behavioral test", `combine_hashes` is the
sharpest example: it is the function that makes incremental reuse possible, and
nothing pins its order-independence.

### F3 — `§11` "References" and "Implementations" are neither produced nor tested

`RelationshipType.REFERENCES` and `RelationshipType.IMPLEMENTS` exist in
`maat/core/enums.py` and have **zero** references in `maat/offline/` and **zero**
in `tests/`. §11 lists both as extraction targets.

These are the declared-but-unused contract members already flagged in
`MEMORY.md` as forward-looking schema. The finding is not that they are unused —
it is that §11 *asks for them*, so either the spec over-reaches for M1 or the
extractor is short. Worth an explicit decision rather than leaving it implicit.

### F4 — §36 "changed dependency target" and §4.6 invalidation are unimplemented

Grep for `invalidat|stale|dependency` across `maat/offline/*.py` returns **zero
hits**. §4.6 is titled "Incremental Processing Must Account for Relationship
Invalidation" and §36 lists `changed dependency target` as a required edge case.

`_reuse` (`pipeline.py:507`) carries an unchanged file's entities forward and
re-stamps only `model_version` and `file_id`. There is no mechanism by which a
change to file B invalidates relationships recorded in unchanged file A.

**Defensible for M1** — M1 emits every cross-file reference as `UNRESOLVED` with a
raw-text target, so nothing in A can *become* wrong when B changes. **Not
defensible for M2**, which is exactly when resolved cross-file edges appear. This
should be an explicit M2 acceptance item, not a discovered surprise.

### F5 — `BindingFact` is produced, never consumed, never tested

`bindings` appears in `maat/offline/extractors/base.py`,
`extractors/query_extractor.py` and the `.scm` files — and nowhere in
`ir_builder.py` or `pipeline.py`. So:

1. `build_file_ir()` never reads `facts.bindings`;
2. `SemanticIR` has no bindings collection;
3. `_group_by_file()` does not bucket them.

Bindings do not survive into `ir.json`. Corroborating evidence: `test_extractor.py:12`
imports `BindingScope` and **never uses it** — a dead import, and no test asserts
any binding behaviour.

This reshapes **D23**: the capture half is already implemented; the missing half
is consumption plus persistence, which touches the persisted schema.

### F6 — AC-interpretation note: §9 AC5 (rename)

AC5 reads:

> A renamed file does not unnecessarily trigger semantic recomputation when
> content is unchanged **and cache policy allows reuse**.

M1's cache policy does **not** allow reuse for a rename, and
`test_ac5_rename_detected_by_content` asserts the opposite of "no recomputation":

```python
self.assertIn("renamed.py", change_set.scheduled_for_parse)
```

with the comment "symbol IDs are path-derived, so the entities must be rebuilt
against the new path". This is a **compliant** reading — the AC is conditional —
but it means a pure rename counts as a parse in `files_parsed`. Since it is a
decision rather than an accident, it belongs in the decision log rather than
only in a test comment.

### F7 — §7 deliverable "Expected semantic graph" is inlined, not a file

`tests/fixtures/` contains only `demo_repo/` and `edgecase_repo/`. There is no
`expected_graph.py`. The expected graph lives as `EXPECTED_MODULE_EDGES` and
`EXPECTED_CHAIN` at the top of `test_pipeline.py`.

Arguably better — the expectation sits next to the assertion that uses it, and
cannot drift out of sync with a separate module. But it diverges from the §7
deliverable list, and `TODO.md` should say so explicitly rather than leaving it
looking unbuilt.

### F8 — §35's prescribed test tree is not followed

§35 prescribes:

```text
tests/offline/
├── snapshot/
├── changes/
├── parser/
├── extraction/
├── resolution/
├── validation/
└── versioning/
```

Actual: flat `tests/offline/test_*.py`, six files. `tests/core/` does not exist
(see F2). Purely structural, but it is a §35 divergence and it is what makes F2
easy to overlook — there is no directory whose absence is visible.

### F9 — `tests/fixtures/demo_repo/.maat/` is a leftover index directory

The fixture directory contains a committed `.maat/`. The fixture should be
pristine; a stray index dir is exactly the kind of thing that makes a test pass
for the wrong reason later. Not currently harmful —
`test_index_directory_is_not_scanned` uses `TempRepository`, not the fixture —
but it should be removed before `git init`.

### F10 — Documentation drift (carried over, still unfixed)

Recorded in `TODO.md` §6 and reproduced here because the test mapping confirms it:

| Claim | Where | Measured |
|---|---|---|
| `node_count=143, max_depth=7` | `docs/walkthrough-offline-parser.md` §3 Step 3, line 396 | The line describes `services/payment_service.py`. `node_count` is **correct (143)**; `max_depth` is **9**, not 7. |
| "13 exclusion entries (5 directories + 8 files)" | `docs/walkthrough-offline-parser.md` §7 bug 4, line 693 | **14** — `IGNORED 10`, `GENERATED 3`, `BINARY 1`. 142 scanned + 14 = **156**, which reconciles. The doc's own arithmetic does not: 142 + 13 = 155 ≠ 156. |
| `edgecase_repo` in 497 ms | docs | 4 457 ms — **not comparable**, first run pays grammar loading |

Measured per-file figures for the fixture, for future reference:

```text
node_count  depth  errors  status    path
        63      9       0  OK        api/checkout_controller.py
        58      8       2  PARTIAL   broken/broken_service.py
        57      7       0  OK        models/payment.py
        79      7       0  OK        repositories/payment_repository.py
       113     10       0  OK        services/checkout_service.py
       143      9       0  OK        services/payment_service.py
       105     10       0  OK        services/refund_service.py
```

Note `max_depth == 7` is correct for two *other* files (`models/payment.py`,
`repositories/payment_repository.py`), which is likely how the error arose.
Separately, `test_deep_nesting_file_does_not_crash_the_pipeline` asserts
`max_depth > 300` for `_edge/deep_nesting.py` — a different fixture entirely.

---

## 13. Coverage summary

| Spec stage | ACs | Directly covered | Notes |
|---|---|---:|---|
| §7 Stage 0 | 7 | 7 | expected graph inlined (F7) |
| §8 Stage 1 | 5 | 5 | |
| §9 Stage 2 | 6 | 6 | AC6 split across two files (F1) |
| §10 Stage 3 | 6 | 6 | |
| §11 Stage 4 | 3 | 3 | References/Implementations missing (F3) |
| §12 Stage 5 | 6 | 6 | `maat/core/` itself untested (F2) |
| §13 Stage 6 | 6 | 0 | M2 — AC4/AC5 pre-satisfied only |
| §16 Stage 9 | 5 | 0 | M3 — preconditions only |
| §19 Stage 12 | 4 | 1 | AC3 only |
| §30 Stage 22 | 5 | 5 | |
| §36 edge matrix | 6 groups | 3 groups | resolution/retrieval/reasoning/agent are M2+ |
| §39 Step 3 | — | counters asserted | |

**M1's acceptance surface is fully covered.** Every numbered AC belonging to
§8, §9, §10, §11 and §30 has at least one direct test. The gaps are (a) one
untested defect in the *loader* (F1), (b) `maat/core/` having no home in the test
tree (F2), and (c) spec items that M1 legitimately defers (F3, F4, §13, §16, §19).

---

## 14. How to run

```bash
# everything
python tests/run_all.py

# one file
python -m unittest tests.offline.test_ir -v

# by pattern
python tests/run_all.py test_ir
```

Use the managed interpreter that has tree-sitter installed:

```text
C:/Users/MOTOROLA/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe
```

The bare `python` on `PATH` does not have tree-sitter.
