# Walkthrough — the M1 Offline Parser

A step-by-step explanation of what was built, from four angles: the overall
architecture, each module's responsibility, the data transformations, and error
handling. Every significant implementation choice is explained where it arises,
and §7 is an honest record of the bugs found along the way.

**What exists:** 14 modules, 18 verified extraction queries, 2 fixtures, 137
tests, all passing.

```bash
python tests/run_all.py                                  # 137 tests, PASS
python tools/demo_offline.py                             # the 7-file fixture
python tools/demo_offline.py tests/fixtures/edgecase_repo # 156 files, 18 grammars
```

---

## 1. Overall architecture

### 1.1 The one rule everything else follows

> **Language-specific shapes never cross out of the syntax tier.**

The semantic model must be language-neutral (§11 AC3). That is not achieved by
being careful — it is achieved by putting a type boundary in the way and never
letting a grammar node through it. So the system is three tiers, and the only
things that cross the boundaries are two plain dataclasses: `FileRecord` going
down and `ParseOutcome` coming back.

```text
Tier 1  acquisition   languages.py  snapshot.py  changes.py
                            ↓  FileRecord + raw bytes
Tier 2  syntax        parser.py  queries/*.scm
                            ↓  ParseOutcome  (tree, status, diagnostics)
Tier 3  semantics     extractors/  ir_builder.py  core/contracts.py
                            ↓  Semantic IR
```

`ExtractionFacts` — what Tier 3 receives — has no `node`, no `node_type`, and no
import of tree-sitter. There is nothing language-specific left in it to leak.
`test_extractor.NoLeakageTests` asserts this by searching the serialised facts
for the strings `Node`, `tree_sitter`, `start_byte`, `type=`.

### 1.2 Why three tiers rather than a parser and a model

Two tiers would have been simpler and would have failed the same way every
code-intelligence tool fails: the model gradually grows grammar-shaped fields
(`is_async`, `decorator_list`, `modifiers`) until adding a second language means
rewriting the model.

The middle tier is deliberately *disposable*. If a better parsing toolchain
arrives, Tier 2 is replaced and Tier 3 never notices. That is what the
`ParserBackend` protocol buys (§10 lists "parser abstraction" as a deliverable):

```python
class ParserBackend(Protocol):
    def parse(self, source: bytes, language: str) -> ParseOutcome: ...
```

### 1.3 Why the grammar is a registry and the extraction is data

The grammar comes from `tree_sitter_language_pack` — around 400 pre-compiled
languages. Two consequences shaped the design:

**Language detection is an explicit table, not the pack's own detector.** The
pack maps `.csv` to a CSV grammar and `.txt` to a text grammar. Those are not
source code, and letting them into the semantic model as if they were would
corrupt it. `languages.py` holds an explicit 61-language, 60-extension table, so
detection is deterministic and reviewable (§8 AC5).

**Extraction is declarative.** Rather than a Python class per language, each
language gets a `.scm` query file. Coverage is then *derived from the
filesystem*:

```python
def extraction_query_path(language: str) -> Path | None:
    candidate = QUERY_DIR / f"{language}.scm"
    return candidate if candidate.is_file() else None
```

Adding a language is dropping in a file. Nothing can drift out of sync, because
there is no second list to forget to update. A language with no query file is
reported honestly — parsed, zero symbols, and a `extract.no_query` diagnostic
saying so — rather than silently returning an empty result that looks like
"this file has no symbols".

### 1.4 The three mechanisms that make one engine serve 18 grammars

This is the part of the design most worth understanding, because the grammars
agree on almost nothing.

**(a) Pairing by match.** Every definition pattern captures the declaration node
*and* its identifier in the same pattern:

```scheme
(class_definition name: (identifier) @name.class) @def.class
```

This is necessary because the name node's parent is frequently not the
declaration node. In C the identifier sits inside a `function_declarator`; in Go
a method name is a `field_identifier` inside a `method_declaration`. Query
*matching* groups the two captures together, so the extractor never has to walk
up and guess.

**(b) Nesting by span containment.** A declaration's parent is the innermost
other declaration whose byte range contains it. tree-sitter gives every node a
byte range, and declaration ranges are properly nested, so this is exact:

```python
ordered.sort(key=lambda item: (item[0].start_byte, -item[0].end_byte))
for node, _type, _name in ordered:
    while stack and not (stack[-1].start_byte <= node.start_byte
                         and node.end_byte <= stack[-1].end_byte):
        stack.pop()
    parent_of[node.id] = stack[-1] if stack else None
    stack.append(node)
```

The alternative — a per-language list of "container node types" — would be 18
pieces of metadata to maintain and get wrong. This needs none, and it is what
produces qualified names and `CONTAINS` edges.

**(c) Reclassification by context.** Kotlin, Swift, Scala, Dart, C++ and Python
all use one function-declaration node for both top-level functions and methods.
Rather than six special cases, one rule applies to all of them: *a function whose
nearest enclosing declaration is a class, interface or enum is a method.* That
is true in every language in the registry.

---

## 2. Module responsibilities

Each module is listed with what it owns, and — more usefully — what it refuses
to do.

### `maat/core/enums.py`
**Owns** the closed vocabularies: `ParseStatus`, `SymbolType`,
`RelationshipType`, `ResolutionStatus`, `DiagnosticSeverity`, `VersionStatus`,
`FileKind`, `ChangeKind`.

`_StrEnum` overrides `__str__` so `str(ParseStatus.OK)` is `"OK"`, not
`"ParseStatus.OK"`. These values are written into canonical JSON and will
become SQLite columns in M3; the wrong form would be baked into persisted data.

`RelationshipType` contains **only observed** relationships (§4.3). Derived ones
(`DEPENDS_ON`, `IMPACTED_BY`) are deliberately absent so they cannot be written
into the model as if they had been observed. `ResolutionStatus` exists in M1 even
though M1 emits only `UNRESOLVED`, so M2 cannot invent a different vocabulary.

**Refuses to do:** carry behaviour. These are values.

### `maat/core/locations.py`
**Owns** `SourceSpan` — 1-based lines, 0-based columns, half-open end.

The conventions are fixed in one place because getting them wrong is the classic
off-by-one bug in code-intelligence tools. Half-open means `end - start` is the
length and adjacent spans never overlap. 1-based lines match every editor and
every error message a user will ever see.

`from_tree_sitter` keeps tree-sitter's **byte** columns rather than converting
them to character offsets — converting would make the span disagree with the
parser on any file containing non-ASCII text.

**Refuses to do:** raise on an invalid span. `problems()` returns strings;
callers aggregate them into a validation report (§14).

### `maat/core/ids.py`
**Owns** identity. Four rules, each load-bearing:

1. **Content-addressed, never random.** No `uuid4`, no counters, no `id()`.
2. **`model_version` is not part of any ID.** Every entity carries a version, so
   including it is tempting — but it would give an *unchanged* symbol a fresh ID
   on every reindex, destroying the incremental reuse Stage 21 depends on.
3. **Fields are joined with `\x1f`** (ASCII unit separator), which is illegal in
   a path, a qualified name and an enum value, so `("a", "b|c")` and
   `("a|b", "c")` cannot collide.
4. **Truncated to 64 bits.** For a 1M-symbol repo the birthday bound is ~2.7e-8,
   far below the rate at which a resolver would produce a wrong-but-stable
   answer. Longer IDs buy nothing and make every log line unreadable.

Relationship IDs include the line **and the column**, because `f(); g()` on one
line is two call sites with two pieces of evidence.

**Refuses to do:** know about files or symbols as concepts. It is pure functions
over strings.

### `maat/core/contracts.py`
**Owns** the canonical model: `FileRecord`, `Symbol`, `Relationship`,
`Evidence`, `SemanticChunk`, `ModelVersion`, `RepositorySnapshot`, `ChangeSet`,
`SemanticIR`, `Diagnostic`, `ExcludedFile`.

Every object exposes `problems()` returning a list of strings. Validation never
raises, because a half-parsed file legitimately produces incomplete entities and
the pipeline must survive that (§30). `SemanticIR.problems()` does whole-model
validation including referential integrity, in one pass over indexed sets so it
stays linear on a large repository.

**Refuses to do:** serialise itself to JSON by hand. `to_dict()` returns plain
data; canonical JSON is `serialization.py`'s job.

### `maat/core/serialization.py`
**Owns** determinism at the point where it is easiest to lose: JSON. Sorted
keys, fixed separators, `ensure_ascii=False` with explicit UTF-8, no timestamps,
no sets.

`write_json` writes to a temp file, `fsync`s, then `os.replace`s over the target.
That makes a half-written manifest impossible, which is how §9 AC6 and §19 AC2
are satisfied without any explicit rollback logic.

`model_digest` deliberately strips `counts` so the determinism test compares
content, not derived statistics.

**Refuses to do:** stringify unknown objects. `_json_default` raises `TypeError`
rather than silently `repr()`-ing something into the model.

### `maat/offline/languages.py`
**Owns** path → grammar mapping. 61 languages, 60+ extensions, special filenames
(`Dockerfile`, `Makefile`, `go.mod`), and a `is_code` flag distinguishing source
from data formats.

**Refuses to do:** import tree-sitter. It is pure data, which is why it can be
tested without a grammar and read without understanding the pack.

### `maat/offline/snapshot.py`
**Owns** deterministic discovery, classification and hashing.

Determinism comes from never trusting the filesystem: `dir_names.sort()` and
`file_names.sort()` at every level of `os.walk`, and a final sort by path.

`content_hash` is SHA-256 over **raw bytes**, for three reasons: it is
encoding-independent; it cannot fail on undecodable input; and it is sensitive to
line-ending changes, which *do* change what a parser sees.

Binary detection is a NUL byte in the first 8 KB — the same heuristic git uses.
No text encoding this pipeline accepts emits NUL, so it never misclassifies
source.

Ignored, binary and generated files are **excluded** from the manifest (§8 AC4)
but recorded in `snapshot.excluded` with a reason. A silently skipped file is
indistinguishable from a missing one, and "why is my code missing?" must be
answerable. Pruned directories are recorded too — as a single entry for the
directory rather than for every file inside it, which would be thousands of
entries for a real `node_modules`.

**Refuses to do:** parse anything, or decide whether syntax is valid. It sets a
*provisional* `parse_status` and says so.

### `maat/offline/changes.py`
**Owns** the diff between two snapshots.

Renames are detected by **content hash**, not similarity. A similarity heuristic
would occasionally pair two unrelated files and mislabel a delete-plus-add as a
move — worse than missing the rename. The pairing is one-to-one and resolved in
sorted order, so it is deterministic when several files share a hash.

A missing or corrupt manifest returns `None` rather than raising. It means "never
indexed", which makes every file new (§9 AC1). A truncated manifest from an
interrupted run lands in the same branch — the safe direction to fail.

**Refuses to do:** treat a rename as a no-op. See §6.3 for why that is a
deliberate deviation.

### `maat/offline/parser.py`
**Owns** turning bytes plus a grammar into a `ParseOutcome`.

The work here is not error recovery — tree-sitter always returns a tree — it is
*classification*. The whole module exists to answer one question: is the tree we
got good enough?

Two details that matter:

`_walk_iteratively` collects node counts and depth with an explicit stack, not
recursion. A deeply nested source file produces a tree thousands of levels deep,
and a recursive walk would raise `RecursionError` — precisely the outcome §30
forbids. The edge-case fixture contains a 300-deep file producing a 604-level
tree; a recursive walk would die on it.

`_has_clean_top_level_statement` is the `PARTIAL`/`FAILED` discriminator: does at
least one top-level child exist that has no error? A file where everything is
inside one `ERROR` node yields nothing extractable and is `FAILED`; a file with
nine good functions and one broken one yields nine symbols and is `PARTIAL`.

**Refuses to do:** raise. `GrammarUnavailableError` is caught and converted to
`ParseStatus.UNSUPPORTED` with a diagnostic.

### `maat/offline/queries/*.scm`
**Owns** the language-specific knowledge — node names, field names, and which
constructs matter. 18 files, each verified against real code by
`tools/verify_queries.py`. `README.md` documents the capture vocabulary, the
two-capture convention and its reason, and every per-language quirk and known gap.

**Refuses to do:** encode anything about the semantic model. The vocabulary
(`@def.class`, `@call.attr`, `@import.module`…) is a *fact* vocabulary, not a
model vocabulary.

### `maat/offline/extractors/base.py`
**Owns** the fact vocabulary and the `Extractor` protocol. This is the type-level
expression of the tier boundary — `SymbolFact`, `ImportFact`, `CallFact`,
`InheritFact`, `ExtractionFacts`.

`CallFact` is explicitly *not* a relationship. It records what the source said —
a callee name, optionally a receiver — and nothing more. Deciding which symbol
`self.validate` refers to is the resolver's job (§13), and guessing here would be
exactly the hallucination §4.2 warns against.

**Refuses to do:** import tree-sitter.

### `maat/offline/extractors/query_extractor.py`
**Owns** the generic capture → fact engine. Implements the three mechanisms from
§1.4. One implementation serves all 18 languages.

**Refuses to do:** contain a single `if language == ...`.

### `maat/offline/ir_builder.py`
**Owns** turning facts into validated, ID-stable entities, and the decisions that
only make sense once you have all the facts for a file:

* **Overload disambiguation.** Two Java methods named `process` in one class
  share a qualified name and therefore a hash. Rather than put a line number in
  every ID — which would make every symbol below an inserted line change identity
  — collisions are detected and resolved only where they occur, by appending a
  short digest of the signature.
* **`CONTAINS` is `RESOLVED_EXACT`.** Containment is structural, not a reference:
  when a method is parsed inside a class, both endpoints are known with certainty
  from the parse alone. Marking it `UNRESOLVED` to be "consistent" would be
  dishonest in the other direction.
* **Everything else is `UNRESOLVED`** with `target_name` preserved, so the
  resolver has something to work with.
* **Evidence is produced eagerly.** §13 AC6 requires every relationship to point
  at source evidence and §41 Rule 3 forbids trusting an answer without it.
  Producing it at build time means an entity either has provenance or is
  rejected — there is no path by which an unsupported claim reaches a reader.

Invalid entities are **dropped with a diagnostic**, never silently kept (§12 AC6).

### `maat/offline/pipeline.py`
**Owns** the two things no stage can own: the model version, and the decision
about what to reuse.

It also owns the incremental behaviour that makes §39 Step 3 work. Entities from
unchanged files are carried forward and **re-stamped** with the new version. That
looks like a contradiction and is not: the symbol's *identity* excludes the
version (rule 2 in `ids.py`), so re-stamping does not change who it is, while
§19 AC3 requires every published entity to reference the same active version.
Carrying V1 entities into a V2 model unmodified would produce exactly the
mixed-version state §19 AC1 forbids.

Nothing is published unless the model validates, and every write is atomic — so
§34's "failed indexing keeps the previous version active" holds with no explicit
rollback code.

**Refuses to do:** let any stage see a version it did not stamp.

---

## 3. Data transformation logic, step by step

Traced on `tests/fixtures/demo_repo/services/payment_service.py`.

### Step 1 — scan (`snapshot.py`)

```text
bytes on disk
   ↓ read_bytes()
data = b'"""Payment domain service."""\n\nfrom models.payment import Payment\n...'
   ↓ _hash_bytes()          sha256 over raw bytes
content_hash = "sha256:4f1c…"
   ↓ languages.detect_language("services/payment_service.py")
language = "python"          (via the .py extension)
   ↓ _looks_binary(head)?      no NUL in first 8 KB
   ↓ _looks_generated(...)?    no marker, no generated suffix, no /generated/ segment
   ↓ is_code_language("python") → True
file_kind = SOURCE, parse_status = OK (provisional)
   ↓
FileRecord(path="services/payment_service.py", language="python", size=612, …)
```

### Step 2 — diff (`changes.py`)

```text
previous manifest = None  (first run)
   ↓
ChangeSet(new=[all 7 paths], changed=[], deleted=[], unchanged=[], renamed=[])
scheduled_for_parse = 7 paths
```

### Step 3 — parse (`parser.py`)

```text
source bytes + "python"
   ↓ pack.get_language("python") → Language (cached)
   ↓ ts.Parser(language).parse(source)
Tree(root=module)
   ↓ _walk_iteratively(root)   explicit stack, no recursion
node_count=143, max_depth=7, error_node_count=0, missing_node_count=0
   ↓ error==0 and missing==0 → OK
ParseOutcome(status=OK, tree, diagnostics=[])
```

For `broken/broken_service.py` the same path yields
`error_node_count>0`, and `_has_clean_top_level_statement` returns `True` (the
`class BrokenService:` header and the import parsed), so the status is `PARTIAL`
and the valid region is retained.

### Step 4 — extract (`query_extractor.py`)

```text
Tree
   ↓ ts.QueryCursor(query).matches(root)
   matches() → [(pattern_index, {capture_name: [node, ...]}), ...]
```

`matches()` returns a *dict of node lists*, not a flat pair list. This matters:
one pattern can bind a capture several times, as when a class has multiple base
classes. Taking only the first node of each capture would silently drop every
base after the first — which is exactly the bug found in testing (§7.3).

```text
   ↓ group captures per match
def.class=PaymentService, def.method=process, def.method=validate,
import.module=models.payment, import.name=Payment,
import.module=repositories.payment_repository, import.name=PaymentRepository,
call.attr=validate + call.recv=self, call.attr=save + call.recv=self.repository
   ↓ span containment (stack over sorted byte ranges)
PaymentService.parent = module
process.parent = PaymentService
validate.parent = PaymentService
   ↓ qualified names
"services.payment_service:PaymentService"
"services.payment_service:PaymentService.process"
   ↓ import grouping via _statement_ancestor
ImportFact(module="models.payment", names=["Payment"], alias=None)
ImportFact(module="repositories.payment_repository", names=["PaymentRepository"])
   ↓ calls, attributed to their innermost enclosing symbol
CallFact(callee="validate", receiver="self", enclosing="…:PaymentService.process")
CallFact(callee="save", receiver="self.repository", enclosing="…:PaymentService.process")
   ↓ docs: earliest doc node inside each symbol's span
PaymentService.documentation = "Validates and persists payments."
```

The module is inserted as the **root** declaration before this, which is why
top-level symbols get a parent and module docstrings have somewhere to attach,
with no special cases anywhere.

### Step 5 — build IR (`ir_builder.py`)

```text
facts
   ↓ _assign_symbol_ids: group by (symbol_type, qualified_name)
      no collision → symbol_id("services/payment_service.py", "CLASS", "…:PaymentService")
   ↓ Symbol(id="sym_7a1f…", file_id="file_3c2b…", location=SourceSpan(9,0,20,0), …)
   ↓ CONTAINS: process → PaymentService, RESOLVED_EXACT, confidence 1.0
   ↓ IMPORTS: module → unresolved:module:models.payment, UNRESOLVED, 0.0
   ↓ CALLS:   process → unresolved:call:self.validate, UNRESOLVED, 0.0
   ↓ Evidence: one per symbol, retrieval_source="offline.ast"
   ↓ Chunks: one per symbol + one "imports" chunk
   ↓ validate each entity; drop with a diagnostic if problems() is non-empty
```

### Step 6 — assemble and publish (`pipeline.py`)

```text
all file IRs
   ↓ _sort_ir: every collection into a defined order
   ↓ combine_hashes(all content hashes) → model_version_id → "mv_9abb…"
   ↓ stamp every FileRecord, Symbol, Relationship, Evidence, Chunk
   ↓ ir.problems() → []  (validate the whole model)
   ↓ VersionStatus.PUBLISHED
   ↓ write_json(manifest.json), write_json(ir.json)   [atomic]
```

On the second run over an unchanged repository, steps 3–5 are skipped for all
seven files; the entities are loaded from `ir.json`, re-stamped, and re-sorted.
The result is byte-identical, and the version ID is unchanged — verified by
`test_pipeline.DeterminismTests`.

---

## 4. Error handling

### 4.1 The rule

> **No function in Tier 2 or Tier 3 raises on malformed input.**

Failure is data. Every failure path produces a `Diagnostic` with a code, a
severity, a span and a recovery action, and the pipeline continues. This is not
defensive programming for its own sake — §30 AC1 states that one malformed file
must not stop repository indexing, and the only way to guarantee that is to make
raising impossible rather than merely unlikely.

### 4.2 The status ladder

```text
grammar unavailable          → UNSUPPORTED   not an error; a diagnostic is recorded
no tokens                    → EMPTY         not an error
no error, no missing nodes   → OK
≥1 clean top-level statement  → PARTIAL       valid regions kept, file marked degraded
no clean top-level statement → FAILED        error persisted, zero symbols
```

### 4.3 What happens to each failure

| Failure | Where handled | Result |
|---|---|---|
| Unreadable file | `snapshot.scan_repository` | `FileRecord` with `FAILED` + reason; scan continues |
| Unknown extension | `snapshot` + `languages` | `UNSUPPORTED`; excluded from symbol extraction |
| Binary / generated / ignored | `snapshot` | Excluded from manifest, recorded with a reason |
| Malformed syntax | `parser` | `PARTIAL` or `FAILED`; valid regions retained |
| Grammar unavailable | `parser` | `UNSUPPORTED` + `parse.grammar_unavailable` |
| No extraction query | `query_extractor` | Module symbol only + `extract.no_query` |
| Invalid entity | `ir_builder` | Dropped + `ir.invalid_symbol` with the reason |
| Overload collision | `ir_builder` | Disambiguated by signature + `ir.overload` |
| Corrupt manifest | `changes` | Treated as "never indexed"; everything is new |
| Corrupt previous model | `pipeline.load_previous_ir` | Treated as absent; full rebuild |
| Interrupted write | `serialization.write_json` | Atomic replace; previous state untouched |
| Invalid model | `pipeline` | Not published; version marked `FAILED` |

### 4.4 Degradation is visible, not silent

Three separate mechanisms keep degradation from disappearing:

1. `FileRecord.parse_status` — `PARTIAL`/`FAILED` on the file itself.
2. `Diagnostic` records — persisted in the model, not logged and discarded.
3. A `parse_error` **chunk** per degraded file — so the reason a file is
   incomplete is retrievable alongside the code that did parse.

Mechanism 2 was initially missing. The parser produced diagnostics, but
`pipeline._parse_and_build` only consumed the *extractor's* diagnostics and let
the parser's go out of scope — so a degraded file reached the model with no
explanation. `test_pipeline.test_broken_file_error_is_persisted` caught it.

Mechanisms 2 and 1 were also lost on the *incremental* path: a reused file's
diagnostics and parse status were not carried forward, so a file that was
`PARTIAL` on run 1 silently became `OK` on run 2 while the broken code was still
there. Both are now carried across; the diagnostics are grouped by file path in
`_group_by_file`.

### 4.5 Recursion is a failure mode too

`_walk_iteratively` and the span-containment walk are both iterative. A 300-level
nested Python file produces a 604-level tree; a recursive traversal would raise
`RecursionError` and take the whole repository down — the same class of failure
§30 forbids, arriving through a different door. `test_parser` asserts a 300-deep
file parses `OK` with `max_depth > 300`.

---

## 5. Verification

```bash
$ python tests/run_all.py
Ran 137 tests in 11.689s
OK
```

| Suite | Tests | What it proves |
|---|---|---|
| `test_snapshot` | 18 | discovery, hash stability/sensitivity, exclusion with reasons, determinism |
| `test_changes` | 16 | the six §9 acceptance criteria, corrupt manifests, incremental counters |
| `test_parser` | 22 | the six §10 acceptance criteria, deep nesting, BOM, CRLF, unicode, 3000-function file |
| `test_extractor` | 15 | §11 acceptance, multi-base capture, expression receivers, all 18 languages, no leakage |
| `test_ir` | 30 | §12 acceptance, ID stability, overloads, referential integrity, confidence policy |
| `test_pipeline` | 26 | §7 expected graph, fault isolation, determinism, 156-file repo, persistence |

Against the generated repository:

```text
files scanned     142        symbols        5,044
excluded          BINARY 1, GENERATED 3, IGNORED 9
status            OK 128, EMPTY 3, PARTIAL 3, FAILED 6, UNSUPPORTED 2
languages         18
model             valid, no referential problems
duration          7.0 s
```

Six files fail to parse and three parse only partially. The other 133 index
normally, which is the entire point.

---

## 6. Rationale for the significant choices

### 6.1 Why `CONTAINS` is resolved and nothing else is

Containment is a structural fact. When the parser sees `def process` inside
`class PaymentService`, both endpoints are known with certainty — no name
resolution is involved. Marking it `UNRESOLVED` for consistency would be
dishonest in the opposite direction, throwing away information we actually have.

Imports, calls and inheritance name things that may live outside the file, so
they are recorded `UNRESOLVED` with the raw target text preserved. §4.2:
*"MAAT should prefer an explicit unresolved relationship over an incorrect
confident relationship."* The consequence is that the §7 dependency graph is not
*connected* at the end of M1 — the edges exist, but their targets are
placeholders. That is the correct state for this stage.

### 6.2 Why version IDs ignore the parent

The first implementation hashed `(parent_version, file_hashes)`. That made the
version a function of *history* rather than of *state*, so reindexing an
unchanged repository produced a new version every time — inventing a change that
did not happen, and contradicting §9 AC2's "0 files reparsed".

Hashing only the content makes the version a pure function of repository state.
The parent is still recorded as lineage on `ModelVersion`, just not as identity.
`test_changes.test_unchanged_repository_keeps_the_same_version` pins this.

### 6.3 Why a rename *is* reparsed

§9 AC5 says a rename should not *unnecessarily* trigger recomputation "when
content is unchanged and cache policy allows reuse". Our cache policy does not
allow it: symbol IDs include the file path, so moving a file changes the identity
of every symbol inside it. Reusing the old parse would leave the model keyed to a
path that no longer exists.

So the recomputation is *necessary*, not unnecessary, and the rename is still
reported separately so callers can see what happened. The alternative — dropping
the path from symbol IDs — would make two same-named classes in different files
collide, breaking §13 AC2. Path in the ID is the right trade.

### 6.4 Why the generated-path markers were made conservative

The first version treated any path containing `/gen/` as generated. That is a
reasonable reading of "generated" and it silently excluded all eight
`com/example/gen/Service*.java` files from the test repository — real source,
invisible to the model.

The rule now: **a false positive here silently removes real source, which is far
worse than a false negative that merely leaves generated code in.** The model can
be queried about generated code; it can never be queried about code that was
never indexed. `/gen/` was removed, and the remaining markers are unambiguous
(`/generated/`, `/autogen/`, `/auto-generated/`, `/__generated__/`).

### 6.5 Why excluded files are recorded rather than dropped

§8 AC4 requires ignored, generated and binary files to be excluded. Excluding
them *silently* would satisfy the letter of that and be worse in practice: a user
asking "why is my file missing?" would have no answer. So they are excluded from
`snapshot.files` — never parsed, never in the model — and recorded in
`snapshot.excluded` with a reason.

Directories are recorded as a single entry rather than one per file inside them,
because a real `node_modules` would add thousands of entries for no additional
information.

### 6.6 Why evidence is eager rather than lazy

Producing evidence on demand would be cheaper and would make it possible for an
entity to exist without provenance. §13 AC6 requires every resolved relationship
to point back at source evidence, and §41 Rule 3 forbids trusting any answer
merely because a model produced it. Eager production means the invariant is
established at build time and cannot be violated later: an entity either has
evidence or was rejected.

### 6.7 Why the module is a symbol

Every file gets a `MODULE` symbol even when it declares nothing. Three things
follow: top-level calls and imports have somewhere to attach, so nothing is
orphaned; module-level docstrings have a home; and an empty file has a
meaningful model entry rather than silently vanishing. Modelling it as the
containment-tree root rather than special-casing it means the qualified-name and
`CONTAINS` code paths need no exceptions.

### 6.8 Why `matches()` not `captures()`

`QueryCursor.captures()` returns a flat `{name: [nodes]}` map that loses the
grouping between a declaration and its name. `matches()` preserves it. Using
`captures()` would have forced the extractor to reconstruct the pairing by
walking parents — which is exactly the fragile, per-language work the
two-capture convention exists to avoid.

### 6.9 Why `unittest` and hand-written validation

The brief originally called for no unexplained external libraries, and the
project now has exactly one runtime dependency (tree-sitter, by explicit
decision). Adding pytest for the tests and pydantic for the models would double
that for ergonomic gain only. `problems()` methods return strings; §12 AC6 wants
invalid objects rejected before indexing, which a list of reasons does as well as
an exception would.

---

## 7. Bugs found during implementation

An honest record, because each one changed the design or the tests.

| # | Bug | How it surfaced | Fix |
|---|---|---|---|
| 1 | `QueryCursor.matches()` was iterated as flat `(node, name)` pairs | `ValueError: too many values to unpack` | Rewrote against the real shape: `(pattern_index, {capture: [nodes]})` |
| 2 | Taking only the first node per capture | Review of the fix for #1 — would have dropped every base class after the first | Iterate the node lists where multiplicity is real |
| 3 | `/gen/` treated as a generated-code marker | Histogram showed 2 Java files instead of 10 | Removed the ambiguous marker; conservative by default |
| 4 | Pruned directories were not reported | Exclusion counts did not add up: 156 files on disk, only 142 scanned, but just 8 exclusions — 5 directories had been pruned silently | Record pruned directories as exclusions; the final tally reconciles as 142 scanned + 13 exclusion entries (5 directories + 8 files) |
| 5 | Early `return` when a file had no declarations | `import ujson as json` alone yielded zero imports | Removed the guard; the module root is a valid attachment point |
| 6 | Version ID included the parent | Unchanged reindex produced a new version | Content-only version identity |
| 7 | Parser diagnostics never reached the model | `test_broken_file_error_is_persisted` | Propagate `outcome.diagnostics` into the IR |
| 8 | `parse_error` set only for `FAILED` | Degraded `PARTIAL` files had no recorded reason | Set it for any degraded status |
| 9 | Parse status and diagnostics lost on incremental reuse | `test_index_files_are_written_and_reloaded` — degraded count went 1 → 0 | Carry the previous `FileRecord`'s outcome and the file's diagnostics forward |
| 10 | `self._current_root` referenced but never assigned | Reading the code while writing tests | Threaded `root` through as a parameter instead of instance state |
| 11 | Dead validation branch (`X and not X`) | Review | Replaced with real confidence/status consistency checks |
| 12 | Module docstrings had nowhere to attach | Smoke test showed only the class docstring | Module modelled as the containment root |

Bugs 1–5 were found by running the code against real inputs; 6–9 by the test
suite; 10–12 by reading the code back. That distribution is the argument for
having all three.

---

## 8. What M1 hands to M2

The resolver (Stage 6) receives a model that is complete, validated and
deterministic, containing:

* every symbol with a stable ID, a qualified name and a source span
* every call site with its receiver, its raw target text and its enclosing symbol
* every import with its module, names and alias
* every base class reference
* `CONTAINS` edges already resolved, so the symbol tree is navigable today
* `UNRESOLVED` reference edges with `target_name` populated, ready to resolve

The `ResolutionStatus` vocabulary, the confidence policy and the relationship
contract already exist, so M2 upgrades edges rather than changing the schema.
