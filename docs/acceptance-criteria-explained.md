# The Acceptance Criteria, Explained

A companion to `docs/test-acceptance-matrix.md` (which maps tests → criteria).
This document explains **the criteria themselves**: what each one demands, why it
exists, and how you would know it holds.

`Problem_doc.md` states acceptance criteria at **four different layers**, and
conflating them is the main source of confusion:

| Layer | Where | Count | Nature |
|---|---|---:|---|
| **Numbered ACs** | `### ACn` in §8–§31 | **83** | Per-stage, testable, the working contract |
| **Unnumbered bullets** | §7, §11, §12, §14, §15, §17, §18, §21, §24 | **43** | Same force, just not numbered |
| **Named scenarios** | §32 `E001`–`E005` | **5** | End-to-end queries the whole system must answer |
| **Summary layers** | §33 gates, §34 failure conditions, §40 definition of done, §41 rules | 26 + 12 + 10 + 3 | Roll-ups and non-negotiables |

**Total: 131 stage-level criteria, plus 51 summary-level statements.**

---

## Part I — The shape of the criteria

The 131 stage-level criteria are not 131 independent checks. They are instances
of **eight recurring demands**. Recognising the family tells you what kind of
test can possibly prove it — and, more usefully, tells you when a criterion is
*unfalsifiable as written*.

### 1. Determinism — "same input, same output"

*Appears in:* §8 AC2, AC5 · §9 AC2, AC6 · §12 · §16 AC5 · §19 · §29 AC3, AC6 · §40.

The strongest form in this spec is **byte-level**: §8 AC5 says "the same file
manifest", and the implementation holds itself to `canonical_json` equality. A
deterministic model means you can cache, diff, and reuse it. Every other
incremental guarantee depends on this one.

**The trap:** "same output" is only meaningful once you have decided *what is not
part of the output*. Timestamps, dict ordering, set iteration order, and absolute
paths all have to be deliberately excluded. §8 AC5 is easy to state and hard to
hold.

### 2. Honesty — "never claim what you cannot support"

*Appears in:* §13 AC3, AC5 · §14 (ambiguous stay ambiguous) · §23 AC2 · §24
(unsupported claims detectable) · §25 AC2, AC5 · §28 AC8 · §34 · §41 Rule 1 & 3.

This is the spine of the whole design. It shows up as:

- **Not inventing**: unknown symbol → `Not found`, not a guess (§23 AC2).
- **Not upgrading**: an ambiguous receiver stays `AMBIGUOUS` rather than being
  assigned an arbitrary target (§13 AC3). This is why `ResolutionStatus` has four
  values instead of two — the third and fourth exist purely so that "I don't
  know" is representable.
- **Not laundering**: an unsupported claim must be *detectable* by the validator
  (§24, §25 AC2). Note the criterion is detection, not prevention — the model is
  allowed to hallucinate, but the system is not allowed to *return* it.

**The trap:** honesty is the one demand that cannot be satisfied by adding
capability. Every improvement to resolution makes it easier to violate. §13 AC5
("the resolver must never create a relationship merely because a model predicts
one") is a *permanent* constraint on a component whose whole purpose is to infer.

### 3. Isolation — "a local failure stays local"

*Appears in:* §10 AC2 · §30 AC1–AC5 · §34 (broken file) · §27 AC6.

The unit of failure is the **file**, never the repository. §30 AC1–AC5 is the
full statement: one bad file must not stop indexing, must be marked `FAILED` or
`PARTIAL`, must have its error persisted, must leave the other files queryable,
and must recover on the next reindex once fixed.

The design consequence is that **failure is data, not an exception** — which is
why `ParseStatus` is a five-value ladder (`OK / PARTIAL / FAILED / EMPTY /
UNSUPPORTED`) and why every object exposes `problems()` rather than raising.

### 4. Version coherence — "nothing mixes versions"

*Appears in:* §12 (every entity belongs to a version) · §16 AC5 · §19 AC1–AC4 ·
§25 AC5 · §34 (mixed index versions) · §40.

Two related but distinct demands, often confused:

- **§19 AC3** — all published *indexes* reference the same version.
- **§12** — every *entity* carries a version, and no entity references a version
  other than the active one.

§19 AC1 is the sharpest formulation in the whole spec: no query may observe
`Graph V2 + FTS V1 + Vector V1` **as one state**. That is a statement about
*atomicity of observation*, not about correctness of any single index. It is
the reason §19 asks for an atomic active-version pointer rather than five
separate writes.

**Note the interaction with §12 and identity:** §12 requires IDs to be *stable
across versions* (otherwise incremental reuse is impossible), while §19 requires
everything to be *stamped with* the active version. Both hold because identity is
content-addressed and version is an attribute, not part of the ID preimage. Get
that wrong and §9 AC2 (no-change run) becomes unachievable.

### 5. Provenance — "every claim traces back to source"

*Appears in:* §12 (evidence) · §13 AC6 · §18 · §22 AC5 · §23 AC4 · §25 AC1, AC2 ·
§27 AC5 · §28 AC2 · §31 AC3 · §40.

Every symbol, relationship, context item, and answer must point at real source
locations. §13 AC6 makes it explicit for relationships; §22 AC5 extends it to
*context*; §25 AC1–AC2 makes it the basis of validation.

This is what makes §41 Rule 3 enforceable. "No generated answer is trusted merely
because a model generated it" is only checkable because every claim has an
evidence ID attached that can be independently verified against the model.

### 6. Boundedness — "everything terminates, within a budget"

*Appears in:* §16 AC3 (depth N), AC4 (cycles) · §22 AC6 (token budget) · §28 AC5
(iterations), AC6 (tokens), AC7 (tool failure) · §34 (agent loop).

The agent is the only component that can run forever, so §28 carries eight
criteria — five of which are about stopping. §28 AC3 (cycles), AC4 (repeated
unproductive calls), AC5 (max iterations), AC6 (token budget), AC8 (no evidence)
are five different reasons to stop, because each can trigger when the others do
not.

### 7. Minimality — "don't do work you don't need"

*Appears in:* §9 AC2, AC3 · §22 AC2 · §23 AC3 · §26 AC1 · §29 AC1, AC3 · §30.

§9 AC2 ("100 files → 0 files reparsed") is the foundational one. §29 extends it
from *files* to *relationships* — the hard version, because a change to B can
invalidate an edge recorded in an unchanged A.

§26 AC1 ("deterministic queries do not invoke an LLM") is minimality expressed as
cost: the cheapest mechanism that can produce a validated answer wins.

**The trap:** minimality and §29 AC6 ("final model is equivalent to a clean
rebuild") are in direct tension. Skipping work is only safe if you can prove the
skipped work could not have changed the outcome. §29 AC6 is the criterion that
keeps AC1 and AC3 honest — without it, "minimal" degenerates into "wrong".

### 8. Replaceability — "the seams hold"

*Appears in:* §10 (parser abstraction) · §11 AC3 (no AST leakage) · §18
(embedding interface) · §26 (model router) · §27 AC7 (no storage details leak) ·
§41.

Three seams are specified, and each has the same shape: a **stable boundary with
an explicit contract, so the implementation behind it can be swapped**.

| Seam | Boundary | The criterion that enforces it |
|---|---|---|
| Parser | `ParserBackend` Protocol | §10 "parser abstraction"; §11 AC3 — no tree-sitter type may cross into the model |
| Model | router + escalation | §26 — capability selected per query, not hard-wired |
| Storage | MCP tool layer | §27 AC7 — tools must not expose storage implementation details |

§11 AC3 is the load-bearing one. Everything downstream of the extractors is
language-neutral *by construction* only if nothing grammar-shaped leaks through.

---

## Part II — Offline plane (§7 – §19)

### §7 Stage 0 — Fixtures and Contracts (7 unnumbered)

Not really a stage; a **precondition on the test suite**. Its criteria are about
the fixture and the tests, not about code.

| Criterion | What it demands |
|---|---|
| Fixture contains at least one complete call chain | The fixture must be able to *fail* — a chain that can be traced end to end |
| Fixture contains direct and transitive dependencies | Both adjacency and reachability are testable |
| Fixture contains an intentionally broken file | Fault isolation (§30) has something to isolate |
| Expected symbols explicitly defined | The oracle is written down, not implied |
| Expected relationships explicitly defined | Same, for edges |
| Tests can compare produced data against expected data | The fixture is *usable* as an oracle |
| No implementation without a behavioral test | The meta-rule |

**Why this is Stage 0:** every later criterion is phrased as "for the fixture".
If the fixture cannot express the demand, the criterion is untestable. The
`demo_repo` is deliberately small (7 files) and its expected graph is drawn twice
in the spec — once as a call chain, once as module imports — precisely because
M1 can only produce the latter.

### §8 Stage 1 — Repository Snapshot (AC1–AC5)

| AC | Demand | Family |
|---|---|---|
| **AC1** Complete discovery | Given 10 source files, all 10 are identified | completeness |
| **AC2** Stable hashes | Unchanged files → identical hashes across runs | determinism |
| **AC3** Content sensitivity | Changed contents → changed hash | correctness |
| **AC4** Non-source filtering | Configured ignored/generated/binary files excluded | minimality |
| **AC5** Deterministic snapshot | Same state → same manifest | determinism |

**AC2 and AC3 are two halves of one requirement.** A hash that never changes
satisfies AC2 and fails AC3; a hash of the current time satisfies AC3 and fails
AC2. Only a *content-derived* hash satisfies both. This pair is what forces raw
byte hashing — and consequently makes a CRLF rewrite a real change.

**AC4's word "configured"** is doing work: filtering must be policy, not
hard-coded, or you cannot index a repository that legitimately contains a
`build/` directory.

### §9 Stage 2 — Incremental Change Detection (AC1–AC6)

| AC | Demand | Family |
|---|---|---|
| **AC1** Initial indexing | No manifest → everything scheduled | completeness |
| **AC2** No-change run | 100 files → 0 reparsed | minimality |
| **AC3** Single modification | 1 modified → 1 reparsed | minimality |
| **AC4** Deletion | Deleted file detected, its entities become stale | correctness |
| **AC5** Rename | Rename does not *unnecessarily* trigger recomputation "when content is unchanged **and cache policy allows reuse**" | minimality |
| **AC6** Interrupted update | An interrupted index must not publish an incomplete version | version coherence |

**AC5 is the most under-specified criterion in the offline plane.** The two
qualifiers are the whole content: "where supported" and "when cache policy allows
reuse". It states a *goal* (don't waste work) without stating a *rule*. Any
implementation can claim compliance by declaring its cache policy restrictive.
M1 does exactly that — symbol IDs are path-derived, so a rename genuinely
requires rebuilding the entities. The criterion is satisfied vacuously.

**This is worth flagging as a spec gap.** A sharper AC5 would say: "a rename must
not change any entity ID that survives the move, and must not require reparsing
the file's contents" — which would be falsifiable. See Part V.

**AC6 has two halves** and they live in different components: the *read* side
(never trust a half-written manifest) and the *write* side (never leave a partial
artifact). §19 is the AC6 write-side done properly; §9 AC6 is the minimal version.

### §10 Stage 3 — Tree-sitter Parsing (AC1–AC6)

| AC | Demand | Family |
|---|---|---|
| **AC1** Valid file | Valid source → an AST | correctness |
| **AC2** Syntax error | Malformed source does not crash indexing | isolation |
| **AC3** Empty file | Empty source handled without exception | isolation |
| **AC4** Unsupported language | Explicit `UNSUPPORTED` status | honesty |
| **AC5** Source locations | Nodes preserve line and column | provenance |
| **AC6** Partial parsing | Usable partial tree → valid regions retained, file marked degraded | isolation |

**AC4's word "explicit"** is the point. A parser that returns an empty tree for an
unknown language is indistinguishable from a parser that found nothing. The
status must *say which*.

**AC6 is the criterion that makes §30 possible.** Without partial retention,
every syntax error would discard the whole file, and "other files remain
queryable" would be the only achievable form of isolation.

### §11 Stage 4 — Language Extractors (3 unnumbered)

| Criterion | Demand |
|---|---|
| `PaymentService` extracted as a symbol | Extraction produces the named entity |
| `CheckoutService → PaymentService` and `RefundService → PaymentService` identified as **candidate** call relationships | The word "candidate" is deliberate — see below |
| No language-specific AST structure leaks into the canonical model | The seam holds |

**"Candidate" is the most important word in §11.** It distinguishes *observing* a
call site from *resolving* a target (§4.3: observed vs derived relationships).
§11 asks only for observation. §13 does resolution. Confusing the two is how a
system ends up asserting that `self.payment_service.process` *is*
`PaymentService.process` without evidence.

**The third criterion is structural, not behavioral**, which makes it awkward to
test. It is checkable only negatively — no `tree_sitter` type, no `start_byte`, no
node object may appear in the fact vocabulary.

### §12 Stage 5 — Semantic IR (6 unnumbered)

| Criterion | Demand | Family |
|---|---|---|
| Identical source → stable entity IDs | Reproducible identity | determinism |
| Different symbols do not collide | Injectivity | correctness |
| Relationships reference valid entities | Referential integrity | correctness |
| Evidence references valid source locations | Provenance is well-formed | provenance |
| Every semantic entity belongs to a model version | Version stamping | version coherence |
| Invalid semantic objects are rejected before indexing | Validation is a gate, not a warning | honesty |

**"Stable" in the first criterion means stable across *versions*, not just across
runs.** That is the subtle one: if the model version were part of the ID, an
unchanged symbol would get a new ID on every reindex and §9 AC2 would be
impossible to satisfy.

**"Before indexing"** in the last criterion is a sequencing demand: validation
must happen *upstream* of publication. A validator that runs after the model is
written can only report a corrupt model, not prevent one.

### §13 Stage 6 — Resolution (AC1–AC6)

| AC | Demand |
|---|---|
| **AC1** Exact resolution | A known symbol reference resolves to the correct symbol |
| **AC2** Namespace separation | Same name in different modules stays distinct |
| **AC3** Ambiguous resolution | Ambiguous receiver → `AMBIGUOUS`, never an arbitrary target |
| **AC4** Unknown target | Unknown symbol → `UNRESOLVED` |
| **AC5** No hallucinated relationship | The resolver must never create a relationship merely because a model predicts one |
| **AC6** Relationship provenance | Every resolved relationship points back to source evidence |

**This is the stage where the four-value `ResolutionStatus` earns its keep.**
AC1 wants `RESOLVED_EXACT`, AC3 wants `AMBIGUOUS`, AC4 wants `UNRESOLVED`. A
two-valued status (resolved / not) cannot express AC3 at all — and AC3 is the
criterion that prevents the most damaging failure mode, which is confidently
picking the wrong target.

**AC5 is unusual: it constrains a mechanism, not an output.** "Must never create a
relationship *merely because a model predicts one*" cannot be tested by observing
results — you would have to observe the resolver's internals. The testable proxy
is that every relationship has evidence (AC6). AC5 is really a design rule
expressed as an acceptance criterion.

### §14 Stage 7 — Relationship Validation (6 unnumbered)

| Criterion | Demand |
|---|---|
| Duplicate relationships removed or rejected | Idempotence |
| Relationships referencing missing entities rejected | Referential integrity |
| Invalid source locations rejected | Location sanity |
| Ambiguous relationships remain explicitly marked | Validation must not *launder* uncertainty |
| Validation produces a machine-readable report | Observable, not just asserted |
| Invalid semantic data cannot be published | Validation gates publication |

**The fourth criterion is the subtle one.** A validator that "cleans up" by
dropping ambiguous edges converts a known-unknown into an absence — which is
indistinguishable from "no relationship exists". The criterion forbids exactly
that. Ambiguity must survive validation.

### §15 Stage 8 — Canonical Semantic Model (6 unnumbered)

| Criterion | Demand |
|---|---|
| All semantic entities retrievable by stable ID | Primary-key access |
| Symbols retrievable by qualified name | Secondary access path |
| Relationships queryable by source/target/type | Edge index |
| Evidence retrievable for an entity | Provenance lookup |
| A complete model can be reconstructed from persistence | Round-trip fidelity |
| **Model versions are immutable after publication** | Append-only versioning |

**"Immutable after publication" is the architectural keystone.** It is what makes
§19's atomic pointer meaningful — if a published version could be mutated, there
would be nothing to atomically point *at*. It is also what makes §9 AC6
(interrupted update) achievable: a failed run simply never publishes, leaving the
previous immutable version intact.

### §16 Stage 9 — Graph Projection (AC1–AC5)

| AC | Demand |
|---|---|
| **AC1** Direct callers | `find_callers(PaymentService)` → `CheckoutService`, `RefundService` |
| **AC2** Direct callees | `find_callees(CheckoutService)` → `PaymentService` |
| **AC3** Transitive traversal | Bounded traversal returns all nodes within depth N |
| **AC4** Cycles | Traversal terminates on cyclic graphs |
| **AC5** Version consistency | Graph version == active model version |

**AC1/AC2 are the only criteria in the spec that name a function signature.** They
are the concrete form of §7's expected graph, promoted from a fixture property to
an API contract.

**AC3's "depth N" is undefined.** N is a parameter, but the criterion does not say
what N is or how the bound is enforced. It is testable in spirit ("all reachable
nodes within N") but the spec never fixes N.

**AC5 is where "an index is not the source of truth" becomes checkable.** The
graph is a *projection*; if its version could drift from the model's, it would
have become a second source of truth.

### §17 Stage 10 — FTS5 Projection (3 unnumbered)

| Criterion | Demand |
|---|---|
| `search_symbol("PaymentService")` returns the correct symbol | Basic retrieval works |
| Search supports exact name, qualified name, partial name, path, documentation | Five access modes |
| No result returned from an inactive semantic model | Version filtering |

**The third is the FTS5 instance of §19 AC1.** A lexical index that returns stale
hits is the most likely way for a user to observe mixed versions, because FTS
results are returned as raw text with no version attached. Version filtering must
be inside the query, not applied afterwards.

### §18 Stage 11 — Vector Projection (2 unnumbered)

| Criterion | Demand |
|---|---|
| A semantic query retrieves relevant code even without exact terminology | Embedding retrieval works |
| Retrieval retains `symbol_id`, `file_id`, `model_version`, source location | Results can become evidence |

**The second criterion is what keeps the vector index honest.** A vector hit is
the least verifiable form of retrieval — it is a similarity score, not a fact.
Requiring it to carry the four provenance fields is what allows §25 to validate an
answer that was partly built from vector results. Without it, semantic retrieval
would be the one path into the answer that could not be checked.

### §19 Stage 12 — Atomic Index Publication (AC1–AC4)

| AC | Demand |
|---|---|
| **AC1** | No query may observe `Graph V2 + FTS V1 + Vector V1` as one state |
| **AC2** | Failed V2 validation leaves V1 active |
| **AC3** | All published indexes reference the same model version |
| **AC4** | The active version is identifiable with one repository-level lookup |

**AC1 is about observation, not correctness.** Each index could be internally
perfect and AC1 would still be violated. This is the criterion that forces the
build-validate-publish sequence rather than incremental updates in place.

**AC2 is the rollback criterion**, and it is why validation (§14) must complete
before publication begins.

**AC4's "one lookup"** is a performance-shaped requirement with an architectural
consequence: there must be a single pointer, not a convention that five files
happen to agree.

---

## Part III — Online plane (§20 – §28)

### §21 Stage 13 — Intent Classifier (4 unnumbered)

| Criterion | Demand |
|---|---|
| `"What calls PaymentService?"` → `FIND_REFERENCES` | Routing is correct |
| `"Explain payment validation."` → `SEMANTIC_SEARCH` | |
| `"Trace checkout from API to database."` → `CROSS_LAYER_TRACE` | |
| Ambiguous queries must not silently route to an arbitrary reasoning strategy | Ambiguity is surfaced, not resolved |

**The fourth criterion mirrors §13 AC3 and §14's fourth.** The same principle
appears three times in the spec: *when the system cannot decide, it must say so
rather than pick.* Intent classification is where this matters most, because the
intent determines which reasoning mechanism runs — and §26's escalation ladder
cannot recover from a misroute, only from a validation failure.

### §22 Stage 14 — Retrieval and Context Engine (AC1–AC6)

| AC | Demand | Family |
|---|---|---|
| **AC1** | `FIND_REFERENCES` uses graph retrieval as primary | minimality |
| **AC2** | `LOCATE_SYMBOL` does not unnecessarily invoke vector search | minimality |
| **AC3** | `SEMANTIC_SEARCH` combines semantic and lexical where appropriate | correctness |
| **AC4** | Duplicate evidence is merged | minimality |
| **AC5** | All context items retain source provenance | provenance |
| **AC6** | Context stays within the configured token budget | boundedness |

**AC1–AC3 are about *not* using the expensive mechanism.** This is the retrieval
mirror of §26 AC1. The architecture's cost story depends on the router sending
most queries to the cheapest sufficient retriever.

**AC5 is stated twice in the spec** (here and §18) — once for the retrieval path,
once for the vector path. That duplication is a signal: provenance is the
property most easily lost when results are normalised, deduplicated, and
compressed, which is exactly what this stage does.

### §23 Stage 15 — Deterministic Reasoning (AC1–AC5)

| AC | Demand |
|---|---|
| **AC1** | Correct repository fact → correct answer |
| **AC2** | Unknown symbol → `Not found`, never an invented answer |
| **AC3** | LLM availability has no effect on deterministic queries |
| **AC4** | Every answer includes relevant evidence |
| **AC5** | Relationship queries can be validated against the graph exactly |

**AC3 is §34's first failure condition** ("LLM unavailable → deterministic queries
continue working"). It is the operational form of §41 Rule 1: the LLM is not on
the critical path for questions the repository can answer by itself.

**AC5's word "exactly"** is what makes §25 AC4 ("the answer must match the graph
result set within the defined response policy") meaningful. For a deterministic
query there *is* a correct answer set, so the answer can be checked for
completeness — not just for unsupported claims.

### §24 Stage 16 — Small-Model Reasoning (6 unnumbered)

| Criterion | Demand |
|---|---|
| Model receives repository evidence, not unrestricted assumptions | Grounded input |
| Generated claims can be extracted | Output is machine-checkable |
| Generated answer references available evidence | Grounded output |
| Model timeout/failure is handled | Isolation |
| Unsupported claims are detectable by the validator | §25 is reachable |
| Small-model failure can trigger escalation | §26 is reachable |

**The first and third criteria are the pair that makes §41 Rule 3 enforceable.**
Garbage in and garbage out are both blocked: the model sees only retrieved
evidence, and its output must cite that evidence.

**"Claims can be extracted"** is a structural requirement on the answer format.
Free prose cannot be validated; the answer must decompose into checkable claims.

### §25 Stage 17 — Answer Validation (AC1–AC5)

| AC | Demand |
|---|---|
| **AC1** Supported answer | Fully grounded → `PASS` |
| **AC2** Unsupported claim | Hallucinated relationship → `FAIL` |
| **AC3** Missing evidence | Needs more information → `INSUFFICIENT` |
| **AC4** Exact relationship validation | For "What calls PaymentService?", the answer matches the graph result set "within the defined response policy" |
| **AC5** Version validation | Evidence from an inactive version cannot validate an active-version answer |

**The three-valued `ValidationResult` is the design point.** `INSUFFICIENT` is not
a failure — it is the correct answer when the repository genuinely does not
contain the information. Collapsing it into `FAIL` would push the system toward
guessing.

§25.2 names six validation dimensions — grounding, citation correctness,
completeness, answer type, version consistency, confidence. Note that
**completeness only applies to deterministic result sets**, because only those
have a known-correct answer to compare against.

**AC5 is the last line of defence for version coherence.** Even with §19's atomic
publication, a cached answer or a stale retrieval result could carry evidence from
a superseded version. AC5 makes that unvalidatable.

**"Within the defined response policy" is undefined in the spec** — another
falsifiability gap (see Part V).

### §26 Stage 18 — Model Router and Escalation (AC1–AC5)

| AC | Demand |
|---|---|
| **AC1** | Deterministic queries do not invoke an LLM |
| **AC2** | Simple semantic questions initially use the small model |
| **AC3** | Small-model validation failure escalates to the complex model |
| **AC4** | Complex queries can directly select agentic execution |
| **AC5** | Repeated model failure terminates with an explicit insufficient-evidence response |

**AC3's trigger is validation failure, not model failure.** The escalation ladder
is driven by §25, which is what makes it principled rather than a retry loop.

**AC5 is the terminal case and it is deliberately not an error.** After
deterministic → small → complex → agent all fail, the system returns
*insufficient evidence* — it does not return the least-bad guess. This is §34's
"Complex model fails → Return insufficient evidence".

### §27 Stage 19 — MCP Tool Layer (AC1–AC7)

| AC | Demand |
|---|---|
| **AC1–AC5** | Agent can: search symbol, retrieve callers, retrieve callees, trace bounded dependencies, retrieve source evidence |
| **AC6** | Tool failure returns structured failure instead of crashing the agent |
| **AC7** | Tools do not expose storage implementation details |

**AC1–AC5 are deliberately one capability per tool.** The tool set is the
system's capability surface, and it mirrors §16's graph operations — the agent
gets exactly what the graph can answer, no more.

**AC6 is what makes §28 AC7 achievable.** An agent can only recover from a tool
failure if the failure arrives as data.

**AC7 is the storage seam.** The agent must not know whether callers come from a
graph table, a join, or an in-memory traversal — otherwise the storage layer can
never be replaced, and §41's boundary between repository truth and reasoning
erodes.

### §28 Stage 20 — ReAct Agent (AC1–AC8)

| AC | Demand | Family |
|---|---|---|
| **AC1** Multi-step trace | Produces `CheckoutController → CheckoutService → PaymentService → PaymentRepository` | correctness |
| **AC2** Evidence | Every transition has supporting evidence | provenance |
| **AC3** Cycle handling | Does not loop indefinitely on cyclic dependencies | boundedness |
| **AC4** Repeated tool call | Repeated *unproductive* calls detected | boundedness |
| **AC5** Maximum iterations | Terminates after configured max | boundedness |
| **AC6** Token budget | Terminates or compresses when budget exhausted | boundedness |
| **AC7** Tool failure | Recovers from recoverable failures | isolation |
| **AC8** No evidence | Returns insufficient evidence rather than inventing | honesty |

**Eight criteria, five of them about stopping.** This is the only component that
can fail by running forever, and it needs a separate guard for each way that can
happen: cycles (AC3), no-progress loops (AC4), absolute count (AC5), resource
exhaustion (AC6). Each can fire when the others do not.

**AC4's word "unproductive"** is the hard one — detecting that a *different* tool
call has not advanced the state requires tracking `visited_entities` and
comparing observations, not just counting calls.

**AC8 is §34's "Missing evidence → Do not claim certainty"** at the agent level.

---

## Part IV — Hardening and delivery (§29 – §32)

### §29 Stage 21 — Incremental Relationship Invalidation (AC1–AC6)

| AC | Demand | Family |
|---|---|---|
| **AC1** | Changing an unrelated file does not trigger unrelated semantic work | minimality |
| **AC2** | Changing a symbol definition triggers required relationship re-resolution | correctness |
| **AC3** | Unchanged source is not reparsed unnecessarily | minimality |
| **AC4** | Affected relationships are updated | correctness |
| **AC5** | Deleted symbols do not leave active dangling relationships | referential integrity |
| **AC6** | Final model is equivalent to a clean rebuild for the changed repository state | correctness |

**This is §9's hard sequel, and §4.6 is its design statement.** §9 works at the
granularity of files; §29 works at the granularity of *relationships*.

The motivating example is exact: `A.py → B.foo()`. If `B.py` changes, `A.py` is
byte-identical and §9 would reuse it untouched — yet the edge recorded in A may
now point at a symbol that moved, changed signature, or no longer exists.

**AC5 is the specific damage this prevents**: a dangling edge is worse than a
missing one, because it asserts a relationship to something that is gone.

**AC6 is the criterion that keeps AC1 and AC3 safe.** "Minimal work" is only
defensible if you can prove the result equals a from-scratch build. AC6 is what
distinguishes incremental indexing from incremental *corruption* — and it is the
single most valuable test in the whole incremental story, because it can be
checked mechanically: index incrementally, index clean, compare digests.

### §30 Stage 22 — Fault Tolerance (AC1–AC5)

Covered in detail under Family 3 above. The five criteria form a complete
lifecycle:

| AC | Phase |
|---|---|
| **AC1** | During — indexing continues |
| **AC2** | During — the file is marked `FAILED`/`PARTIAL` |
| **AC3** | After — the error is persisted |
| **AC4** | After — other files remain queryable |
| **AC5** | Later — fixing the file recovers on reindex |

**AC3 and AC4 are what make the degradation *usable*.** A system that survives a
broken file but forgets why is only marginally better than one that crashes.

### §31 Stage 23 — API / CLI (AC1–AC4)

| AC | Demand |
|---|---|
| **AC1** | One command indexes a repository |
| **AC2** | One command executes a natural-language query |
| **AC3** | Query output includes answer, intent, model/reasoning strategy, evidence, model version |
| **AC4** | Index status exposes files, symbols, relationships, model version, degraded files |

**AC3 and AC4 are observability criteria dressed as CLI criteria.** Every field
they require is one of the system's honesty guarantees made visible:
*model version* (§19), *evidence* (§25), *reasoning strategy* (§26), *degraded
files* (§30). The CLI is where the user can see that the system is being honest.

### §32 Stage 24 — End-to-End Integration (E001–E005)

Five named scenarios. Each exercises a different reasoning path:

| Scenario | Query | Path exercised | Expected |
|---|---|---|---|
| **E001** Locate Symbol | "Where is PaymentService implemented?" | FTS + deterministic | path + location + evidence |
| **E002** Dependency Query | "What calls PaymentService?" | Graph + deterministic | `CheckoutService`, `RefundService` |
| **E003** Impact Analysis | "What breaks if PaymentService changes?" | Graph + transitive | direct + bounded transitive dependents + evidence |
| **E004** Semantic Explanation | "Explain payment validation." | Vector + small model + validator | code + explanation + evidence + **no unsupported claims** |
| **E005** Agentic Trace | "Trace checkout from API request to payment persistence." | Agent + MCP | full 4-hop chain + evidence per transition |

**These five are the real acceptance test of the whole system.** They are
deliberately ordered by escalating mechanism: E001–E003 are deterministic,
E004 adds a model, E005 adds an agent. If E001–E003 need an LLM, §26 AC1 is
violated. If E004 returns a claim with no evidence, §25 AC2 is violated. If E005
does not terminate, §28 is violated.

Note that **E002 and E003 are the same graph query at different depths**, and
E005 is E003's chain made explicit. The fixture's expected graph appears three
times in the spec — §7, §16 AC1/AC2, and §32 E002/E005 — which is a deliberate
consistency check across layers.

---

## Part V — The summary layers

### §33 Quality Gates (26 items)

A flat checklist: discovery, snapshot, change detection, parsing, extraction,
resolution, validation, semantic model, graph, FTS5, vector, version consistency,
incremental indexing, fault isolation, intent, context ranking, deterministic
reasoning, small-model reasoning, answer validation, model escalation, MCP tools,
agent tool calling, agent termination, evidence generation, end-to-end queries.

**All 26 must pass.** This is the release gate, and it is a union of the stage
criteria rather than a new demand — every gate maps to at least one AC in
§8–§32.

### §34 Critical Failure Conditions (12)

"Must never silently succeed." The word *silently* is the whole criterion — most
of these are permitted to fail, just not quietly.

| Failure | Required behaviour | Related AC |
|---|---|---|
| LLM unavailable | Deterministic queries continue working | §23 AC3, §26 AC1 |
| Small model fails validation | Escalate | §26 AC3 |
| Complex model fails | Return insufficient evidence | §26 AC5 |
| Broken file | Repository remains queryable | §30 AC1, AC4 |
| Unknown symbol | Do not hallucinate | §13 AC4, §23 AC2 |
| Ambiguous relationship | Mark ambiguous | §13 AC3, §14 |
| Agent loop | Terminate | §28 AC3–AC6 |
| Tool failure | Structured failure | §27 AC6, §28 AC7 |
| Mixed index versions | Never expose as one state | §19 AC1 |
| Missing evidence | Do not claim certainty | §28 AC8, §25 AC3 |
| Deleted symbol | Remove stale active relationships | §29 AC5 |
| Failed indexing | Keep previous valid version active | §19 AC2, §15 immutability |

**This table is the best single-page summary of the system's philosophy.** Every
row is a decision to degrade *visibly* rather than succeed *falsely*.

### §40 Definition of Done (10 properties)

The test suite must prove: correctness, incremental updates, fault isolation,
retrieval correctness, context control, model escalation, answer grounding,
evidence provenance, agent termination, version consistency.

**These are the ten properties, not ten features.** Note what is *not* on the
list: speed, accuracy percentage, coverage. Everything here is a property that
either holds or does not.

### §41 Final Architectural Contract — the three rules

> **Rule 1** — The LLM must not become the source of repository truth.
> **Rule 2** — The agent must not replace deterministic repository capabilities.
> **Rule 3** — No generated answer is trusted merely because a model generated it.

**"Everything else in MAAT exists to enforce those three rules."**

These are the generative axioms. Read them against the eight families in Part I:

| Rule | Enforced by families |
|---|---|
| Rule 1 | Determinism, provenance, version coherence |
| Rule 2 | Minimality (§26 AC1, §22 AC1–AC3), replaceability |
| Rule 3 | Honesty, provenance, boundedness |

The three-layer diagram in §41 — **Repository Truth → Reasoning → Validation** —
is the architectural form of Rule 1: the reasoning layer is *downstream* of truth
and can never write back to it. The validation layer sits between reasoning and
the user precisely because Rule 3 says the reasoning layer cannot be trusted on
its own authority.

---

## Part VI — Where the criteria are weak

Consistent with the standing rule that a spec/implementation conflict must be
surfaced rather than silently resolved, these are the criteria that **cannot be
falsified as written**. They are not implementation gaps — they are specification
gaps, and they should be sharpened before the stage that depends on them is
built.

| Criterion | Problem | Sharper form |
|---|---|---|
| **§9 AC5** Rename | Conditional on "where supported" and "when cache policy allows reuse" — satisfiable vacuously by declaring a restrictive policy | "A rename must not change any entity ID that survives the move, and must not require reparsing file contents" |
| **§16 AC3** Transitive traversal | "within depth N" — N never fixed | State N, or state that N is caller-supplied and that the bound is enforced |
| **§13 AC3** Ambiguous resolution | "Ambiguous" is undefined — ambiguity is a policy decision, not a fact | Define the ambiguity predicate (e.g. ">1 candidate with equal confidence") |
| **§21** Intent ambiguity | "must not silently route to an arbitrary strategy" — no threshold for when a query counts as ambiguous | Define the confidence threshold and the clarification response |
| **§25 AC4** Exact relationship validation | "within the defined response policy" — the policy is never defined | Define the policy (e.g. exact set equality for `FIND_REFERENCES`) |
| **§13 AC5** No hallucinated relationship | Constrains a mechanism, not an output; not directly observable | Test the proxy: every relationship carries evidence (§13 AC6) and confidence matches status |
| **§11 AC3** No AST leakage | Structural and negative; only checkable by absence | Enumerate the allowed fact vocabulary exhaustively |
| **§10 AC6** Partial parsing | "Where Tree-sitter provides a usable partial tree" — "usable" undefined | Define usable (e.g. ≥1 clean top-level statement) — **the implementation already does this** via `_has_clean_top_level_statement` |

**§10 AC6 is the model to follow.** The implementation made the undefined word
concrete — "usable" became "at least one clean top-level statement" — and the
behaviour is testable as a result. The other seven deserve the same treatment.

---

## Part VII — Milestone map

From §37's dependency order, grouped into the milestones this project actually
uses:

| Milestone | Stages | Spec sections | Status |
|---|---|---|---|
| **M1** | 1–5 + 22 | §7–§12, §30 (+ §19 AC3 partial) | **Complete** — 137 tests passing |
| **M2** | 6–8 | §13, §14, §15 | Not started |
| **M3** | 9–12 | §16, §17, §18, §19 | Not started |
| **M4** | 13–16 | §21, §22, §23, §24 | Not started |
| **M5** | 17–20 | §25, §26, §27, §28 | Not started |
| **M6** | 21–25 | §29, §30 (done), §31, §32 | Not started |

Two observations:

- **§30 (fault tolerance) is built early** relative to §37's order — it is stage 22
  in the spec but landed in M1. That was the right call: isolation is a property
  of the parser and pipeline, not a later layer, and retrofitting it would mean
  reworking the status ladder.
- **§29 (incremental relationship invalidation) is listed last but is M2-relevant.**
  §37 places it at position 22 because it needs resolution (§13) to exist first —
  there is nothing to invalidate until edges are resolved. But it is the direct
  successor to §9, and the longer it is deferred after M2, the more M2's design
  will have to accommodate it. **Worth pulling forward into M2's design phase even
  if it is implemented later.**

---

## Part VIII — Status at a glance

| Section | Criteria | Covered by tests |
|---|---|---|
| §7 | 7 | 7 |
| §8 | 5 | 5 |
| §9 | 6 | 6 |
| §10 | 6 | 6 |
| §11 | 3 | 3 |
| §12 | 6 | 6 |
| §13 | 6 | 0 (M2) |
| §14 | 6 | 0 (M2) |
| §15 | 6 | 0 (M2) |
| §16 | 5 | 0 (M3) |
| §17 | 3 | 0 (M3) |
| §18 | 2 | 0 (M3) |
| §19 | 4 | 1 (AC3) |
| §21 | 4 | 0 (M4) |
| §22 | 6 | 0 (M4) |
| §23 | 5 | 0 (M4) |
| §24 | 6 | 0 (M4) |
| §25 | 5 | 0 (M5) |
| §26 | 5 | 0 (M5) |
| §27 | 7 | 0 (M5) |
| §28 | 8 | 0 (M5) |
| §29 | 6 | 0 (M6) |
| §30 | 5 | 5 |
| §31 | 4 | 0 (M6) |
| §32 | 5 | 0 (M6) |
| **Stage total** | **131** | **39 (30 %)** |

Plus §33 (26 gates), §34 (12 failure conditions), §40 (10 properties), §41 (3
rules) — these become achievable only as the stages above complete.

See `docs/test-acceptance-matrix.md` for the per-test mapping of the 39 covered
criteria.
