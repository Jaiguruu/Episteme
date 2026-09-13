"""Shared test support: fixture paths, temp repositories, small builders."""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
DEMO_REPO = FIXTURES / "demo_repo"
EDGECASE_REPO = FIXTURES / "edgecase_repo"


class TempRepository:
    """A disposable copy of a fixture repository.

    Change-detection tests have to mutate files and reindex, and they must not
    touch the committed fixture or leave an index directory behind. Copying into
    a temporary directory keeps the fixture pristine and makes each test
    independent of the others.
    """

    def __init__(self, source: Path = DEMO_REPO) -> None:
        self._source = source
        self._temp = Path(tempfile.mkdtemp(prefix="maat-test-"))

    @property
    def root(self) -> Path:
        return self._temp / "repo"

    @property
    def index_dir(self) -> Path:
        return self._temp / "index"

    def __enter__(self) -> "TempRepository":
        shutil.copytree(self._source, self.root)
        return self

    def __exit__(self, *exc_info: object) -> None:
        shutil.rmtree(self._temp, ignore_errors=True)

    def write(self, relative: str, content: str | bytes) -> Path:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
        return target

    def append(self, relative: str, content: str) -> Path:
        target = self.root / relative
        with open(target, "a", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        return target

    def delete(self, relative: str) -> None:
        (self.root / relative).unlink()

    def rename(self, old: str, new: str) -> None:
        target = self.root / new
        target.parent.mkdir(parents=True, exist_ok=True)
        (self.root / old).rename(target)


def empty_temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="maat-index-"))


@contextmanager
def temp_repo(files: dict[str, str | bytes]) -> Iterator[Path]:
    """Build a throwaway repository from an explicit file map.

    Bytes values are written verbatim, which matters for the cases that are
    about bytes rather than text: NUL bytes, a UTF-8 BOM, CRLF line endings.
    """
    root = Path(tempfile.mkdtemp(prefix="maat-gen-"))
    try:
        for relative, content in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8", newline="\n")
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
