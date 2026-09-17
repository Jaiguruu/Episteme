# Security Policy

## Supported versions

This project is at `0.1.0` and is under active development. Security fixes are
applied to the `main` branch; there are no maintained release branches yet.

| Version | Supported |
|---|---|
| `main` (unreleased) | yes |
| `0.1.0` | yes |

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on the repository's **Security** tab, or contact the maintainer via
[https://github.com/Jaiguruu](https://github.com/Jaiguruu).

Please include:

* what you did, and the input that triggered it
* what happened, and what you expected
* the version or commit you tested
* whether the issue is reachable from untrusted input

You can expect an acknowledgement within a few days. Please allow time for a fix
to be prepared before disclosing publicly.

## Threat model

Worth stating explicitly, because it shapes what counts as a vulnerability here.

**Episteme parses untrusted input.** Its whole job is to read a directory of
source files it did not write. It is designed to be pointed at arbitrary
repositories.

**It does not execute the code it reads.** No file is imported, evaluated,
compiled or run. Nothing shells out. There is no network access, no database, and
no model call anywhere in the offline path.

**What it does do** is hand file contents to tree-sitter grammars, walk directory
trees, hash bytes, and write JSON into `<repo>/.maat/`.

That leaves three realistic risk classes:

1. **Resource exhaustion.** A pathologically large file, deeply nested syntax, or
   a directory tree with an extreme number of entries could consume excessive
   memory or CPU. Depth is a known failure mode: the traversal is iterative
   specifically because a deeply nested file can exceed Python's recursion limit.
2. **Parser crashes.** A malformed or adversarial file causing a native grammar to
   crash rather than return an error tree. The Python-side contract is that bad
   input is isolated as data — a crash that escapes that boundary is a bug worth
   reporting.
3. **Path handling.** The scanner writes into the repository it is pointed at, and
   applies ignore rules to paths it did not author. Escaping the intended
   directory, or writing outside `<repo>/.maat/`, would be a security issue.

**Not in scope:** the accuracy or completeness of extracted symbols. A missed
symbol or an unresolved edge is a correctness bug, not a vulnerability — the
design deliberately prefers an honest `UNRESOLVED` over a confident guess.

## Robustness of the model loader

`load_previous_ir` treats a corrupt previous model as absent and triggers a full
rebuild. "Corrupt" covers both **syntactically** invalid JSON and payloads that parse
but do not match the persisted shape: a missing field (`KeyError`), an unknown enum
value (`ValueError`) and a wrong type (`TypeError` / `AttributeError`) are all caught
and reported as absence, so a drifted model can never abort an index run.

An empty object is structurally valid, so it does load — and is harmless. It yields no
reusable entities, so every unchanged file falls through to the parse branch and is
rebuilt; the outcome is identical to treating the model as absent. Both behaviours are
asserted by `PreviousModelLoaderTests` in `tests/offline/test_pipeline.py`.

The realistic trigger for the structural case is **schema drift across versions**, not a
truncated write — publication is atomic (`mkstemp` → `fsync` → `os.replace`), so a
half-written `ir.json` cannot be observed.

This was a documented defect until it was fixed; the history and the corrected analysis
are in [`docs/decisions.md`](docs/decisions.md). If you can reach any remaining failure
with untrusted input in a way that is worse than a failed index run, please report it.
