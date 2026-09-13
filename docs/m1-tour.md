# M1 Tour — the big picture, fast

A single-pass tour of the offline parser. Read top to bottom; nothing here
requires you to have read anything else. For the deep version with a bug-by-bug
record, see `docs/walkthrough-offline-parser.md`.

---

## 1. The whole thing in sixty seconds

```text
repository path
   → snapshot     decide which files count, hash their bytes
   → changes      compare against last run, decide what to redo
   → parse        tree-sitter, one grammar per language
   → extract      syntax tree → facts (no IDs, no resolved targets)
   → build IR     facts → Symbols, Relationships, Evidence, Chunks
   → publish      canonical JSON, written atomically
```

M1 ends there. **Every reference in the output is marked `UNRESOLVED`** — that is
the design, not an omission. Deciding what `self.repository.save` refers to is
Stage 6, which is M2.

Run it:

```bash
python tools/demo_offline.py tests/fixtures/demo_repo
```

---

## 2. Big picture: three tiers and one rule

```text
                    pipeline.py                     ← orchestration
        ┌───────────────────────────────────┐
        │  Tier 3  SEMANTICS  (canonical)   │
        │  extractors/  ·  ir_builder.py    │       facts → the model
        ├───────────────────────────────────┤
        │  Tier 2  SYNTAX     (disposable)  │
        │  parser.py  ·  queries/*.scm      │       text → syntax trees
        ├───────────────────────────────────┤
        │  Tier 1  ACQUISITION              │
        │  languages · snapshot · changes   │       disk → a stable snapshot
        ├───────────────────────────────────┤
        │  maat/core/   the shared vocabulary and data shapes   │
        └───────────────────────────────────┘
```

### The one rule

> **No language-specific shape may cross the Tier 2 → Tier 3 boundary.**

Tier 2 deals in tree-sitter node types and `.scm` query files — things that differ
per language and are disposable. Tier 3 sees only four language-neutral facts:
`SymbolFact`, `ImportFact`, `CallFact`, `InheritFact`.

**Why this single rule matters more than any other decision:** it is what lets
**one** extractor and **one** IR builder serve 18 languages. Adding a 19th
language means adding one `.scm` file and changing zero Python.

`SymbolFact` has no `node`, no `node_type`, no tree-sitter import at all. There
is nothing language-specific left in it to leak.

---

## 3. The data's journey — one real file

The fastest way to understand a pipeline is to follow one item through it.
This is `services/payment_service.py` from the spec's fixture.

```text
services/payment_service.py                        (bytes on disk)
      │
      │  snapshot.py
      │    os.walk with dirs.sort()/files.sort()  → deterministic order
      │    kept? not ignored, not generated, not binary
      │    content_hash = sha256(raw bytes)
      ▼
FileRecord(path="services/payment_service.py", language="python",
           content_hash="sha256:...", size=...)
      │
      │  changes.py
      │    compare content_hash against the stored manifest
      │    → NEW | CHANGED | DELETED | UNCHANGED
      ▼
ChangeSet(changed=[...], scheduled_for_parse=[...])
      │
      │  parser.py
      │    load_grammar("python")  → cached tree-sitter Parser
      │    tree = parser.parse(source_bytes)
      │    iterative walk: count ERROR / MISSING nodes
      ▼
ParseOutcome(tree, status=OK, diagnostics=[...], root_node=...)
      │
      │  query_extractor.py
      │    Query("python.scm")  →  QueryCursor.matches()
      │    each match pairs  @def.method  +  @name.method
      │    nest by span containment   → parent_qualified_name
      │    reclassify by context      → function inside a class becomes METHOD
      ▼
ExtractionFacts(
    symbols = [SymbolFact("process", METHOD,
                          "services.payment_service:PaymentService.process",
                          span, signature, docstring, parent=...), ...],
    imports = [ImportFact("models.payment", names=["Payment"]), ...],
    calls   = [CallFact("save",     receiver="self.repository"),
               CallFact("validate", receiver="self"), ...],
)
      │        ← no IDs. no resolved targets. nothing language-specific.
      │
      │  ir_builder.py
      │    module modelled as the containment-tree root
      │    symbol_id = sha1(path, type, qualified_name) → "sym_a1b2..."
      │    CONTAINS edges  → RESOLVED_EXACT   (both ends are in this file)
      │    CALLS/IMPORTS/INHERITS → target = "unresolved:<raw text>",
      │                             status = UNRESOLVED, confidence = 0.0
      │    one Evidence row per symbol, chunks per symbol + per file
      ▼
SemanticIR(model_version="mv_...", files, symbols,
           relationships, evidence, chunks, diagnostics)
      │
      │  pipeline.py
      │    _sort_ir()        deterministic ordering of every collection
      │    ir.problems()     referential integrity in one pass
      │    write_json()      tempfile → fsync → os.replace   (atomic)
      ▼
.maat/ir.json  +  .maat/manifest.json
```

Note the asymmetry that defines M1: **`CONTAINS` is resolved, everything else is
not.** `CONTAINS` is provable from a single file — a method really is inside its
class. A call target is not provable from one file, so M1 declines to guess.

---

## 4. Module reference

Skim the "Refuses to" column — those boundaries are the architecture.

### `maat/core/` — the shared vocabulary (1,161 lines)

| Module | Lines | Does | Refuses to |
|---|---|---|---|
| `enums.py` | 151 | Closed vocabularies: parse status, symbol types, relationship types, resolution states | Name derived relationships (`DEPENDS_ON`…), so the model cannot represent a fabricated observation |
| `locations.py` | 104 | `SourceSpan`: 1-based lines, 0-based byte columns, half-open end | Raise on a bad span — malformed spans are *data*, aggregated into a report |
| `ids.py` | 150 | Content-addressed deterministic IDs, SHA-1 truncated to 64 bits | Include `model_version` in an ID (would break incremental reuse) |
| `contracts.py` | 654 | The data shapes: `Symbol`, `Relationship`, `Evidence`, `SemanticChunk`, `SemanticIR`… | Hold tree-sitter objects; each has `problems()` returning strings, never raising |
| `serialization.py` | 112 | Canonical JSON (sorted keys, fixed separators) + atomic writes | Emit timestamps, sets, or `repr` into the model |

### Tier 1 — acquisition (702 lines)

| Module | Lines | Does | Refuses to |
|---|---|---|---|
| `languages.py` | 208 | Path → grammar registry, 61 languages, 60+ extensions | Guess from content — extension and exact filename only |
| `snapshot.py` | 341 | Sorted walk, ignore rules, binary sniffing, content hashing | Silently drop files — every exclusion is recorded with a reason |
| `changes.py` | 153 | Manifest diff, rename detection by content hash | Assume a rename is a delete+add |

### Tier 2 — syntax (358 lines + 18 query files)

| Module | Lines | Does | Refuses to |
|---|---|---|---|
| `parser.py` | 358 | Tree-sitter behind a `ParserBackend` protocol; status classification | Raise on bad syntax — returns a `ParseOutcome` with a status |
| `queries/*.scm` | 18 files | Per-language capture patterns | — (declarative data, no code) |

### Tier 3 — semantics (1,259 lines)

| Module | Lines | Does | Refuses to |
|---|---|---|---|
| `extractors/base.py` | 238 | The fact vocabulary + the `Extractor` protocol | Expose any tree-sitter type |
| `extractors/query_extractor.py` | 538 | Runs queries, pairs captures, nests by containment, attaches docs | Contain a single `if language == ...` branch |
| `ir_builder.py` | 483 | Facts → `SemanticIR`; IDs, evidence, chunks | Resolve a cross-file reference — emits `UNRESOLVED` instead |

### Orchestration (579 lines)

| Module | Lines | Does | Refuses to |
|---|---|---|---|
| `pipeline.py` | 579 | Runs the stages, reuses unchanged files, publishes atomically | Let a failed file stop the run |

---

## 5. The decisions that define M1

Nine choices explain almost all of the code. Each one traded something away.

**1. Tree-sitter with pre-compiled grammars.** ~400 grammars, no build step.
*Cost:* a real external dependency, which overrode the original
"no black-box dependencies" instruction. *Payoff:* 18 languages for the price of
18 declarative files.

**2. One engine, not 18 special cases.** Grammars agree on almost nothing, so the
design exploits three properties instead of branching per language:

- **Pairing by match.** Every pattern captures a declaration *and* its name
  (`@def.class` + `@name.class`) in the same pattern. Necessary because the name
  node's parent is often not the declaration node — C nests names under
  `function_declarator`, Go uses a separate `field_identifier`.
- **Nesting by span containment.** A declaration's parent is the innermost
  declaration whose byte range contains it. No per-language container lists.
- **Reclassification by context.** A function whose enclosing declaration is a
  class, interface or enum becomes a `METHOD`.

**3. `ParserBackend` protocol, with one implementation.** Spec §10 lists "parser
abstraction" as a deliverable, so the seam exists even though only tree-sitter
implements it. *Cost:* one indirection for one implementer.

**4. IDs are content-addressed and version-free.** `sha1(path, type,
qualified_name)` truncated to 16 hex chars, fields joined with `\x1f` (ASCII unit
separator — illegal in paths and qualified names, so `("a","b|c")` and
`("a|b","c")` cannot collide). **`model_version` is deliberately not an input**:
including it would give an *unchanged* symbol a fresh ID on every reindex, which
would break the incremental reuse Stage 21 depends on.

**5. A relationship's ID is keyed on the raw target text, plus line and column.**
Two reasons: one function may call the same target several times, and each call
site has its own evidence; and `f(); g()` on one line is two calls at one line
number, so the column is required or one is silently dropped as a duplicate.
This choice becomes load-bearing in M2 — it is why resolving an edge does not
renumber it.

**6. Failure is data, never an exception.** Nothing in the offline path raises on
bad input. Each file lands on a status ladder — `OK` / `PARTIAL` / `FAILED` /
`EMPTY` / `UNSUPPORTED` — and every degraded file carries a human-readable reason.
A file that fails to parse is isolated; the rest of the repository stays
queryable. *Cost:* callers must check status instead of catching exceptions.

**7. Model version is a pure function of file content.** Reindexing unchanged
content mints no new version and reparses nothing. The parent version is excluded
from the identity, because hashing it would make the second run over an unchanged
repository produce a different version every time. *This is the one decision M2
has to change* — see §7.

**8. Determinism is engineered, not hoped for.** Sorted `os.walk`; byte-level
content hashing; canonical JSON with sorted keys and no sets; a final `_sort_ir`;
no absolute paths or run timestamps anywhere in the model. Two runs produce a
byte-identical `ir.json`.

**9. Iterative tree walking.** An explicit stack rather than recursion, because a
deeply nested file (the fixture has one) would otherwise hit Python's recursion
limit and turn a *parse* problem into a *crash*.

---

## 6. What M1 guarantees

Verified by 137 tests (`python tests/run_all.py`, ~12 s):

| Property | Evidence |
|---|---|
| **Deterministic** | Two runs → byte-identical `ir.json`, same `model_digest` |
| **Idempotent** | Unchanged reindex → same version, 0 files reparsed |
| **Incremental** | Touch 1 file → 1 changed, 1 reparsed, 6 reused |
| **Fault-isolated** | Edge-case repo: 9 degraded files, other 133 unaffected, model valid |
| **Language-neutral** | 18 grammars, 5,044 symbols, one extractor, zero per-language branches |
| **Honest** | Every reference `UNRESOLVED`; every exclusion and degradation reported |

Scale check on the polyglot edge-case repo (156 files, 18 grammars):

```text
142 scanned   5,044 symbols   5,398 relationships   ~500 ms
128 OK   3 PARTIAL   6 FAILED   3 EMPTY   2 UNSUPPORTED
model is valid: no referential or structural problems
```

---

## 7. Where M2 plugs in

M1 deliberately stops at "here is what the source said". M2 decides "here is what
it meant".

**The hard part, in one line:** all four edges of the spec's §7 expected graph
resolve through a receiver whose *type* is only knowable from a binding —
a local variable, an instance field, or a constructor parameter annotation.
`CallFact` records the receiver as raw text (`"self.repository"`) and nothing
more, so Stage 6 cannot resolve any of those four edges without new information.

That is decision **D23**: add a `BindingFact` and a `@bind.*` capture family to
the 18 query files, reusing the exact extension mechanism M1 established.

**And one M1 decision has to change.** Decision 7 above — version identity from
file content only — was correct while the model was a pure function of file
content. Resolution changes the model *without changing any file*, so one content
hash would map to two different models sharing a version ID. That is **D27**.

Both are explained in full in `docs/implementation-plan-resolution.md` §3 and §6.

---

## 8. If you remember five things

1. **Three tiers, one rule:** no language-specific shape crosses into the model.
   That rule is why 18 languages cost one extractor.
2. **M1 observes; it does not infer.** `CONTAINS` is resolved because one file
   proves it. Everything else is `UNRESOLVED` on purpose.
3. **IDs are content-addressed and version-free**, so an unchanged symbol keeps
   its identity — which is what makes incremental work possible.
4. **Failure is data.** Nothing raises; everything is reported with a reason.
5. **Determinism is a tested property**, not an aspiration.
