"""Source location primitives.

Conventions (fixed here once, because getting them wrong is the classic
off-by-one bug in every code-intelligence tool):

* ``line`` is 1-based, matching every editor and every error message a user
  will ever see.
* ``column`` is 0-based, matching tree-sitter, CPython's tokenizer and LSP.
* ``end`` is exclusive, so ``end - start`` is the length of the span and
  adjacent spans never overlap.

Validation never raises. Callers aggregate ``problems()`` into a validation
report (section 14), because a malformed span in a half-parsed file is data to
be reported, not an exception to be thrown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, order=True)
class SourceSpan:
    """A half-open region of a single file."""

    start_line: int
    start_col: int
    end_line: int
    end_col: int

    # -- construction -----------------------------------------------------

    @classmethod
    def from_tree_sitter(cls, node: Any) -> "SourceSpan":
        """Build a span from a tree-sitter node.

        tree-sitter reports ``row`` 0-based and ``column`` in **bytes**, not
        characters. We keep the byte column as-is: it is the value tree-sitter
        uses for slicing, and converting it to a character offset would make
        the span disagree with the parser. The line is shifted to 1-based.
        """
        return cls(
            start_line=node.start_point[0] + 1,
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
        )

    @classmethod
    def point(cls, line: int, col: int) -> "SourceSpan":
        """A zero-width span, used for relationships anchored to a token."""
        return cls(line, col, line, col)

    @classmethod
    def whole_file(cls, line_count: int) -> "SourceSpan":
        return cls(1, 0, max(1, line_count), 0)

    # -- queries ----------------------------------------------------------

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    def contains_line(self, line: int) -> bool:
        return self.start_line <= line <= self.end_line

    def is_zero_width(self) -> bool:
        return self.start_line == self.end_line and self.start_col == self.end_col

    # -- validation -------------------------------------------------------

    def problems(self) -> list[str]:
        issues: list[str] = []
        if self.start_line < 1:
            issues.append(f"start_line must be >= 1, got {self.start_line}")
        if self.end_line < 1:
            issues.append(f"end_line must be >= 1, got {self.end_line}")
        if self.start_col < 0:
            issues.append(f"start_col must be >= 0, got {self.start_col}")
        if self.end_col < 0:
            issues.append(f"end_col must be >= 0, got {self.end_col}")
        if (self.end_line, self.end_col) < (self.start_line, self.start_col):
            issues.append(
                f"span end {self.end_line}:{self.end_col} precedes "
                f"start {self.start_line}:{self.start_col}"
            )
        return issues

    def is_valid(self) -> bool:
        return not self.problems()

    # -- serialisation ----------------------------------------------------

    def to_dict(self) -> dict[str, int]:
        return {
            "start_line": self.start_line,
            "start_col": self.start_col,
            "end_line": self.end_line,
            "end_col": self.end_col,
        }

    def __str__(self) -> str:
        return f"{self.start_line}:{self.start_col}-{self.end_line}:{self.end_col}"
