# Documentation

Reference material for working on Episteme. Start at the repository
[`README.md`](../README.md) if you have not set the project up yet.

---

## Reading order

If you are new to the codebase:

1. [`../README.md`](../README.md) — what the project is, and how to run it
2. [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — how it works and **why**; read this
   before changing anything structural
3. [`glossary.md`](glossary.md) — the vocabulary, kept open in a second tab
4. [`architecture-deep-dive.html`](architecture-deep-dive.html) — per-file activity
   diagrams, when you need to see the mechanics of one module

Then, depending on what you are doing:

| I want to… | Read |
|---|---|
| contribute a change | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| know what is done and what is next | [`../ROADMAP.md`](../ROADMAP.md) |
| add or fix a language | [`adding-a-language.md`](adding-a-language.md) |
| write or run tests | [`testing.md`](testing.md) |
| know why something is built this way | [`decisions.md`](decisions.md) |
| know what the tests prove | [`verification.md`](verification.md) |
| read the requirements | [`../SPEC.md`](../SPEC.md) |

---

## The documents

### [`adding-a-language.md`](adding-a-language.md)

The most common contribution, and for an already-registered grammar it needs no
Python at all. Covers the workflow, the full capture vocabulary, the
two-captures-per-pattern rule, per-language quirks for 15 languages, an honest list
of known partial coverage, and the two verification tools.

**Highest-value open gap:** `@bind.*` patterns exist for Python only. The other 17
extractable languages need them.

### [`architecture-deep-dive.html`](architecture-deep-dive.html)

A self-contained HTML reference — 17 sections, each with an activity/flow diagram
derived from the source, plus a "small logics" table for the parts that are easy to
misread. One section per module, then an end-to-end trace of a single call edge
through all five stages.

Open it in a browser; it has no external dependencies and works offline.

### [`testing.md`](testing.md)

Suite layout, the two fixture helpers, the two rules that prevent most mistakes
(never write into a committed fixture; never assert on an absolute hash), how to
write a test, and the baseline numbers.

### [`glossary.md`](glossary.md)

Every piece of project-specific vocabulary: the tiers, the fact types, the ID
prefixes, the status vocabularies, the tree-sitter terms, and the notation used in
the spec (`§n`, `ACn`, `E00n`, `Dn`, `Mn`).

### [`decisions.md`](decisions.md)

The design decision log, D1–D32, each with its rationale **and the trade-off
accepted**. Also the record of the twelve bugs found during M1 — each one changed
the design or the tests — and the list of open defects.

Read this when you are about to change something structural and want to know
whether the current shape is deliberate.

### [`verification.md`](verification.md)

How the acceptance criteria are discharged. Covers the four layers the spec states
criteria at (83 numbered + 43 unnumbered + 5 scenarios + 51 summary statements),
the coverage table per stage, the cross-cutting properties, the known gaps, and the
eight criteria that cannot be falsified as written.

---

## Documents that are deliberately absent

There is no `CHANGELOG`-per-module, no per-file API reference, and no separate
architecture document per milestone. Module behaviour is documented in module
docstrings — the source is the reference — and milestone plans are working
documents rather than durable documentation.

If you need the requirements rather than the design, read
[`../SPEC.md`](../SPEC.md). It is normative for **intent**; the code is normative
for **behaviour**. Where they disagree, that is a defect worth reporting, not
something to resolve silently.
