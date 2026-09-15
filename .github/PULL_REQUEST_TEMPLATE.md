<!--
Thanks for the pull request. The sections below are not bureaucracy: this
codebase has tight design constraints, and the questions are the ones a
reviewer will ask anyway.
-->

## What was wrong before

<!-- The current behaviour, described precisely. If you could not describe what
the code does today, this is the place to say so. -->

## What this changes

<!-- The proposed behaviour, and why this shape rather than another. -->

## How it was verified

<!--
Be specific, and label anything you could not check. "I ran the suite" is
weaker than "test_x fails before the change and passes after". If you measured
something, give the number. If you assumed something, say so here rather than
leaving it implicit.
-->

## Checklist

- [ ] `python tests/run_all.py` passes — **137 tests**
- [ ] New or changed behaviour has a test that fails without this change
- [ ] No unrelated code was modified in this PR
- [ ] Any number quoted in the docs was **re-measured**, not copied
- [ ] `CHANGELOG.md` updated if the change is user-visible

<!-- Only if you touched a .scm query file: -->

- [ ] `python tools/verify_queries.py` exits 0
- [ ] `python tools/verify_bindings.py` run if binding patterns were added

## Design constraints

<!-- Delete any that do not apply, but do not delete the section silently. -->

- [ ] No language-specific shape crosses the Tier 2 → Tier 3 boundary
- [ ] The semantic model is still the source of truth; no index became authoritative
- [ ] No ambiguous relationship was turned into a confident one without evidence
- [ ] Failure is still data — new entities expose `problems()` and do not raise
- [ ] Determinism is preserved (traversal, hashing, serialisation, ID derivation)
- [ ] `model_version` is not an input to any entity ID

## If this diverges from SPEC.md

<!--
SPEC.md is normative for intent; the code is normative for behaviour. If they
disagree, say so here and explain the conflict rather than resolving it
silently.
-->

## Related issues

<!-- Closes #... -->
