# Contributing

Thanks for taking a look. This document gets you from a fresh clone to a merged
change.

---

## 1. Setup

```bash
git clone https://github.com/Jaiguruu/Episteme.git
cd Episteme

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

That installs the package in editable mode along with `tree-sitter` and
`tree-sitter-language-pack` (about 400 pre-compiled grammars).

**Confirm the interpreter is the right one.** `tree-sitter` is a hard runtime
dependency — `maat.offline` imports it at module scope, so nothing runs without
it. If you have several interpreters on `PATH`, a bare `python` may not be the one
you installed into:

```bash
python -c "import tree_sitter; print(tree_sitter.__file__)"
```

**Run the suite:**

```bash
python tests/run_all.py              # 327 tests, ~15 s
python tests/run_all.py -v           # verbose
python tests/run_all.py offline      # only tests whose id contains "offline"
```

`run_all.py` uses stdlib `unittest`. **There is no pytest**, deliberately — the
suite runs with no third-party test dependency. Positional arguments are
substring filters on the test id, not file paths. The runner exits `1` on any
failure or error.

**Try it end to end:**

```bash
python tools/demo_offline.py tests/fixtures/demo_repo
python tools/demo_offline.py tests/fixtures/edgecase_repo
```

---

## 2. Before you change anything

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first — specifically
[§9, the invariants](ARCHITECTURE.md#9-invariants-a-change-must-not-break). Most
rejected changes are rejected because they break one of those rules, not because
they are wrong in isolation.

Then:

1. **Inspect the existing code before implementing.** Do not infer repository
   behaviour from the docs alone; the docs describe intent, the code is the fact.
2. **State the current behaviour first.** If you cannot describe what the code
   does today, you are not ready to change it.
3. **Prefer a deterministic mechanism over a heuristic.** If a rule can be
   expressed structurally, express it structurally. A guess that is right 95% of
   the time is worse than an honest `UNRESOLVED`.
4. **If the spec and the implementation conflict, stop and say so.** Do not
   silently pick one. `SPEC.md` is normative for intent; the code is normative for
   behaviour; a divergence is a defect to report.

---

## 3. Working on a change

Work in **one small vertical slice at a time**. A slice is a change that can be
tested on its own — not "add the resolver", but "resolve import targets within a
single file".

```text
PLAN  →  IMPLEMENT  →  TEST  →  REVIEW  →  COMMIT
```

For anything non-trivial, open an issue or a draft PR describing the plan before
writing code. The design constraints here are tight enough that a plan review is
cheaper than a rewrite.

**Do not modify unrelated code in the same change.** If you find an unrelated
defect, note it in the PR description rather than fixing it in the same commit.

### Diagnose before you patch

If a test fails, find the root cause before editing anything. A change that makes
a test pass without explaining why it was failing is not a fix. Several of the
bugs in `docs/decisions.md` were only understood after the failing behaviour was
traced back to a wrong assumption about tree-sitter's API shape.

---

## 4. Code conventions

**Style.** `from __future__ import annotations` as the first import in every
module. Type hints throughout. Modern unions (`str | None`).

**Data.** `dataclasses`, not pydantic. Mutable for entities the pipeline
re-stamps; `frozen=True` for value objects (`SourceSpan`, `LanguageSpec`,
`SnapshotOptions`).

**Seams.** Replaceable components are `typing.Protocol`, not ABCs —
`ParserBackend` and `Extractor`. Both are structural.

**Docstrings.** Plain prose, module-first, explaining **why** rather than what.
Cite the spec section each rule serves. There are no Google/NumPy `Args:` blocks;
follow the existing voice.

**Enums.** Persisted vocabulary lives in `maat/core/enums.py` and uses the private
`_StrEnum`, whose `__str__` returns the bare value, so a status serialises as
`"OK"` and not `"ParseStatus.OK"`.

**Validation never raises.** New entities expose `problems() -> list[str]`. They
return human-readable strings; they do not throw on invalid input. Only
programmer/setup errors raise.

**Determinism.** If your change touches traversal, hashing, serialisation or ID
derivation, it needs a test that would catch a regression. Sort before hashing;
never let a `set` reach serialised state.

---

## 5. Adding a language

This is the most common contribution and it needs **no Python at all** if the
grammar is already registered:

> Drop `maat/offline/queries/<grammar-key>.scm` into the queries directory.

`extractable_languages()` derives extractability from the filesystem, so the
language becomes extractable the moment the file lands and stops being
extractable when it is removed. Full details — the capture vocabulary, the
two-captures-per-pattern rule, per-language quirks, and how to verify — are in
[`docs/adding-a-language.md`](docs/adding-a-language.md).

```bash
python tools/verify_queries.py         # compiles all 18 queries, exits 1 on failure
python tools/dump_trees.py <language>  # print a real parse tree to write patterns against
python tools/count_tests.py            # derive the suite figures the docs quote
```

`verify_queries.py` matters more than it looks: a malformed query does **not**
crash the pipeline. It silently degrades extraction, so a broken query ships as
missing symbols unless this gate catches it. CI runs it.

`count_tests.py` is for you, not for CI. The test, class and file counts appear in
this file and in two docs, and hand-copied figures drifted; run the tool and paste
its output instead of editing a number by hand.

---

## 6. Tests

**Layout.** `tests/offline/test_<module>.py`, one `unittest.TestCase` per
concern. A new `tests/<package>/` directory needs its own `__init__.py` to be
importable.

**Fixtures.** Use `tests/support.py`:

* `TempRepository` — a disposable copy of a fixture. Change-detection tests mutate
  files, and they must never touch the committed fixture.
* `temp_repo(files)` — build a synthetic repository from an explicit file map.
  Bytes values are written verbatim, which matters for NUL, BOM and CRLF cases.

**Never write into a committed fixture.** Pass `persist=False` to
`index_repository` when you only want the result:

```python
result = index_repository("path/to/repo", persist=False)
```

That is the right default in tests and experiments, because it cannot dirty a
fixture. Note that `tools/demo_offline.py --touch <file>` **does** mutate a
fixture file and does not revert it — copy to a temp directory first.

**Every important behaviour needs a behavioural test.** Test the observable
contract, not the implementation. A test that asserts an internal call sequence
will block a legitimate refactor; a test that asserts the model's contents will
not.

See [`docs/testing.md`](docs/testing.md) for the suite map and the baseline.

---

## 7. Commits and pull requests

**Commit messages** explain *why*. The body should say what was wrong before, what
the change does, and what was traded away. If you had to measure something to make
a decision, put the measurement in the message.

```text
fix: carry parse status forward on incremental reuse

Reused files lost their FileRecord outcome, so a degraded file became OK on
the second run and the degraded count went 1 -> 0.

...
```

**Before opening a PR:**

- [ ] `python tests/run_all.py` passes (327 tests)
- [ ] `python tools/verify_queries.py` exits 0 (if you touched a `.scm`)
- [ ] New behaviour has a test that fails without your change
- [ ] No unrelated code was modified
- [ ] Any measured numbers quoted in docs were re-measured, not copied
- [ ] `CHANGELOG.md` updated if the change is user-visible

**In the PR description,** state the current behaviour, the proposed behaviour,
and what you verified. If you made an assumption you could not check, say so
explicitly rather than leaving it implicit.

---

## 8. Reporting bugs and security issues

Open an issue with the repository layout that reproduces it, the command you ran,
and the output. A fixture that reproduces the bug is worth more than a
description of it.

For security issues, **do not open a public issue** — see
[`SECURITY.md`](SECURITY.md).

Participation is covered by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
