# MEMORY — Episteme / MAAT (project conventions)

## Pair-programming protocol (user-set, 2026-09-13)

The user owns this project. The assistant is an **implementation partner**, not
an autonomous owner. Interaction loop:

    PLAN → user reviews → IMPLEMENT → TEST → REVIEW → COMMIT

Never jump straight to implementation. Before touching code, state:
current behaviour · relevant files/modules · proposed design · assumptions ·
files to change · tests required. Work in **one small vertical slice at a time**.
Do not modify unrelated code.

## Engineering rules the user enforces

1. Inspect existing code before implementing any feature.
2. Do not invent repository behaviour — verify it from the code.
3. Prefer deterministic mechanisms over LLM reasoning where a deterministic
   mechanism can solve the problem.
4. Preserve the architecture: Canonical Semantic Model → Graph / FTS5 / Vector
   projections. **Never let an index become the source of truth.**
5. Never convert an ambiguous/unresolved relationship into a confident
   relationship without evidence.
6. Every important behaviour needs a behavioural test. Run relevant tests after
   implementing. On failure, diagnose the root cause before changing code.
7. Keep public interfaces and domain contracts explicit.
8. If the specification and the implementation conflict, **stop and explain the
   conflict** — never silently choose one.

## Codebase facts worth not re-deriving

- Two packages: `maat/core/` (language-neutral contracts) and `maat/offline/`
  (the pipeline). `maat/semantic/` is planned for M2 but does not exist yet.
- Three tiers, one rule: **no language-specific shape may cross Tier 2 → Tier 3.**
  Tier 3 sees only `SymbolFact` / `ImportFact` / `CallFact` / `InheritFact` /
  `BindingFact`.
- `maat/offline/queries/<lang>.scm` presence **is** extractability — derived from
  the filesystem, never hard-coded. Drop in a `.scm` to upgrade a language.
- Tests: stdlib `unittest`, no pytest. Run with `python tests/run_all.py`.
- Declared-but-unused contract members (forward-looking schema, do NOT delete
  without asking): `ChangeKind`, `RECOVERY_STATEMENT`,
  `SymbolType.PARAMETER` / `VARIABLE` / `IMPORT`,
  `RelationshipType.REFERENCES` / `IMPLEMENTS`.
- `TODO.md` is **stale** relative to the implementation (it describes a
  hand-written lexer/parser later replaced by tree-sitter). Treat the code and
  `docs/*.md` as the source of truth; flag the divergence rather than "fixing"
  the code to match the stale plan.
- M1 emits **every** reference as `UNRESOLVED` by design. Only `CONTAINS` is
  `RESOLVED_EXACT`. Resolution is M2.

## Communication preferences

- The user asks for **first-principles** explanations (explicitly requested an
  "explain like I am 10" walkthrough of the architecture). When explaining a
  design, start from *why the thing exists* and build up from simple, checkable
  ideas. Analogies are welcome; jargon is not. Assume engineering competence but
  not prior familiarity with this codebase.
- Explanations should still be technically accurate — simplify the language, not
  the mechanism. Do not drop a design rule just because it is hard to phrase
  simply.
