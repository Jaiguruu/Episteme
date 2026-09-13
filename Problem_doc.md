# MAAT: Repository Intelligence Agent

## Problem, Architecture & Implementation Specification

**Status:** Proposed
**Version:** 1.0
**Scope:** Offline repository intelligence pipeline + online query/reasoning pipeline
**Primary objective:** Build a versioned semantic representation of a software repository and provide reliable, evidence-backed answers through intent-aware retrieval, model routing, validation, and bounded agentic reasoning.

---

# 1. Problem Statement

Understanding a large software repository requires answering questions about its structure, behavior, dependencies, and architecture.

Typical developer questions include:

```text
Where is PaymentService implemented?

What calls PaymentService?

Explain payment validation.

What breaks if PaymentService changes?

Trace checkout from API request to payment persistence.
```

Traditional search is effective for exact text but weak at structural and semantic questions.

An LLM can reason over source code but should not be responsible for discovering repository facts from scratch. Doing so introduces:

* hallucinated symbols
* incorrect dependencies
* incomplete call chains
* stale information after code changes
* excessive context consumption
* inconsistent answers
* unnecessary model cost

MAAT therefore separates **repository knowledge creation** from **reasoning**.

```text
OFFLINE

Repository
    ↓
Semantic Model
    ↓
Indexes
```

and:

```text
ONLINE

User Query
    ↓
Intent
    ↓
Retrieval
    ↓
Reasoning
    ↓
Validation
    ↓
Evidence-backed Answer
```

The core thesis is:

> **MAAT is not an LLM over a codebase. It is a versioned semantic system over a codebase, with an LLM-powered reasoning layer on top.**

This is consistent with the original MAAT design objective and definition of done. 

---

# 2. Goals

MAAT must:

1. Parse a repository using Tree-sitter.
2. Extract language-neutral semantic information.
3. Construct a canonical repository semantic model.
4. Resolve and validate structural relationships.
5. Preserve source provenance.
6. Support incremental repository updates.
7. Maintain version-consistent indexes.
8. Provide graph, lexical, and vector retrieval.
9. Classify natural-language queries into explicit intents.
10. Route queries to the cheapest reliable reasoning strategy.
11. Use deterministic reasoning where possible.
12. Use a small model for straightforward semantic synthesis.
13. Escalate to a complex model when validation fails or complexity requires it.
14. Provide MCP-based repository tools.
15. Support bounded ReAct-style agentic reasoning.
16. Validate generated answers against repository evidence.
17. Isolate malformed files without making the repository unusable.
18. Provide an end-to-end demonstrable system.

---

# 3. Non-Goals

The prototype will not:

* autonomously modify source code
* deploy applications
* merge pull requests
* execute arbitrary repository commands
* replace an IDE
* perfectly understand every programming language
* use an LLM to construct the entire repository graph
* build a general-purpose software ontology
* start with a frontend
* require an LLM for deterministic repository indexing

---

# 4. Design Principles

## 4.1 Semantic Model Is the Source of Truth

The canonical semantic model is authoritative.

Graph, FTS5, and vector indexes are projections.

```text
                 Canonical Semantic Model
                         │
              ┌──────────┼──────────┐
              ↓          ↓          ↓
            Graph       FTS5      Vector
```

The system must not treat the indexes themselves as independent sources of truth.

---

## 4.2 Separate Parsing From Semantic Resolution

Tree-sitter provides syntax.

It does not necessarily determine what every symbol refers to.

```text
AST Extraction
      ≠
Semantic Resolution
```

Relationships therefore carry resolution states:

```text
RESOLVED_EXACT
RESOLVED_HEURISTIC
AMBIGUOUS
UNRESOLVED
```

MAAT should prefer an explicit unresolved relationship over an incorrect confident relationship.

---

## 4.3 Separate Observed From Derived Relationships

### Observed

Directly extracted or resolved:

```text
CONTAINS
IMPORTS
CALLS
REFERENCES
INHERITS
IMPLEMENTS
```

### Derived

Computed from observed relationships:

```text
DEPENDS_ON
TRANSITIVELY_DEPENDS_ON
IMPACTED_BY
REACHABLE_FROM
```

---

## 4.4 Reasoning Complexity Must Be Earned

```text
Deterministic
      ↓
Small Model
      ↓
Complex Model + Agent
```

Do not use the largest model when the graph can answer the question exactly.

---

## 4.5 Validation Controls Trust

Every generated answer must pass through validation.

```text
Answer
   ↓
Claims
   ↓
Evidence
   ↓
Repository Truth
   ↓
Validation
   ↓
PASS / FAIL / INSUFFICIENT
```

---

## 4.6 Incremental Processing Must Account for Relationship Invalidation

A changed file does not necessarily imply that every dependent file must be reparsed.

Conversely, an unchanged file may contain relationships whose targets changed.

Therefore:

```text
Parse Invalidation
        ≠
Relationship Invalidation
```

The incremental system must eventually support both.

---

# 5. High-Level Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                    OFFLINE KNOWLEDGE PLANE                   │
│                                                              │
│ Repository                                                   │
│    ↓                                                         │
│ Snapshot / Change Detection                                  │
│    ↓                                                         │
│ Tree-sitter Parsing                                          │
│    ↓                                                         │
│ Language Extractors                                          │
│    ↓                                                         │
│ Semantic IR                                                  │
│    ↓                                                         │
│ Normalization                                                │
│    ↓                                                         │
│ Symbol / Relationship Resolution                             │
│    ↓                                                         │
│ Validation + Provenance                                      │
│    ↓                                                         │
│ Canonical Semantic Model                                     │
│    ↓                                                         │
│ ┌──────────────┬──────────────┬───────────────┐              │
│ │ Graph        │ FTS5         │ Vector        │              │
│ └──────────────┴──────────────┴───────────────┘              │
│    ↓                                                         │
│ Atomic Model Publication                                     │
└──────────────────────────────┬───────────────────────────────┘
                               │
                         Versioned State
                               │
┌──────────────────────────────┴───────────────────────────────┐
│                    ONLINE REASONING PLANE                    │
│                                                              │
│ User Query                                                   │
│    ↓                                                         │
│ Intent Classifier                                             │
│    ↓                                                         │
│ Use-case Router                                               │
│    ↓                                                         │
│ Retrieval / Context Engine                                   │
│    ↓                                                         │
│ ┌───────────────────────────────────────────────┐             │
│ │ Deterministic                                │             │
│ │ Small Model                                  │             │
│ │ Complex Model + ReAct Agent                  │             │
│ └───────────────────────┬───────────────────────┘             │
│                         ↓                                    │
│                    Answer Validator                           │
│                         ↓                                    │
│                  Evidence-backed Answer                      │
└──────────────────────────────────────────────────────────────┘
```

---

# 6. Offline Pipeline

The offline pipeline is responsible for creating repository knowledge.

```text
Repository
    ↓
Repository Snapshot
    ↓
Change Detection
    ↓
File Classification
    ↓
Tree-sitter Parsing
    ↓
Language Extraction
    ↓
Semantic IR
    ↓
Normalization
    ↓
Symbol Resolution
    ↓
Relationship Validation
    ↓
Canonical Semantic Model
    ↓
Graph / FTS5 / Vector
    ↓
Atomic Publication
```

---

# 7. Stage 0: Test Fixtures and Contracts

## Objective

Define the repository fixture and contracts before implementing the pipeline.

Use a small synthetic repository that contains known relationships.

Example:

```text
demo_repo/
├── api/
│   └── checkout_controller.py
├── services/
│   ├── checkout_service.py
│   ├── payment_service.py
│   └── refund_service.py
├── repositories/
│   └── payment_repository.py
├── models/
│   └── payment.py
└── broken/
    └── broken_service.py
```

Expected graph:

```text
CheckoutController
        ↓
CheckoutService
        ↓
PaymentService
        ↓
PaymentRepository

RefundService
        ↓
PaymentService
```

## Deliverables

* Repository fixture
* Semantic IR schema
* Entity ID contract
* Relationship contract
* Evidence contract
* Model-version contract
* Test helper utilities
* Expected semantic graph

## Acceptance Criteria

* Fixture contains at least one complete call chain.
* Fixture contains direct and transitive dependencies.
* Fixture contains an intentionally broken file.
* Expected symbols are explicitly defined.
* Expected relationships are explicitly defined.
* Tests can compare produced semantic data against expected data.
* No implementation is accepted without a corresponding behavioral test.

---

# 8. Stage 1: Repository Snapshot

## Objective

Create a stable representation of the repository at a point in time.

Each file must have:

```text
path
language
content_hash
size
parse_status
parse_error
model_version
```

## Deliverables

* Repository scanner
* File manifest
* Content hashing
* Language detection
* Snapshot representation

## Acceptance Criteria

### AC1: Complete discovery

Given a repository:

```text
10 source files
```

the snapshot identifies all supported source files.

### AC2: Stable hashes

Unchanged files produce identical hashes across runs.

### AC3: Content sensitivity

Changing file contents changes the hash.

### AC4: Non-source filtering

Configured ignored/generated/binary files are excluded.

### AC5: Deterministic snapshot

The same repository state produces the same file manifest.

---

# 9. Stage 2: Incremental Change Detection

## Objective

Determine which files require processing.

```text
Previous Snapshot
        +
Current Snapshot
        ↓
Change Detector
        ↓
New
Changed
Deleted
Unchanged
```

## Deliverables

* Manifest persistence
* Change detector
* New-file detection
* Modified-file detection
* Deleted-file detection
* Rename detection where supported
* Incremental statistics

## Acceptance Criteria

### AC1: Initial indexing

No previous manifest:

```text
100 files
→ 100 files scheduled
```

### AC2: No-change run

```text
100 files
→ 0 files reparsed
```

### AC3: Single modification

```text
100 files
1 modified
→ 1 file reparsed
```

### AC4: Deletion

Deleted file is detected and its semantic entities become stale.

### AC5: Rename

A renamed file does not unnecessarily trigger semantic recomputation when content is unchanged and cache policy allows reuse.

### AC6: Interrupted update

An interrupted indexing operation does not publish an incomplete semantic version.

---

# 10. Stage 3: Tree-sitter Parsing

## Objective

Convert source files into syntax trees.

```text
Source
  ↓
Tree-sitter
  ↓
AST
```

## Deliverables

* Parser abstraction
* Tree-sitter integration
* Language registry
* Parse status handling
* Source location tracking
* Parse error capture

## Acceptance Criteria

### AC1: Valid file

Valid source produces an AST.

### AC2: Syntax error

Malformed source does not crash repository indexing.

### AC3: Empty file

Empty source is handled without exception.

### AC4: Unsupported language

Unsupported language produces an explicit unsupported status.

### AC5: Source locations

Extracted nodes preserve line and column information.

### AC6: Partial parsing

Where Tree-sitter provides a usable partial tree, valid regions can be retained and the file marked degraded.

---

# 11. Stage 4: Language Extractors

## Objective

Convert language-specific AST structures into a common semantic representation.

Extract:

```text
Files
Symbols
Imports
Declarations
Calls
References
Inheritance
Implementations
Documentation
Source locations
```

## Deliverables

* Language extractor interface
* Initial language implementation
* Symbol extraction
* Import extraction
* Call extraction
* Reference extraction
* Class/interface extraction
* Documentation extraction

## Acceptance Criteria

For the fixture:

```text
PaymentService
```

must be extracted as a symbol.

The system must identify:

```text
CheckoutService → PaymentService
RefundService   → PaymentService
```

as candidate call relationships.

No language-specific AST structure should leak into the canonical semantic model.

---

# 12. Stage 5: Semantic IR

## Objective

Create a language-neutral intermediate representation.

## Core entities

```text
Repository
File
Symbol
Relationship
SemanticChunk
Evidence
ModelVersion
```

## Symbol

```text
id
file_id
name
qualified_name
symbol_type
signature
location
documentation
content_hash
model_version
```

## Relationship

```text
id
source_symbol_id
target_symbol_id
relationship_type
resolution_status
confidence
source_location
model_version
```

## Semantic Chunk

```text
id
symbol_id
text
chunk_type
embedding_id
token_count
model_version
```

## Evidence

```text
id
entity_id
file_id
start_line
end_line
retrieval_source
score
model_version
```

## Deliverables

* Pydantic/domain models
* Stable ID generation
* Serialization format
* Schema validation
* Semantic IR tests

## Acceptance Criteria

* Identical source produces stable entity IDs.
* Different symbols do not collide.
* Relationships reference valid entities.
* Evidence references valid source locations.
* Every semantic entity belongs to a model version.
* Invalid semantic objects are rejected before indexing.

---

# 13. Stage 6: Symbol and Relationship Resolution

## Objective

Resolve extracted references to actual repository entities.

Example:

```python
payment_service.process()
```

must be transformed from syntax:

```text
receiver = payment_service
method = process
```

into a semantic relationship where possible:

```text
CheckoutService
      |
     CALLS
      ↓
PaymentService.process
```

## Resolution states

```text
RESOLVED_EXACT
RESOLVED_HEURISTIC
AMBIGUOUS
UNRESOLVED
```

## Deliverables

* Symbol resolver
* Import resolver
* Qualified-name resolver
* Receiver resolution
* Call-target resolution
* Ambiguity handling
* Resolution confidence

## Acceptance Criteria

### AC1: Exact resolution

Known symbol reference resolves to the correct symbol.

### AC2: Namespace separation

Two symbols with the same name in different modules remain distinct.

### AC3: Ambiguous resolution

Ambiguous receiver is marked ambiguous rather than assigned an arbitrary target.

### AC4: Unknown target

Unknown symbol is represented as unresolved.

### AC5: No hallucinated relationship

The resolver must never create a relationship merely because a model predicts one.

### AC6: Relationship provenance

Every resolved relationship points back to source evidence.

---

# 14. Stage 7: Relationship Validation

## Objective

Validate semantic relationships before they enter the canonical model.

Validation includes:

```text
duplicate detection
entity existence
relationship validity
source location validity
resolution status
confidence
version consistency
```

## Deliverables

* Relationship validator
* Duplicate detector
* Orphan detector
* Confidence policy
* Validation report

## Acceptance Criteria

* Duplicate relationships are removed or rejected.
* Relationships referencing missing entities are rejected.
* Invalid source locations are rejected.
* Ambiguous relationships remain explicitly marked.
* Validation produces a machine-readable report.
* Invalid semantic data cannot be published.

---

# 15. Stage 8: Canonical Semantic Model

## Objective

Persist the validated repository semantic state.

```text
Repository
├── Files
├── Symbols
├── Relationships
├── Semantic Chunks
├── Evidence
└── Model Version
```

## Deliverables

* Canonical repository store
* CRUD/query interface
* Version management
* Entity lookup
* Relationship lookup
* Provenance lookup

## Acceptance Criteria

* All semantic entities can be retrieved by stable ID.
* Symbols can be retrieved by qualified name.
* Relationships can be queried by source/target/type.
* Evidence can be retrieved for an entity.
* A complete model can be reconstructed from persistence.
* Model versions are immutable after publication.

---

# 16. Stage 9: Graph Projection

## Objective

Project the canonical semantic model into a graph optimized for structural queries.

```text
Symbol
   ↓
Relationship
   ↓
Symbol
```

## Deliverables

* Graph abstraction
* Node creation
* Edge creation
* Caller lookup
* Callee lookup
* Direct dependency lookup
* Transitive traversal
* Cycle detection

## Acceptance Criteria

### AC1: Direct callers

```text
find_callers(PaymentService)
```

returns:

```text
CheckoutService
RefundService
```

### AC2: Direct callees

```text
find_callees(CheckoutService)
```

returns:

```text
PaymentService
```

### AC3: Transitive traversal

Bounded dependency traversal returns all reachable nodes within depth N.

### AC4: Cycles

Graph traversal terminates on cyclic graphs.

### AC5: Version consistency

Graph version equals active semantic model version.

---

# 17. Stage 10: FTS5 Projection

## Objective

Provide fast exact and lexical retrieval.

Primary use cases:

```text
LOCATE_SYMBOL
BROWSE_STRUCTURE
exact code lookup
path lookup
identifier lookup
```

## Deliverables

* FTS5 schema
* Symbol indexing
* Path indexing
* Documentation indexing
* Search API
* Ranking

## Acceptance Criteria

```text
search_symbol("PaymentService")
```

returns the correct symbol.

Search must support:

* exact name
* qualified name
* partial name
* path
* documentation

No result should be returned from an inactive semantic model.

---

# 18. Stage 11: Vector Projection

## Objective

Support semantic retrieval.

Primary use cases:

```text
SEMANTIC_SEARCH
semantic explanations
documentation retrieval
concept discovery
```

## Deliverables

* Chunking strategy
* Embedding interface
* Vector index
* Similarity retrieval
* Metadata filtering
* Version filtering

## Acceptance Criteria

A semantic query such as:

```text
How does the system validate a payment?
```

retrieves relevant payment-validation code or documentation even when the query does not use exact source terminology.

Vector retrieval must retain:

```text
symbol_id
file_id
model_version
source location
```

so results can become evidence.

---

# 19. Stage 12: Atomic Index Publication

## Objective

Ensure all indexes represent the same repository version.

```text
Build V2
   ↓
Validate V2
   ↓
Graph V2
FTS5 V2
Vector V2
   ↓
Consistency Check
   ↓
Publish V2
```

## Deliverables

* Model version manager
* Index version metadata
* Validation gate
* Atomic active-version pointer
* Rollback behavior

## Acceptance Criteria

### AC1

No query can observe:

```text
Graph V2
FTS V1
Vector V1
```

as one state.

### AC2

Failed V2 validation leaves V1 active.

### AC3

All published indexes reference the same model version.

### AC4

The active version can be identified with one repository-level lookup.

---

# 20. Online Pipeline

The online pipeline starts from an already-built semantic repository.

```text
User Query
    ↓
Intent Classifier
    ↓
Use-case Router
    ↓
Retrieval Plan
    ↓
Context Engine
    ↓
Reasoning Strategy
    ↓
Answer
    ↓
Validation
    ↓
Evidence-backed Response
```

---

# 21. Stage 13: Intent Classifier

## Objective

Determine what kind of repository question the user is asking.

## Initial Intent Taxonomy

| Intent               | Retrieval            | Reasoning     |
| -------------------- | -------------------- | ------------- |
| `LOCATE_SYMBOL`      | FTS + Graph          | Deterministic |
| `FIND_REFERENCES`    | Graph                | Deterministic |
| `TRACE_DEPENDENCIES` | Graph                | Deterministic |
| `SEMANTIC_SEARCH`    | Vector + FTS         | Small model   |
| `BROWSE_STRUCTURE`   | Graph                | Deterministic |
| `CROSS_LAYER_TRACE`  | Graph + FTS + Vector | Agent         |
| `AMBIGUOUS`          | Clarification        | None          |

## Intent Contract

```text
QueryIntent {
    intent
    entity
    target
    complexity
    confidence
}
```

## Deliverables

* Intent schema
* Intent classifier
* Classification confidence
* Routing rules
* Ambiguity handling

## Acceptance Criteria

```text
"What calls PaymentService?"
```

must classify as:

```text
FIND_REFERENCES
```

```text
"Explain payment validation."
```

must classify as:

```text
SEMANTIC_SEARCH
```

```text
"Trace checkout from API to database."
```

must classify as:

```text
CROSS_LAYER_TRACE
```

Ambiguous queries must not silently route to an arbitrary reasoning strategy.

---

# 22. Stage 14: Retrieval and Context Engine

## Objective

Construct the minimum useful evidence set for a query.

```text
Query
 ↓
Intent
 ↓
Retrieval Strategy
 ↓
Parallel Retrieval
 ↓
Normalize
 ↓
Deduplicate
 ↓
Rank
 ↓
Context Expansion
 ↓
Compression
 ↓
Token Budget
 ↓
Final Context
```

## Deliverables

* Retrieval planner
* Graph retriever
* FTS retriever
* Vector retriever
* Result normalization
* Deduplication
* Ranking
* Context compression
* Token budgeting

## Acceptance Criteria

### AC1

`FIND_REFERENCES` uses graph retrieval as its primary source.

### AC2

`LOCATE_SYMBOL` does not unnecessarily invoke vector search.

### AC3

`SEMANTIC_SEARCH` combines semantic and lexical retrieval where appropriate.

### AC4

Duplicate evidence is merged.

### AC5

All context items retain source provenance.

### AC6

Context remains within the configured token budget.

---

# 23. Stage 15: Deterministic Reasoning Engine

## Objective

Answer questions that can be computed directly from the semantic model.

Examples:

```text
Where is PaymentService?
What calls PaymentService?
What imports X?
What are the direct callees of X?
What are the direct dependencies of X?
```

## Deliverables

* Deterministic query handlers
* Graph traversal operations
* Symbol lookup operations
* Result formatter
* Evidence attachment

## Acceptance Criteria

### AC1

Correct repository fact produces correct answer.

### AC2

Unknown symbol produces:

```text
Not found
```

rather than an invented answer.

### AC3

LLM availability has no effect on deterministic queries.

### AC4

Every answer includes relevant evidence.

### AC5

Relationship queries can be validated against the graph exactly.

---

# 24. Stage 16: Small-Model Reasoning

## Objective

Use a smaller model when retrieved evidence is sufficient but natural-language synthesis is required.

Example:

```text
Explain payment validation.
```

Pipeline:

```text
Query
 ↓
Intent
 ↓
Retrieve evidence
 ↓
Context
 ↓
Small Model
 ↓
Answer
```

## Deliverables

* Model interface
* Structured prompt
* Evidence-aware generation
* Structured answer format
* Model failure handling

## Acceptance Criteria

* Model receives repository evidence rather than unrestricted repository assumptions.
* Generated claims can be extracted.
* Generated answer references available evidence.
* Model timeout/failure is handled.
* Unsupported claims are detectable by the validator.
* Small-model failure can trigger escalation.

---

# 25. Stage 17: Answer Validation

## Objective

Determine whether an answer is sufficiently correct to return.

Validation must be query-type-aware.

---

## 25.1 Claim Extraction

Example:

```text
CheckoutService and RefundService call PaymentService.
```

becomes:

```text
C1:
CheckoutService → CALLS → PaymentService

C2:
RefundService → CALLS → PaymentService
```

---

## 25.2 Validation Dimensions

### Grounding

Is each claim supported by repository evidence?

### Citation correctness

Does the cited source actually support the claim?

### Completeness

For deterministic result sets, were expected entities omitted?

### Answer type

Does the answer match what the query requires?

### Version consistency

Does evidence belong to the currently active model version?

### Confidence

How strong is the underlying evidence?

---

## Validator Contract

```text
ValidationResult {
    status:
        PASS
        FAIL
        INSUFFICIENT

    claims: [
        {
            claim
            supported
            evidence_ids
            confidence
        }
    ]

    grounding_score
    citation_score
    completeness_score
    failure_reason
}
```

## Deliverables

* Claim extractor
* Evidence matcher
* Grounding validator
* Citation validator
* Completeness validator
* Query-type-specific validators
* Validation result schema

## Acceptance Criteria

### AC1: Supported answer

Fully grounded answer:

```text
PASS
```

### AC2: Unsupported claim

Answer containing a hallucinated relationship:

```text
FAIL
```

### AC3: Missing evidence

Answer requiring more repository information:

```text
INSUFFICIENT
```

### AC4: Exact relationship validation

For:

```text
What calls PaymentService?
```

the answer must match the graph result set within the defined response policy.

### AC5: Version validation

Evidence from an inactive model version cannot validate an active-version answer.

---

# 26. Stage 18: Model Router and Escalation

## Objective

Route each query to the least expensive reasoning mechanism capable of producing a validated answer.

```text
                Query
                  ↓
                Intent
                  ↓
             Execution Plan
                  ↓
        ┌─────────┴─────────┐
        ↓                   ↓
 Deterministic          Model Required
                            ↓
                       Small Model
                            ↓
                       Validator
                      /          \
                   PASS          FAIL
                    ↓             ↓
                 Answer       Complex Model
                                  ↓
                              Agent / MCP
                                  ↓
                              Validator
```

## Deliverables

* Reasoning strategy selector
* Model router
* Escalation policy
* Retry policy
* Failure classification
* Cost/latency instrumentation

## Acceptance Criteria

### AC1

Deterministic queries do not invoke an LLM.

### AC2

Simple semantic questions initially use the small model.

### AC3

Small-model validation failure escalates to the complex model.

### AC4

Complex queries can directly select agentic execution.

### AC5

Repeated model failure terminates with an explicit insufficient-evidence response.

---

# 27. Stage 19: MCP Tool Layer

## Objective

Expose repository capabilities to agents through a stable tool boundary.

```text
Agent
  ↓
MCP
  ↓
MAAT Tools
  ↓
Semantic Model / Indexes
```

## Initial Tools

```text
search_symbol
search_code
find_callers
find_callees
trace_dependencies
get_file
```

## Tool Contract

Every tool should define:

```text
name
description
input schema
output schema
errors
version
```

## Deliverables

* MCP server
* Tool schemas
* Tool implementations
* Error contracts
* Tool-level tests
* Evidence-preserving tool responses

## Acceptance Criteria

### AC1

Agent can search for a symbol.

### AC2

Agent can retrieve callers.

### AC3

Agent can retrieve callees.

### AC4

Agent can trace bounded dependencies.

### AC5

Agent can retrieve source evidence.

### AC6

Tool failure returns structured failure instead of crashing the agent.

### AC7

Tools do not expose storage implementation details to the agent.

---

# 28. Stage 20: ReAct Agent

## Objective

Enable bounded multi-step reasoning for questions that cannot be answered through a single retrieval operation.

```text
Query
 ↓
Plan
 ↓
Reason
 ↓
Tool
 ↓
Observation
 ↓
Reason
 ↓
Tool
 ↓
Observation
 ↓
Answer
```

## Agent State

```text
query
intent
complexity
plan
current_step
tool_calls
observations
evidence
visited_entities
token_budget
iteration_count
status
```

## Deliverables

* Agent state machine
* ReAct loop
* Tool invocation
* Observation handling
* Evidence accumulation
* Loop detection
* Iteration limits
* Token budget
* Termination logic

## Acceptance Criteria

### AC1: Multi-step trace

Agent can produce:

```text
CheckoutController
→ CheckoutService
→ PaymentService
→ PaymentRepository
```

### AC2: Evidence

Every transition has supporting evidence.

### AC3: Cycle handling

Agent does not loop indefinitely on cyclic dependencies.

### AC4: Repeated tool call

Repeated unproductive calls are detected.

### AC5: Maximum iterations

Agent terminates after configured maximum iterations.

### AC6: Token budget

Agent terminates or compresses context when budget is exhausted.

### AC7: Tool failure

Agent can recover from recoverable tool failures.

### AC8: No evidence

Agent returns insufficient evidence rather than inventing a conclusion.

---

# 29. Stage 21: Incremental Relationship Invalidation

## Objective

Extend incremental indexing beyond file-level parsing.

Consider:

```text
A.py → B.foo()
```

If B changes:

```text
B.py changed
```

MAAT must determine:

```text
Does A.py need reparsing?
Does A.py's relationship need re-resolution?
Which semantic entities become stale?
```

## Deliverables

* Dependency-aware invalidation
* Relationship dependency tracking
* Re-resolution queue
* Stale relationship detection
* Minimal recomputation planner

## Acceptance Criteria

### AC1

Changing an unrelated file does not trigger unrelated semantic work.

### AC2

Changing a symbol definition triggers required relationship re-resolution.

### AC3

Unchanged source does not get reparsed unnecessarily.

### AC4

Affected relationships are updated.

### AC5

Deleted symbols do not leave active dangling relationships.

### AC6

Final model is equivalent to a clean rebuild for the changed repository state.

---

# 30. Stage 22: Fault Tolerance

## Objective

Prevent local repository failures from becoming system-wide failures.

```text
Valid Files
+
Broken File
      ↓
Indexer
      ↓
Valid semantic state
+
Degraded file
```

## Deliverables

* File-level isolation
* Parse quarantine
* Partial parse handling
* Error reporting
* Degraded-state metadata
* Recovery on subsequent reindex

## Acceptance Criteria

### AC1

One malformed file does not stop repository indexing.

### AC2

Broken file is marked:

```text
FAILED
```

or:

```text
PARTIAL
```

### AC3

Error is persisted.

### AC4

Other files remain queryable.

### AC5

Fixing the file allows successful reindexing.

---

# 31. Stage 23: API / CLI

## Objective

Expose the system through a minimal usable interface.

## Commands

```bash
maat index ./demo_repo
```

```bash
maat query "What calls PaymentService?"
```

```bash
maat status
```

```bash
maat inspect PaymentService
```

## Deliverables

* CLI
* Query API
* Index API
* Repository status API
* Error handling
* JSON output mode

## Acceptance Criteria

### AC1

One command can index a repository.

### AC2

One command can execute a natural-language query.

### AC3

Query output includes:

```text
answer
intent
model/reasoning strategy
evidence
model version
```

### AC4

Index status exposes:

```text
files
symbols
relationships
model version
degraded files
```

---

# 32. Stage 24: End-to-End Integration

## Objective

Connect the complete system.

```text
Repository
    ↓
Parse
    ↓
Semantic Model
    ↓
Indexes
    ↓
Natural Language Query
    ↓
Intent
    ↓
Retrieval
    ↓
Reasoning
    ↓
Validation
    ↓
Evidence-backed Answer
```

## Deliverables

* Full pipeline
* Integration test suite
* Demo repository
* Demo script
* Metrics
* Failure demonstrations

## Acceptance Criteria

The following queries must work.

### E001: Locate Symbol

```text
Where is PaymentService implemented?
```

Expected:

```text
services/payment_service.py
correct location
evidence
```

### E002: Dependency Query

```text
What calls PaymentService?
```

Expected:

```text
CheckoutService
RefundService
```

### E003: Impact Analysis

```text
What breaks if PaymentService changes?
```

Expected:

```text
direct dependents
+
bounded transitive dependents
+
evidence
```

### E004: Semantic Explanation

```text
Explain payment validation.
```

Expected:

```text
relevant code
+
natural-language explanation
+
evidence
+
no unsupported claims
```

### E005: Agentic Trace

```text
Trace checkout from API request to payment persistence.
```

Expected:

```text
CheckoutController
→ CheckoutService
→ PaymentService
→ PaymentRepository
```

plus evidence for every transition.

These acceptance scenarios derive directly from the existing MAAT design. 

---

# 33. Quality Gates

The implementation is successful only when all of the following pass:

```text
[PASS] Repository discovery
[PASS] Snapshot creation
[PASS] Change detection
[PASS] Tree-sitter parsing
[PASS] Symbol extraction
[PASS] Relationship extraction
[PASS] Relationship resolution
[PASS] Relationship validation
[PASS] Semantic model
[PASS] Graph projection
[PASS] FTS5 projection
[PASS] Vector retrieval
[PASS] Version consistency
[PASS] Incremental indexing
[PASS] Fault isolation
[PASS] Intent classification
[PASS] Context ranking
[PASS] Deterministic reasoning
[PASS] Small-model reasoning
[PASS] Answer validation
[PASS] Model escalation
[PASS] MCP tools
[PASS] Agent tool calling
[PASS] Agent termination
[PASS] Evidence generation
[PASS] End-to-end queries
```

---

# 34. Critical Failure Conditions

The following must never silently succeed.

| Failure                      | Required behavior                      |
| ---------------------------- | -------------------------------------- |
| LLM unavailable              | Deterministic queries continue working |
| Small model fails validation | Escalate                               |
| Complex model fails          | Return insufficient evidence           |
| Broken file                  | Repository remains queryable           |
| Unknown symbol               | Do not hallucinate                     |
| Ambiguous relationship       | Mark ambiguous                         |
| Agent loop                   | Terminate                              |
| Tool failure                 | Structured failure                     |
| Mixed index versions         | Never expose as one state              |
| Missing evidence             | Do not claim certainty                 |
| Deleted symbol               | Remove stale active relationships      |
| Failed indexing              | Keep previous valid version active     |

The existing MAAT quality gates explicitly identify LLM unavailability, broken files, unknown symbols, agent termination, and mixed index versions as critical failure cases. 

---

# 35. Test Strategy

Testing follows:

```text
RED
 ↓
Minimal Implementation
 ↓
GREEN
 ↓
REFACTOR
 ↓
Next Behavior
```

The system should prioritize deterministic behavioral tests.

## Test Categories

```text
tests/
├── fixtures/
├── offline/
│   ├── snapshot/
│   ├── changes/
│   ├── parser/
│   ├── extraction/
│   ├── resolution/
│   ├── validation/
│   └── versioning/
│
├── indexes/
│   ├── graph/
│   ├── lexical/
│   └── vector/
│
├── online/
│   ├── intent/
│   ├── retrieval/
│   ├── context/
│   ├── reasoning/
│   └── validation/
│
├── agent/
│   ├── tools/
│   ├── mcp/
│   ├── loops/
│   └── termination/
│
└── e2e/
```

The original MAAT design similarly calls for parser, semantic-model, graph, lexical, vector, intent, context, agent, incremental, fault-tolerance, and E2E tests. 

---

# 36. Required Edge-Case Matrix

## Parser

```text
empty file
malformed syntax
partial AST
unsupported language
large file
generated file
```

## Resolution

```text
same symbol name
ambiguous receiver
overloaded method
alias import
missing import
dynamic dispatch
unknown symbol
```

## Incremental

```text
new file
modified file
deleted file
renamed file
unchanged file
changed dependency target
interrupted update
stale cache
```

## Semantic Model

```text
duplicate symbol
duplicate relationship
orphan relationship
invalid location
mixed versions
```

## Retrieval

```text
exact match
partial match
no result
ambiguous result
conflicting sources
stale result
```

## Reasoning

```text
unsupported claim
missing evidence
wrong answer type
incomplete answer
model timeout
model unavailable
```

## Agent

```text
tool failure
repeated tool
cycle
no progress
maximum iterations
token exhaustion
missing evidence
```

---

# 37. Implementation Order

The implementation must proceed in dependency order.

```text
1. Test fixtures + contracts
        ↓
2. Repository snapshot
        ↓
3. Change detector
        ↓
4. Tree-sitter parser
        ↓
5. Language extractors
        ↓
6. Semantic IR
        ↓
7. Symbol resolution
        ↓
8. Relationship validation
        ↓
9. Canonical semantic model
        ↓
10. Graph projection
        ↓
11. FTS5 projection
        ↓
12. Vector projection
        ↓
13. Atomic version publication
        ↓
14. Intent classifier
        ↓
15. Retrieval / context engine
        ↓
16. Deterministic reasoning
        ↓
17. Small-model reasoning
        ↓
18. Answer validator
        ↓
19. Model router
        ↓
20. MCP tools
        ↓
21. ReAct agent
        ↓
22. Incremental relationship invalidation
        ↓
23. Fault tolerance
        ↓
24. CLI / API
        ↓
25. End-to-end integration
```

Frontend and visualization are intentionally downstream of the core system.

The existing MAAT plan likewise places visualization and E2E validation after the semantic, retrieval, reasoning, agent, incremental, and fault-tolerance layers. 

---

# 38. Deliverable Matrix

| Stage | Deliverable              | Acceptance                              |
| ----- | ------------------------ | --------------------------------------- |
| 0     | Test fixture + contracts | Expected graph and schemas defined      |
| 1     | Repository snapshot      | Deterministic file manifest             |
| 2     | Change detector          | Only changed files processed            |
| 3     | Tree-sitter parser       | Valid/invalid/partial parsing handled   |
| 4     | Language extractors      | Symbols and relationships extracted     |
| 5     | Semantic IR              | Stable, validated entities              |
| 6     | Resolver                 | Correct/ambiguous/unresolved references |
| 7     | Relationship validator   | No invalid semantic edges               |
| 8     | Canonical model          | Versioned semantic state persisted      |
| 9     | Graph index              | Callers/callees/dependencies work       |
| 10    | FTS5 index               | Exact symbol search works               |
| 11    | Vector index             | Semantic retrieval works                |
| 12    | Version publisher        | All indexes atomically consistent       |
| 13    | Intent classifier        | Correct routing                         |
| 14    | Context engine           | Relevant, bounded evidence              |
| 15    | Deterministic engine     | Exact queries work without LLM          |
| 16    | Small model              | Semantic synthesis works                |
| 17    | Validator                | Unsupported claims detected             |
| 18    | Model router             | Failed simple reasoning escalates       |
| 19    | MCP                      | Repository tools available to agent     |
| 20    | ReAct agent              | Multi-step reasoning terminates         |
| 21    | Incremental resolver     | Affected relationships updated          |
| 22    | Fault tolerance          | Broken files isolated                   |
| 23    | CLI/API                  | Complete system accessible              |
| 24    | E2E                      | Full acceptance scenario passes         |

---

# 39. Final Demonstration

The final demonstration should run from a clean repository.

## Step 1: Index

```text
maat index ./demo_repo
```

Output:

```text
Files:          124
Symbols:        1,842
Relationships:  3,921
Model:          V1
```

---

## Step 2: Exact Query

```text
What calls PaymentService?
```

Pipeline:

```text
Query
 ↓
Intent = FIND_REFERENCES
 ↓
Graph
 ↓
Deterministic Reasoning
 ↓
Validation
 ↓
Answer + Evidence
```

Expected:

```text
CheckoutService
RefundService
```

---

## Step 3: Modify Repository

Modify:

```text
payment_service.py
```

Run:

```text
maat index ./demo_repo
```

Expected:

```text
Changed files: 1
Reparsed files: 1
Model: V2
```

No unrelated files should be unnecessarily reparsed.

---

## Step 4: Impact Query

```text
What breaks if PaymentService changes?
```

Pipeline:

```text
Intent
 ↓
CROSS_LAYER_TRACE
 ↓
Complex reasoning
 ↓
MCP
 ↓
find_callers
 ↓
trace_dependencies
 ↓
get_file
 ↓
Answer Validator
 ↓
Evidence-backed impact analysis
```

---

## Step 5: Fault Injection

Break one source file.

Reindex.

Expected:

```text
Files: 124
Healthy: 123
Degraded: 1
Model: V3
```

Repository remains queryable.

---

# 40. Definition of Done

MAAT is complete for the prototype when one complete workflow supports:

```text
Repository
    ↓
Snapshot
    ↓
Incremental Change Detection
    ↓
Tree-sitter Parse
    ↓
Semantic IR
    ↓
Relationship Resolution
    ↓
Canonical Semantic Model
    ↓
Graph / FTS5 / Vector
    ↓
Versioned Publication
    ↓
Natural Language Query
    ↓
Intent Classification
    ↓
Retrieval Strategy
    ↓
Context Construction
    ↓
Deterministic / Small Model / Complex Model
    ↓
MCP / ReAct when required
    ↓
Answer Validation
    ↓
Evidence-backed Answer
```

The test suite must prove:

```text
Correctness
+
Incremental Updates
+
Fault Isolation
+
Retrieval Correctness
+
Context Control
+
Model Escalation
+
Answer Grounding
+
Evidence Provenance
+
Agent Termination
+
Version Consistency
```

The original MAAT definition of done requires the same fundamental progression from repository parsing through semantic modeling, retrieval, intent, reasoning, evidence, and visualization, with correctness, resilience, incremental updates, context control, agent termination, provenance, and version consistency as the final quality properties. 

---

# 41. Final Architectural Contract

The entire implementation should preserve these boundaries:

```text
┌────────────────────────────────────────────┐
│              REPOSITORY TRUTH              │
│                                            │
│ Tree-sitter                                │
│ Extractors                                 │
│ Resolver                                   │
│ Semantic Model                             │
│ Evidence                                   │
│ Version                                    │
└──────────────────────┬─────────────────────┘
                       │
                       │ retrieval
                       ↓
┌────────────────────────────────────────────┐
│               REASONING                    │
│                                            │
│ Intent                                     │
│ Context                                    │
│ Deterministic                             │
│ Small Model                                │
│ Complex Model                              │
│ Agent                                     │
└──────────────────────┬─────────────────────┘
                       │
                       │ claims
                       ↓
┌────────────────────────────────────────────┐
│               VALIDATION                   │
│                                            │
│ Grounding                                  │
│ Evidence                                   │
│ Completeness                               │
│ Citation correctness                       │
│ Version consistency                        │
└──────────────────────┬─────────────────────┘
                       │
                       ↓
              Evidence-backed Answer
```

## The three rules that must never be violated

### Rule 1

> **The LLM must not become the source of repository truth.**

### Rule 2

> **The agent must not replace deterministic repository capabilities.**

### Rule 3

> **No generated answer is trusted merely because a model generated it.**

Everything else in MAAT exists to enforce those three rules.
