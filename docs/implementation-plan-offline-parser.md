# Implementation Plan — M1: Offline Parser

**Spec:** [`Problem_doc.md`](../Problem_doc.md) v1.0 · Stages 0–5 (§7–§12)
**Status:** **Implemented** — 137 tests passing
**Revision:** 2. Supersedes v1, which proposed a hand-written parser. See §1.

**Deliverable of M1:** a deterministic, fault-tolerant pipeline that turns a
repository directory into validated, language-neutral **Semantic IR**, with
malformed files isolated rather than fatal.

---

## 1. Decisions taken (revision 2)

Revision 1 of this plan flagged a conflict: the spec mandates Tree-sitter
(§2 Goal 1, §10), while the brief called for no black-box dependencies. Three
decisions were taken and this document reflects them:

| # | Decision | Consequence |
|---|---|---|
| **D-A** | **Tree-sitter is used**, via `tree_sitter_language_pack` (v1.19, ~400 pre-compiled grammars) | Parsing is grammar-driven, not hand-written. No lexer. |
| **D-B** | **Work stays inside `Episteme/`** | `MAAT - test/` and `MAAT v1/` are untouched and unused. |
| **D-C** | **A larger polyglot repository is used** for edge cases | `tools/make_edgecase_repo.py` generates 156 files across 18 grammars (142 scanned, 13 exclusion entries). |

The `ParserBackend` protocol from revision 1 was kept even though only one
backend now exists. It costs nothing and it is what the spec asks for as a
deliverable (§10, "Parser abstraction").

### What this changes about the design

The original plan had a three-tier architecture with a hand-written lexer and
recursive-descent parser in Tier 2. Tier 1 (acquisition) and Tier 3 (semantics)
are unchanged. Tier 2 collapsed to a single adapter module, and the work that
would have gone into a Python grammar moved into **declarative query files** —
one `.scm` per language — which is a better outcome: adding a language is now a
data change, not a code change.

---

## 2. Architecture

Three tiers, with a hard rule: **language-specific shapes never cross the
second boundary.**

```text
┌──────────────────────────────────────────────────────────────────────┐
│ TIER 1 — ACQUISITION                          (no parsing knowledge) │
│                                                                      │
│  languages.py         snapshot.py            changes.py              │
│  path → grammar       scan, hash, classify   manifest diff           │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ FileRecord + raw bytes
┌───────────────────────────────▼──────────────────────────────────────┐
│ TIER 2 — SYNTAX                    (grammar-specific, disposable)    │
│                                                                      │
│  parser.py            queries/<lang>.scm                             │
│  tree-sitter adapter   declarative extraction queries                │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ ParseOutcome (tree + status + diagnostics)
┌───────────────────────────────▼──────────────────────────────────────┐
│ TIER 3 — SEMANTICS                     (language-neutral, canonical) │
│                                                                      │
│  extractors/base.py          extractors/query_extractor.py           │
│  Extractor protocol          captures → ExtractionFacts              │
│                                                                      │
│  ir_builder.py               core/contracts.py                       │
│  facts → Semantic IR         Symbol / Relationship / Evidence / ...  │
└──────────────────────────────────────────────────────────────────────┘
```

### Module layout

```text
maat/
├── core/
│   ├── enums.py            ParseStatus, SymbolType, RelationshipType, ResolutionStatus, ...
│   ├── locations.py        SourceSpan
│   ├── ids.py              content-addressed, deterministic ID generation
│   ├── contracts.py        FileRecord, Symbol, Relationship, Evidence, SemanticChunk, ...
│   └── serialization.py    canonical JSON + atomic writes
└── offline/
    ├── languages.py        extension → grammar registry (61 languages, 60+ extensions)
    ├── snapshot.py         deterministic scan, hashing, classification, exclusions
    ├── changes.py          manifest diff, content-hash rename detection
    ├── parser.py           ParserBackend protocol + TreeSitterParser
    ├── queries/            18 verified .scm files + README
    ├── extractors/
    │   ├── base.py         Extractor protocol + fact dataclasses
    │   └── query_extractor.py   the generic capture→fact engine
    ├── ir_builder.py       facts → validated, ID-stable entities
    └── pipeline.py         orchestration, versioning, incremental reuse
```

---

## 3. Language coverage

Three tiers, all derived from the filesystem so coverage can never drift from
reality:

| Tier | Languages | What works |
|---|---|---|
| **Extractable** (18) | python, javascript, typescript, tsx, java, go, rust, c, cpp, csharp, ruby, php, kotlin, swift, scala, lua, bash, dart | Full parse + symbols, imports, calls, inheritance, docs |
| **Parse-only code** (39) | elixir, erlang, haskell, ocaml, clojure, perl, r, julia, nim, zig, gdscript, groovy, fsharp, vb, powershell, batch, objc, asm, solidity, proto, thrift, graphql, sql, hcl, dockerfile, make, cmake, css, scss, html, vue, svelte, xml, json, yaml, toml, markdown, rst, csv | Parsed, status reported, **no symbols** — reported honestly via a `extract.no_query` diagnostic |
| **Data / config** (4) | ini (`.ini`, `.cfg`), gitignore (`.gitignore`), gomod (`go.mod`), requirements (`requirements.txt`) | Matched by exact filename or extension; `is_code=False`, so they are never treated as symbol sources and never counted as degraded |

Total: **61** declared grammars — `len(LANGUAGE_SPECS)` — of which 18 are
extractable.

A language is extractable exactly when `maat/offline/queries/<key>.scm` exists.
Dropping in a query file upgrades it with no code change.

The `is_code=False` tier exists so that config files are still *parsed and
reported* rather than silently dropped, while never polluting the symbol graph.
It is the reason `LANGUAGE_SPECS` (61) is larger than the sum of the two code
tiers (18 + 39 = 57).

---

## 4. Data flow

```text
repository path
      │  snapshot.py      os.walk, sorted, ignore rules, binary sniff
      ▼
FileRecord[]  ── path, language, content_hash, size, parse_status, model_version
      │  changes.py       diff against persisted manifest
      ▼
ChangeSet     ── {NEW, CHANGED, DELETED, UNCHANGED, RENAMED} + statistics
      │  parser.py        tree-sitter parse + status classification
      ▼
ParseOutcome  ── tree, ParseStatus, Diagnostic[], node_count, max_depth
      │  query_extractor.py   .scm captures → facts
      ▼
ExtractionFacts ── SymbolFact[], ImportFact[], CallFact[], InheritFact[]
      │  ir_builder.py    IDs, validation, evidence, chunks
      ▼
Semantic IR   ── Symbol[], Relationship[], Evidence[], SemanticChunk[]
```

### Worked trace — `services/payment_service.py`

```python
"""Payment domain service."""
from models.payment import Payment
from repositories.payment_repository import PaymentRepository


class PaymentService:
    def process(self, payment: Payment) -> bool:
        if not self.validate(payment):
            return False
        self.repository.save(payment)
        return True
```

| Step | Output |
|---|---|
| Snapshot | `FileRecord(path="services/payment_service.py", language="python", content_hash="sha256:…", size=…)` |
| Parser | `OK`, 143 nodes, max depth 7 |
| Query | captures: `def.class`=PaymentService, `name.class`, `def.method`×2, `import.module`×2, `import.name`×2, `call.attr`+`call.recv`×2 |
| Extractor | `SymbolFact(CLASS, "services.payment_service:PaymentService")`, `SymbolFact(METHOD, "…:PaymentService.process")`, `ImportFact(module="models.payment", names=["Payment"])`, `CallFact(target="self.validate")`, `CallFact(target="self.repository.save")` |
| IR builder | `Symbol` entities with stable IDs; `CONTAINS` edges `RESOLVED_EXACT`; `IMPORTS`/`CALLS` edges `UNRESOLVED` with `target_name` preserved |

The last row is the point of §4.2: **M1 records syntax; it does not pretend to
know semantics.** The resolver in M2 upgrades `UNRESOLVED → RESOLVED_EXACT`.

---

## 5. Error handling

**One rule governs the whole tier: no function in Tier 2 or Tier 3 raises on
malformed input.** Failure is data, not an exception (§30 AC1).

| Status | When | What happens |
|---|---|---|
| `OK` | No error or missing nodes | Full extraction |
| `PARTIAL` | Some top-level statement parsed cleanly | Valid regions extracted, file marked degraded |
| `FAILED` | No top-level statement parsed cleanly | File recorded, error persisted, zero symbols |
| `EMPTY` | No tokens | Not an error |
| `UNSUPPORTED` | No grammar, or a non-code format | Not an error |

Status decision, in order:

```text
language unknown / grammar unavailable   -> UNSUPPORTED
file has no tokens at all                -> EMPTY
no error and no missing nodes            -> OK
root is one ERROR node, or no top-level
    statement parsed cleanly             -> FAILED
otherwise                                -> PARTIAL
```

`PARTIAL` vs `FAILED` is the load-bearing distinction: a file with one broken
function among ten good ones yields nine usable symbols; a file where nothing
matched yields nothing and says so.

---

## 6. Determinism rules

Required by §8 AC5 and §12 AC1, enforced by convention and asserted by test:

1. `os.walk` with `dirs.sort()` and `files.sort()` — never filesystem order.
2. `content_hash` over **raw bytes** — encoding-independent, line-ending-sensitive.
3. Canonical JSON: sorted keys, no timestamps, no sets in output.
4. All collections sorted at the end of the pipeline (`_sort_ir`).
5. No absolute paths, machine names or run timestamps in the IR.

Verified by `test_pipeline.DeterminismTests`, which asserts two runs produce an
identical model digest and identical JSON.

### The one deliberate exception: `manifest.json`

`ir.json` is byte-for-byte reproducible. `manifest.json` is **not**, and that is
intentional. The manifest is a *record of a scan event*, not a model artifact, so
it carries `taken_at` — the wall-clock time the scan ran. Two runs six seconds
apart differ in exactly one field:

```text
ir.json         IDENTICAL
manifest.json   differs only in taken_at
                entries       identical (same paths, same content hashes)
                model_version identical (mv_72dfca7b6037c080)
```

The separation is enforced structurally, not by convention: `SemanticIR` stores
only `model_version: str` — the version **ID** — never the `ModelVersion` object,
whose `created_at` field would otherwise leak a timestamp into the model. That is
why `test_serialised_model_contains_no_timestamps` can assert that `created_at`,
`taken_at` and `2026-` appear nowhere in the serialised IR.

---

## 7. Design decisions log

| # | Decision | Rationale | Trade-off accepted |
|---|---|---|---|
| D1 | Tree-sitter + language pack | Spec §2/§10; ~400 grammars with no build step | External dependency (superseded the original no-dependency constraint by decision) |
| D2 | `ParserBackend` protocol retained | Spec §10 lists "parser abstraction" as a deliverable | One indirection with a single implementer |
| D3 | Extraction via declarative `.scm` queries, not per-language Python | Adding a language becomes a data change | Query syntax is a second language to learn |
| D4 | Two captures per definition pattern (`@def.*` + `@name.*`) | The name node's parent is often *not* the declaration node (C, Go) | Slightly noisier queries |
| D5 | Nesting derived from **span containment**, not a per-language container list | No language metadata to maintain; works for every grammar | O(n log n) per file |
| D6 | Methods reclassified by enclosing container | Kotlin/Swift/Scala/Dart/C++/Python cannot distinguish in the query | One rule instead of six |
| D7 | `ParseStatus` as data, never exceptions | §30 AC1 requires file-level isolation | Callers must check status |
| D8 | `PARTIAL`/`FAILED` split on "did any top-level statement parse" | §10 AC6 wants a usable partial tree, not just a flag | Recovery can mis-attribute a diagnostic |
| D9 | `sha256` over raw bytes | Encoding-independent, catches line-ending changes | Cannot detect "reformatted but equivalent" |
| D10 | IDs exclude `model_version` | §12 AC1 (stable IDs) vs Stage 21 (incremental reuse) | Moving a symbol changes its ID |
| D11 | Version ID derived from content hashes **only**, not from the parent | Makes an unchanged reindex idempotent (§9 AC2) | Two identical repos share a version ID (harmless, scoped to the index dir) |
| D12 | Overload collisions disambiguated by signature hash | Java/C# overloads share a qualified name | IDs differ from the simple case only where collisions exist |
| D13 | `CONTAINS` is `RESOLVED_EXACT`, all references `UNRESOLVED` | Containment is structural, not a reference (§4.2) | The graph is not connected until M2 |
| D14 | Relationship ID includes line **and column** | `f(); g()` on one line are two call sites | None |
| D15 | Evidence produced eagerly at build time | §13 AC6, §41 Rule 3 | Larger model |
| D16 | Renamed files **are** reparsed | Symbol IDs are path-derived, so a rename changes identity | Deviates from §9 AC5's *permission*; the recomputation is necessary, not unnecessary |
| D17 | Pruned directories are recorded as exclusions | "Why is my file missing?" must be answerable | Larger snapshot payload |
| D18 | Generated-path markers kept conservative (`/gen/` removed) | A false positive silently drops real source | Some generated code stays in the model |
| D19 | `dataclasses` + explicit `problems()`, not pydantic | Avoids a dependency; §12 AC6 wants rejection before indexing | Hand-written validation |
| D20 | `unittest`, not pytest | No third-party test dependency | Less ergonomic assertions |
| D21 | Index written atomically (temp file + `os.replace`) | §9 AC6, §19 AC2, §34 | None |
| D22 | Module modelled as the root declaration | Gives top-level symbols a parent and module docstrings a home, with no special cases | One synthetic symbol per file |

---

## 8. Test plan (spec §35, RED → GREEN)

137 tests, `unittest`, run with `python tests/run_all.py`.

| File | Covers | Spec AC |
|---|---|---|
| `test_snapshot.py` | discovery, hash stability, hash sensitivity, filtering, determinism | §8 AC1–AC5 |
| `test_changes.py` | initial, no-change, modify, delete, rename, interrupted | §9 AC1–AC6 |
| `test_parser.py` | valid, syntax error, empty, unsupported, locations, partial, deep nesting, BOM, CRLF, unicode, large file | §10 AC1–AC6, §36 |
| `test_extractor.py` | PaymentService symbol, both call edges, multi-base capture, cross-language coverage, no leakage | §11 AC |
| `test_ir.py` | ID stability, no collision, overloads, referential integrity, evidence, chunks | §12 AC |
| `test_pipeline.py` | §7 expected graph, fault isolation, determinism, edge-case repo, persistence | §7, §30 |

---

## 9. What M1 deliberately does NOT do

* no symbol **resolution** — references are `UNRESOLVED` (M2, Stage 6)
* no graph / FTS5 / vector indexes (M3)
* no LLM, intent classifier, or agent (M4–M5)
* no relationship-level incremental invalidation — file-level only (Stage 21)
* no CLI (Stage 23)
* no visualization

---

## 10. Known limitations

Honest boundaries, all documented in `maat/offline/queries/README.md`:

* Nested functions inside methods are not captured (queries anchor to module and
  class bodies).
* Python `__init__` and PHP `__construct` are reported as methods, not
  constructors.
* Ruby `def` is always a method; a non-literal `require` is not captured.
* Lua has no class or field concepts to extract.
* Kotlin constructors are nameless in the grammar.
* Shell variable assignments are approximated as fields; quoted `source` is missed.
* Parse-only languages produce a module symbol and an explicit diagnostic, not
  symbols.
