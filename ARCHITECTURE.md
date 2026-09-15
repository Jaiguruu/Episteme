# Architecture

How Episteme is put together, and **why** each structural choice was made. Read
this before changing anything structural.

For a per-file walkthrough with activity diagrams, see
[`docs/architecture-deep-dive.html`](docs/architecture-deep-dive.html).
For the normative specification, see [`SPEC.md`](SPEC.md).

---

## 1. What the system does

Episteme turns a directory of source code into one **`SemanticIR`** — a
deterministic, versioned, self-validating model of the repository.

```text
repository path
   → snapshot     decide which files count, hash their bytes
   → changes      compare against the last run, decide what to redo
   → parse        tree-sitter, one grammar per language
   → extract      language-neutral facts
   → build IR     facts → symbols, relationships, evidence, chunks
   → publish      write it atomically, or write nothing at all
```

Nothing in that path calls a model, a network, or a database. It reads files,
parses them, and writes JSON.

---

## 2. The three tiers, and the one rule

```text
Tier 1  acquisition   languages.py  snapshot.py  changes.py     files on disk
Tier 2  syntax        parser.py     queries/*.scm               tree-sitter — disposable
Tier 3  semantics     extractors/   ir_builder.py              language-neutral
```

> **The one rule: no language-specific shape may cross the Tier 2 → Tier 3
> boundary.**

Tier 2 deals in tree-sitter node types and `.scm` queries. Tier 3 never sees
them. Tier 3 sees only five language-neutral fact types:

```text
SymbolFact      a declaration: type, qualified name, span, signature, doc
ImportFact      a module reference: module, imported names, alias
CallFact        a call site: callee name, receiver, enclosing symbol
InheritFact     a base-class reference
BindingFact     name → type binding: bound name, type name, scope
```

That rule is the whole reason 18 languages cost **one** extractor and **one** IR
builder. It is also what makes tree-sitter replaceable: the parser sits behind a
`ParserBackend` protocol, and swapping it out would not touch the model.

**Corollary — queries are disposable.** Extraction logic lives in
`maat/offline/queries/<language>.scm`, not in Python. A `.scm` file can be
rewritten or thrown away without touching a single line of the semantic tier.

---

## 3. Module map

```text
maat/core/                    language-neutral contracts. No I/O, no parsing.
  enums.py           174      closed vocabularies — every value is a persisted contract
  locations.py       104      SourceSpan: line 1-based, column 0-based, end exclusive
  ids.py             150      content-addressed stable IDs
  contracts.py       654      FileRecord, Symbol, Relationship, Evidence,
                              SemanticChunk, ModelVersion, SemanticIR, ...
  serialization.py   112      canonical JSON, atomic writes, hash combination

maat/offline/                 the pipeline
  languages.py       208      61-language registry; extractability derived from disk
  snapshot.py        341      sorted walk, ignore rules, binary sniffing, content hashing
  changes.py         153      manifest diffing, content-hash rename detection
  parser.py          358      tree-sitter behind ParserBackend; never raises
  queries/*.scm     1265      18 extraction queries, one per extractable language
  extractors/
    base.py          316      the fact vocabulary + the Extractor protocol
    query_extractor.py 623    one extractor that serves every language
  ir_builder.py      483      facts → validated Symbol/Relationship/Evidence/Chunk
  pipeline.py        579      orchestration, incremental reuse, atomic publication
```

`maat/core/` depends on nothing else in the project. `maat/offline/` depends on
`maat/core/` and never the reverse.

---

## 4. The data that flows

### 4.1 Identity is content-addressed and version-free

Every ID is `sha1(parts joined by "\x1f")[:16]`, with a per-family prefix so an
ID is self-describing:

| Prefix | Entity | Inputs |
|---|---|---|
| `file_` | `FileRecord` | repository-relative path |
| `sym_` | `Symbol` | path, symbol type, qualified name |
| `rel_` | `Relationship` | source ID, relationship type, target key, line, column |
| `ev_` | `Evidence` | symbol ID, source span |
| `chunk_` | `SemanticChunk` | symbol ID, chunk type |
| `mv_` | `ModelVersion` | the digest of all file content hashes |
| `unresolved:` | placeholder target | the raw target text |

Two deliberate omissions:

* **`model_version` is not an input to any ID.** If it were, an unchanged symbol
  would get a new ID on every reindex and incremental reuse would be impossible.
* **`file_id` is path-only, not content-derived.** Hashing the content would make
  every edit change the file's identity, so a file could never be recognised as
  "the same file, changed" — which is exactly what change detection needs.

The cost of path-derived symbol IDs is accepted and explicit: **moving a symbol
to a different file changes its identity**, so a rename *is* reparsed (D16).

### 4.2 The model

`SemanticIR` holds six collections and is the source of truth:

| Collection | Contents |
|---|---|
| `files` | every scanned file: language, content hash, parse status |
| `symbols` | modules, classes, interfaces, enums, functions, methods, fields |
| `relationships` | `CONTAINS`, `IMPORTS`, `CALLS`, `INHERITS` |
| `evidence` | the source span backing each symbol |
| `chunks` | token-bounded slices for later retrieval |
| `diagnostics` | everything the parser or extractor could not fully handle |

Every object exposes `problems() -> list[str]`. An empty list on the root means
the model is structurally and referentially valid.

### 4.3 Observed versus derived

M1 **observes**; it does not infer. Only `CONTAINS` is `RESOLVED_EXACT`, because
containment is structural. Every `IMPORTS` / `CALLS` / `INHERITS` edge is
`UNRESOLVED`, confidence `0.0`, pointing at an `unresolved:` placeholder, with
the raw source text preserved in `target_name`.

That is not an unfinished edge — it is the correct representation of an
observation that has not been resolved yet. Resolution is Stage 6 (M2).

---

## 5. Determinism

Two runs over unchanged content produce a **byte-identical `ir.json`** and an
identical `model_digest`. This is a tested property, not an aspiration.

Enforced by:

* sorted `os.walk` — the directory listing is sorted **in place** before descent
* raw-byte `sha256` content hashing — encoding-independent
* canonical JSON — sorted keys, `ensure_ascii=False`, no sets
* a final `_sort_ir` pass over every collection
* content-derived model versions — never derived from the parent version
* `combine_hashes`, which **sorts before hashing** so collection order cannot leak

**One deliberate exception:** `manifest.json` carries a scan timestamp, so it is
intentionally *not* reproducible. `ir.json` is the artifact with the determinism
guarantee.

**The idempotence property:** reindexing unchanged content does **not** mint a new
model version. `model_version_id` takes exactly one input — the digest of the file
content hashes — so identical content maps to an identical version.

---

## 6. Failure model

> **Failure is data, never an exception.**

Nothing in the offline path raises on bad input. Every file lands on a status
ladder:

```text
OK           parsed cleanly
PARTIAL      parsed, but with error or missing nodes
FAILED       could not produce a usable tree
EMPTY        zero bytes
UNSUPPORTED  no grammar, or no registered language
```

`is_error` is `FAILED` only; `is_degraded` is `PARTIAL | FAILED`. Every degraded
file carries a human-readable diagnostic, and the model exposes a `parse_error`
chunk so the reason is retrievable, not just recorded.

A malformed file is **isolated**: the rest of the repository stays queryable. The
only `raise` sites in `maat/` are programmer/setup errors — a missing grammar, an
uncompilable query, an unserialisable value, a non-directory root argument. None
of them can be triggered by source code being parsed.

The `PARTIAL` / `FAILED` split is decided by one question: **did any top-level
statement parse cleanly?** If yes the tree is usable and the status is `PARTIAL`.
That single predicate is what makes "a usable partial tree" a testable property
rather than a judgement call.

---

## 7. Incremental indexing

`manifest.json` records the previous snapshot. Diffing it yields
`NEW / CHANGED / DELETED / RENAMED / UNCHANGED`, and only affected files pass
through the expensive stages.

```text
run 1  cold           parsed 7   reused 0
run 2  no change      parsed 0   reused 7   same version
run 3  touch 1 file   parsed 1   reused 6   new version, parent recorded
run 4  no change      parsed 0   reused 7   same version as run 3
```

**Rename detection is byte-identical only.** New paths are bucketed by content
hash; deleted paths are walked in sorted order and paired against that bucket. No
similarity heuristic — a content-changed rename is reported as delete + add,
because guessing would be a fabricated relationship.

Reused files have their entities carried forward and **re-stamped**: parse status,
error, node counts and diagnostics come from the previous `FileRecord`, and the
new `model_version` is written onto every entity. Losing a degraded status on
reuse was a real bug (see `docs/decisions.md`).

---

## 8. Publication

The index is written to `<repo>/.maat/`:

```text
manifest.json    the change-detection baseline. Carries a timestamp.
ir.json          the model. Byte-for-byte reproducible.
```

Writes are atomic: `mkstemp` → `flush` → `fsync` → `os.replace`, and the cleanup
handler catches `BaseException` so an interrupt mid-write still unlinks the
temporary file. **A model is published only if `problems()` is empty.** An invalid
build leaves the previous version intact on disk.

---

## 9. Invariants a change must not break

These are the rules that make the design work. Breaking one is an architectural
change, not a refactor.

1. **No language-specific shape crosses Tier 2 → Tier 3.** If you find yourself
   writing `if language == "go"` in `ir_builder.py`, the design has been violated.
2. **The model is the source of truth.** Graph, FTS5 and vector stores are
   projections. No index may become authoritative.
3. **Never let an index become the source of truth for identity.** IDs come from
   content and structure, never from a store's row order or an autoincrement.
4. **Never turn an ambiguous relationship into a confident one without evidence.**
   `AMBIGUOUS` is a correct answer, not a failure to decide.
5. **Failure is data.** New entities expose `problems()`; they do not raise on
   invalid input.
6. **Validation never raises.** Rejection happens by returning problems, before
   publication.
7. **Determinism is a tested property.** Any change to traversal, hashing,
   serialisation or ID derivation needs a test that would catch a regression.
8. **`model_version` is never an input to an ID.**

---

## 10. Where the next milestones plug in

```text
M1  Stages 0–5    snapshot → parse → extract → SemanticIR          DONE
M2  Stages 6–8    resolution → validation → canonical model        next
M3  Stages 9–12   graph / FTS5 / vector projections                not started
M4  Stages 13–18  retrieval and reasoning                          not started
M5  Stages 19–20  MCP tools and the ReAct agent                    not started
M6  Stages 21–24  invalidation, fault tolerance, CLI, end-to-end   not started
```

M2 lands in a **new sibling package, `maat/semantic/`** — not inside
`offline/`. The reason is the tier boundary: the syntax tier must stay free of
meaning, exactly as it does today. M2 upgrades edges rather than changing the
schema, because the `ResolutionStatus` vocabulary, the confidence policy and the
relationship contract already exist.

Two known prerequisites for M2 are documented in
[`docs/decisions.md`](docs/decisions.md): bindings are extracted but never
persisted, and version identity needs a pipeline fingerprint once resolution can
change the model without changing any file.

See [`ROADMAP.md`](ROADMAP.md) for status and where to contribute.
