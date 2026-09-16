# Glossary

The project uses a dense, specific vocabulary. This is the definition list.

---

## Notation used across the docs

| Form | Meaning |
|---|---|
| **§n** | A section of [`../SPEC.md`](../SPEC.md). `§10` is "Stage 3: Tree-sitter Parsing". |
| **ACn** | A numbered acceptance criterion inside a spec section. `§9 AC5` is the fifth criterion of §9. |
| **E00n** | A named end-to-end scenario, `E001`–`E005`, in §32. |
| **Dn** | A design decision, `D1`–`D32`. See [`decisions.md`](decisions.md). |
| **Mn** | A delivery milestone, `M1`–`M6`. See [`../ROADMAP.md`](../ROADMAP.md). |
| **Stage n** | One of the spec's 25 implementation stages. Stage 0–5 is M1. |

---

## The system

**MAAT** — Repository Intelligence Agent. The whole system: an offline knowledge
plane plus an online query and reasoning plane.

**Episteme** — the offline knowledge plane, and what this repository implements.
It turns a repository into a semantic model. It is *not* the whole of MAAT.

**Tier 1 — acquisition.** Files on disk become a snapshot with content hashes.
`languages.py`, `snapshot.py`, `changes.py`.

**Tier 2 — syntax.** Files are parsed with tree-sitter grammars via declarative
queries. `parser.py`, `queries/*.scm`. **Disposable** — this tier is replaceable.

**Tier 3 — semantics.** Syntax becomes language-neutral facts, and facts become the
model. `extractors/`, `ir_builder.py`.

**The one rule** — no language-specific shape may cross the Tier 2 → Tier 3
boundary. Tier 3 never sees a tree-sitter node type. This is why 18 languages cost
one extractor.

**Offline / online plane** — the offline plane builds knowledge; the online plane
(retrieval, reasoning, MCP) uses it. Only the offline plane exists today.

---

## The model

**`SemanticIR`** — the canonical semantic model, and the source of truth. Six
collections: `files`, `symbols`, `relationships`, `evidence`, `chunks`,
`diagnostics`. Every index is a projection of it.

**`Symbol`** — a declaration: module, class, interface, enum, function, method,
constructor, field, type alias.

**`Relationship`** — an edge between symbols. `CONTAINS`, `IMPORTS`, `CALLS`,
`INHERITS` are produced; `REFERENCES` and `IMPLEMENTS` are declared but unused.

**`Evidence`** — the source span backing a symbol. Every symbol has one, and
`retrieval_source` records where it came from (`offline.ast`).

**`SemanticChunk`** — a token-bounded slice of source, for later retrieval.

**`FileRecord`** — one scanned file: language, content hash, parse status.

**`ModelVersion`** — the identity of a whole model. Derived from the content hashes
of every file, and nothing else.

**`problems()`** — every entity exposes this and returns a list of human-readable
strings. An empty list on the root means the model is valid. Validation never
raises.

---

## Facts — the Tier 2 / Tier 3 vocabulary

The only shapes that cross the boundary.

**`SymbolFact`** — a declaration, with its type, qualified name, span, signature and
doc comment.

**`ImportFact`** — a module reference, with the imported names and any alias.

**`CallFact`** — a call site, with the callee name, the receiver expression, and the
enclosing symbol.

**`InheritFact`** — a base class or implemented trait reference.

**`BindingFact`** — a name → type binding. Records the bound name, the type name,
the scope, and the enclosing qualified name. Bindings exist so that member calls
can be resolved: resolving `self.repository.save(...)` requires knowing what
`repository` is.

**Scope** — where a binding lives: `LOCAL`, `INSTANCE`, or `PARAMETER`.

---

## Identity

**Content-addressed ID** — `sha1(parts joined by "\x1f")[:16]`, with a per-family
prefix. Stable across runs, and never derived from a database row.

| Prefix | Entity |
|---|---|
| `file_` | file (path only) |
| `sym_` | symbol |
| `rel_` | relationship |
| `ev_` | evidence |
| `chunk_` | chunk |
| `mv_` | model version |
| `unresolved:` | placeholder target for an unresolved edge |

**`model_digest`** — a digest over the whole model, used to compare two models.

**`model_version`** — the ID of a model version. **Never an input to any entity
ID** — if it were, an unchanged symbol would get a new ID on every reindex and
incremental reuse would be impossible.

**`unresolved:` target** — the placeholder a relationship points at when its target
has not been resolved. The raw source text is preserved in `target_name`.

---

## Statuses

**`ParseStatus`** — `OK`, `PARTIAL`, `FAILED`, `EMPTY`, `UNSUPPORTED`.
`is_error` is `FAILED` only; `is_degraded` is `PARTIAL` or `FAILED`.

**`ResolutionStatus`** — `RESOLVED_EXACT`, `RESOLVED_HEURISTIC`, `AMBIGUOUS`,
`UNRESOLVED`. M1 emits `RESOLVED_EXACT` only for `CONTAINS`, because containment is
structural. Everything else is `UNRESOLVED` by design — M1 **observes, it does not
infer**.

**Ambiguous** — a correct answer, not a failure to decide. The model must never
turn an ambiguous relationship into a confident one without evidence.

**`FileKind`** — whether a file is a symbol source or merely parsed.

---

## Tree-sitter

**Grammar** — a parser for one language, supplied pre-compiled by
`tree-sitter-language-pack` (about 400 of them, no build step).

**Query / `.scm`** — a declarative pattern file, one per extractable language, in
`maat/offline/queries/`. A language becomes extractable the moment its `.scm`
exists — the set is derived from the filesystem, never hard-coded.

**Capture** — a named node matched by a query, written `@name.suffix`. See
[`adding-a-language.md`](adding-a-language.md) for the full vocabulary.

**Match** — a query result: a pattern index plus a map of capture name to nodes.
The extractor pairs a declaration capture (`@def.class`) with its name capture
(`@name.class`) *within one match*, because the name node's parent is frequently
not the declaration node.

**ERROR / MISSING node** — tree-sitter's markers for unparseable and absent syntax.
Their presence is what distinguishes `PARTIAL` from `OK`.

---

## The pipeline

**Snapshot** — the result of scanning a repository: every file that counts, with
its language and content hash. Excluded files are recorded with a reason rather
than dropped.

**Manifest** — `manifest.json`, the change-detection baseline. Carries a scan
timestamp, so unlike `ir.json` it is deliberately **not** reproducible.

**`ir.json`** — the serialised model. **Byte-for-byte reproducible** for identical
source content.

**`.maat/`** — the index directory, written inside the repository being indexed.
Ignored by git.

**Change detection** — diffing the current snapshot against the manifest, producing
`NEW`, `CHANGED`, `DELETED`, `RENAMED`, `UNCHANGED`.

**Incremental reuse** — unchanged files keep their previously built entities rather
than being reparsed. Reused entities are re-stamped with the new `model_version`.

**Rename detection** — pairing a deleted path with a new one **by content hash
only**. A content-changed rename is reported as delete + add; no similarity
heuristic is used, because guessing would fabricate a relationship.

**Atomic publication** — `mkstemp` → `fsync` → `os.replace`. A model is published
only if it validates; an invalid build leaves the previous version intact.

**`persist=False`** — index without writing anything. The right choice in tests.

---

## Contributing terms

**Vertical slice** — a change that can be tested on its own. Not "add the
resolver", but "resolve import targets within a single file".

**Deterministic mechanism** — a rule expressed structurally, as opposed to a
heuristic. Preferred everywhere: a guess that is right 95% of the time is worse
than an honest `UNRESOLVED`.
