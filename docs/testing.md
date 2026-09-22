# Testing

How the test suite is organised and how to add to it.

---

## 1. Framework

**stdlib `unittest`. There is no pytest**, deliberately — the suite runs with no
third-party test dependency.

```bash
python tests/run_all.py              # 440 tests, ~15 s
python tests/run_all.py -v           # verbose
python tests/run_all.py offline      # only tests whose id contains "offline"
python tests/run_all.py ir pipeline  # several filters at once
```

**Positional arguments are substring filters on the test id**, not file paths.

`run_all.py` inserts the project root on `sys.path`, then discovers with
`start_dir=tests`, `pattern="test_*.py"`, and `top_level_dir=PROJECT_ROOT`. That
last argument is what makes the relative imports into `tests/support.py` work. A
new `tests/<package>/` directory therefore needs its own `__init__.py` to be
importable.

The runner exits **1** on any failure or error, and **0** otherwise — which is
what makes it usable directly as a CI gate.

---

## 2. Layout

```text
tests/
  run_all.py          the runner
  support.py          shared fixtures and helpers
  test_docs.py            3 tests   documentation hygiene guard (D33)
  core/
    test_enums.py         9 tests   the closed vocabularies
    test_locations.py    18 tests   SourceSpan conventions and validation
    test_contracts.py    63 tests   entity contracts, referential integrity
    test_serialization.py 24 tests  canonical JSON, atomic writes, hash combining
    test_validation.py   32 tests   §14 Stage 7 — the validator, the report and the severity policy
  offline/
    test_snapshot.py     16 tests   §8  Stage 1
    test_changes.py      19 tests   §9  Stage 2
    test_parser.py       20 tests   §10 Stage 3
    test_extractor.py    16 tests   §11 Stage 4
    test_ir.py           47 tests   §12 Stage 5
    test_pipeline.py     71 tests   end-to-end, incremental, publication, §30, model loader, resolution, validation
  semantic/
    test_ladder.py       21 tests   §13 Stage 6 — the resolution ladder
    test_resolver.py     37 tests   §13 Stage 6 — resolution end to end
    test_store.py        44 tests   §15 Stage 8 — the canonical model store
  fixtures/
    demo_repo/          7 files, including one deliberately broken
    edgecase_repo/      142 scanned files, 18 grammars, deliberate edge cases
```

`tests/core/` needs its own `__init__.py`, per the note above; `tests/test_docs.py`
sits at the top level and needs none.

One `unittest.TestCase` subclass per concern; module-level helper functions and
constants above the classes.

> **Spec §35 describes a per-stage tree** (`tests/offline/snapshot/`, …). The
> actual layout is flat. Functionally equivalent, and the divergence is recorded
> in [`verification.md`](verification.md) rather than left silent.

---

## 3. Fixtures

Both live in `tests/support.py`.

### `TempRepository` — a disposable copy of a real fixture

```python
from ..support import TempRepository

with TempRepository() as repo:
    repo.write("services/new.py", "def f(): pass\n")
    repo.delete("services/old.py")
    repo.rename("a.py", "b.py")

    first = pipeline.index(repo.root, index_dir=repo.index_dir)
    second = pipeline.index(repo.root, index_dir=repo.index_dir)
```

It copies the fixture into a temporary directory and removes it on exit. Change
detection has to mutate files and reindex, and it must never touch the committed
fixture or leave an index directory behind.

`TempRepository` defaults to `demo_repo`; pass `EDGECASE_REPO` for the polyglot
one.

### `temp_repo` — a synthetic repository from an explicit file map

```python
from ..support import temp_repo

with temp_repo({"a.py": "x = 1\n", "b.bin": b"\x00\x01"}) as root:
    ...
```

**Bytes values are written verbatim**, which is what makes the NUL, BOM and CRLF
cases testable. String values are written UTF-8 with `newline="\n"`.

### `empty_temp_dir()`

An empty directory outside the repository, for use as an explicit `index_dir`.

---

## 4. Two rules that prevent most mistakes

### Never write into a committed fixture

```python
result = index_repository("path/to/repo", persist=False)
```

`persist=False` indexes without writing anything. It is the right default in tests
and experiments, because it cannot dirty a fixture.

When a test genuinely needs persistence, pass an explicit `index_dir` pointing
outside the repository:

```python
pipeline.index(repo.root, index_dir=repo.index_dir)     # TempRepository: already a temp dir
pipeline.index(DEMO_REPO, index_dir=empty_temp_dir())   # explicit temp dir
```

> **`tools/demo_offline.py --touch <file>` mutates a committed fixture and does not
> revert it.** Copy to a temp directory first. This is a known defect.

### Do not assert on absolute hashes or versions

Content hashes and `model_version` values change whenever a fixture file changes,
and they differ across environments. Every `mv_*` literal in the suite is a
synthetic value (`"mv_1"`, `"mv_2"`, `"mv_a"`) used to test *relations*.

The mechanism is worth stating, because it explains why this is not a matter of
taste. A `model_version` is a digest of the **raw bytes** of every scanned file
(`core.ids.model_version_id` over `core.serialization.combine_hashes`), and content
hashing is deliberately byte-level (D9). Line endings are bytes. So a checkout with
`core.autocrlf=true` materialises the `.py` fixtures as CRLF and derives a different
version than an LF checkout does — from identical source, yielding identical symbols
and relationships. Nothing is wrong; the value simply does not travel between machines.

Assert the relation, not the number:

```python
# good — every entity agrees on one version
version = result.version.id
for entity in result.ir.symbols:
    self.assertEqual(entity.model_version, version)

# fragile — the placeholder below is deliberately not a digest.
# Any concrete value breaks the moment a fixture byte changes, or a
# different checkout materialises the fixtures with different line endings.
self.assertEqual(result.version.id, "mv_<digest>")
```

---

## 5. Writing a test

1. **Put it with its stage.** A snapshot behaviour goes in `test_snapshot.py`.
2. **Name it after the behaviour, not the method.** `test_rename_is_reparsed`
   tells you what broke; `test_detect_renames_2` does not.
3. **Test the observable contract.** Assert on the model's contents, not on an
   internal call sequence — a test that pins the implementation blocks a
   legitimate refactor.
4. **Make it fail first.** If it passes before your change, it is not testing your
   change.
5. **Cover the degraded path.** The interesting behaviour here is what happens to
   bad input. `PARTIAL`, `FAILED`, `EMPTY` and `UNSUPPORTED` are all reachable and
   all worth a test.

A worked example:

```python
def test_reused_file_keeps_its_degraded_status(self) -> None:
    """A degraded file must not become OK merely because it was reused."""
    with TempRepository() as repo:
        pipeline = OfflinePipeline()

        first = pipeline.index(repo.root, index_dir=repo.index_dir)
        second = pipeline.index(repo.root, index_dir=repo.index_dir)

        degraded_first = [f for f in first.ir.files if f.parse_status.is_degraded]
        degraded_second = [f for f in second.ir.files if f.parse_status.is_degraded]
        self.assertEqual(len(degraded_first), len(degraded_second))
```

---

## 6. The baseline

```text
440 tests, 89 classes, 15 files
python tests/run_all.py  ->  PASS, ~15 s
```

The three figures are derived, not hand-maintained — `python tools/count_tests.py`
prints exactly this line. It walks the AST rather than importing, because importing
would report a different number from the one `unittest` discovers if a module failed
to load. Re-derive before editing any count in this file.

| Fixture | Scanned | Symbols | Relationships | Bindings |
|---|---:|---:|---:|---:|
| `demo_repo` | 7 | 26 | 42 | 15 |
| `edgecase_repo` | 142 | 5,044 | 5,398 | 1 |

`edgecase_repo` holds 155 files in total: 142 scanned, 8 excluded as files (1 binary,
3 generated, 4 ignored) and 5 inside 4 pruned directories. Model versions are
deliberately not listed — see §4 for why they do not travel between checkouts.

`edgecase_repo` statuses: `OK 128`, `PARTIAL 3`, `FAILED 6`, `EMPTY 3`,
`UNSUPPORTED 2`. The 9 degraded files are isolated and named.

**Per-repository durations are not comparable** across machines or across cold and
warm grammar caches — the edge-case figure includes first-run grammar loading for
18 languages. Treat any single-run duration as indicative only, and do not encode
one in a test.

---

## 7. What is not covered

Full detail in [`verification.md`](verification.md). In short:

* **`REFERENCES` and `IMPLEMENTS`** are neither produced nor tested.
* **Stage 8 and beyond** have no tests, because they do not exist.

`maat/core/` was previously listed here as having no test module; it now has one
(§2), and Stage 7's six acceptance criteria are covered by
`tests/core/test_validation.py`.

The model loader was previously listed here as an untested defect. It is now covered by
`PreviousModelLoaderTests` in `tests/offline/test_pipeline.py`, which asserts that a
malformed previous model rebuilds rather than aborting the run.
