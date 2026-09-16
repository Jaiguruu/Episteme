"""Stage 3 — parsing, backed by tree-sitter grammars (spec section 10).

The grammar is provided by ``tree_sitter_language_pack``; this module is the
adapter that turns a grammar plus a byte string into a :class:`ParseOutcome`
carrying a parse status, diagnostics and structural metrics.

The whole module is built around one rule from section 30: **a malformed file
must never raise.** tree-sitter is error-tolerant by design -- it always returns
a tree, inserting ``ERROR`` and ``MISSING`` nodes where it could not match --
so the work here is not recovery, it is *classification*. We decide whether the
tree we got is good enough to be ``OK``, usable-but-degraded (``PARTIAL``), or
worthless (``FAILED``), and we attach the error locations as diagnostics.

Status decision, in order:

    language unknown / grammar unavailable   -> UNSUPPORTED
    file has no tokens at all                -> EMPTY
    no error and no missing nodes            -> OK
    root itself is an ERROR node, or no
        top-level statement parsed cleanly   -> FAILED
    otherwise                                -> PARTIAL

The FAILED/PARTIAL line is the interesting one. A file whose *entire* content
failed to match (tree-sitter hands back a single ``ERROR`` node covering
everything) gives us nothing to extract, so it is FAILED. A file with one bad
function among ten good ones gives us nine usable symbols, so it is PARTIAL and
the symbols are kept (section 10 AC6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

from ..core.contracts import Diagnostic
from ..core.enums import (
    RECOVERY_BLOCK,
    RECOVERY_FILE,
    RECOVERY_NONE,
    DiagnosticSeverity,
    ParseStatus,
)
from ..core.locations import SourceSpan

#: Stop collecting diagnostics after this many, to bound output on a
#: catastrophically broken file. A summary diagnostic is appended if truncated.
MAX_DIAGNOSTICS = 100

#: Node types that mean "tree-sitter could not match here".
ERROR_NODE_TYPES = frozenset({"ERROR"})


class GrammarUnavailableError(RuntimeError):
    """Raised internally when a grammar cannot be loaded.

    Caught by the parser and converted into ``ParseStatus.UNSUPPORTED``. It never
    escapes to the caller, because an unavailable grammar is an expected
    condition (section 10 AC4), not a failure of the pipeline.
    """


@dataclass
class ParseOutcome:
    """Everything the extraction stage needs from one file."""

    status: ParseStatus
    language: str | None
    source: bytes
    tree: Any | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    node_count: int = 0
    max_depth: int = 0
    error_node_count: int = 0
    missing_node_count: int = 0

    @property
    def has_tree(self) -> bool:
        return self.tree is not None

    def text_of(self, node: Any) -> str:
        """Decode a node's source text.

        ``errors="replace"`` rather than strict decoding: a file with mixed
        encodings must still yield symbols for its decodable regions.
        """
        return self.source[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )


class ParserBackend(Protocol):
    """The seam that keeps the parser replaceable.

    Any object with this shape can drive the pipeline. ``TreeSitterParser`` is
    the implementation shipped here; a different backend (a language server, a
    remote parser, a different grammar toolchain) can be substituted without
    touching the extractor, because the extractor only ever sees a
    ``ParseOutcome``.
    """

    def parse(self, source: bytes, language: str) -> ParseOutcome:
        ...


# ---------------------------------------------------------------------------
# Grammar loading
# ---------------------------------------------------------------------------


@lru_cache(maxsize=128)
def _load_language(language: str) -> Any:
    """Load a grammar once per process.

    Grammars are large compiled objects, so caching matters on a repository with
    thousands of files.
    """
    try:
        import tree_sitter_language_pack as pack

        return pack.get_language(language)
    except Exception as error:  # noqa: BLE001 - any loader failure is "unavailable"
        raise GrammarUnavailableError(
            f"grammar {language!r} could not be loaded: {error}"
        ) from error


@lru_cache(maxsize=128)
def _build_parser(language: str) -> Any:
    import tree_sitter as ts

    return ts.Parser(_load_language(language))


def load_grammar(language: str) -> Any:
    """Public accessor for a cached grammar object.

    Used by the extractor, which needs the ``Language`` itself to compile a
    query. Raises :class:`GrammarUnavailableError` if the grammar cannot load.
    """
    return _load_language(language)


# ---------------------------------------------------------------------------
# Tree metrics
# ---------------------------------------------------------------------------


def _walk_iteratively(root: Any) -> tuple[int, int, int, int, list[Any], list[Any]]:
    """Collect tree metrics without recursion.

    Iterative on purpose. A deeply nested source file (the "deep nesting" edge
    case in section 36) produces a tree thousands of levels deep, and a
    recursive walk would hit Python's recursion limit and raise -- precisely the
    outcome section 30 forbids. An explicit stack has no depth limit.

    Returns ``(node_count, max_depth, error_count, missing_count, errors, missing)``.
    """
    node_count = 0
    max_depth = 0
    error_nodes: list[Any] = []
    missing_nodes: list[Any] = []

    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        node_count += 1
        if depth > max_depth:
            max_depth = depth

        if node.type in ERROR_NODE_TYPES:
            error_nodes.append(node)
        if node.is_missing:
            missing_nodes.append(node)

        for child in node.children:
            stack.append((child, depth + 1))

    return (
        node_count,
        max_depth,
        len(error_nodes),
        len(missing_nodes),
        error_nodes,
        missing_nodes,
    )


def _has_clean_top_level_statement(root: Any) -> bool:
    """True if at least one top-level child parsed without errors.

    This is the discriminator between PARTIAL and FAILED. A file where
    everything is inside one giant ERROR node yields False; a file with nine
    good functions and one broken one yields True.
    """
    for child in root.children:
        if child.type in ERROR_NODE_TYPES:
            continue
        if child.is_missing:
            continue
        if not child.is_named:
            continue
        if not child.has_error:
            return True
    return False


def _diagnostics_for(
    error_nodes: list[Any],
    missing_nodes: list[Any],
    language: str,
    file_path: str | None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for node in error_nodes:
        if len(diagnostics) >= MAX_DIAGNOSTICS:
            break
        diagnostics.append(
            Diagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="parse.error_node",
                message=f"unparsable region ({node.type})",
                file_path=file_path,
                language=language,
                span=SourceSpan.from_tree_sitter(node),
                recovery_action=RECOVERY_BLOCK,
            )
        )

    for node in missing_nodes:
        if len(diagnostics) >= MAX_DIAGNOSTICS:
            break
        diagnostics.append(
            Diagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="parse.missing_token",
                message=f"expected {node.type!r} was missing",
                file_path=file_path,
                language=language,
                span=SourceSpan.from_tree_sitter(node),
                recovery_action=RECOVERY_BLOCK,
            )
        )

    total = len(error_nodes) + len(missing_nodes)
    if total > MAX_DIAGNOSTICS:
        diagnostics.append(
            Diagnostic(
                severity=DiagnosticSeverity.INFO,
                code="parse.truncated",
                message=(
                    f"{total} syntax problems found; only the first "
                    f"{MAX_DIAGNOSTICS} are reported"
                ),
                file_path=file_path,
                language=language,
                recovery_action=RECOVERY_NONE,
            )
        )
    return diagnostics


# ---------------------------------------------------------------------------
# The backend
# ---------------------------------------------------------------------------


class TreeSitterParser:
    """Parse source bytes with a tree-sitter grammar.

    ``file_path`` is accepted on :meth:`parse` purely so diagnostics can name the
    file they came from; the parser itself is stateless and reusable across
    files of the same language.
    """

    def __init__(self, max_diagnostics: int = MAX_DIAGNOSTICS) -> None:
        self.max_diagnostics = max_diagnostics

    def parse(
        self, source: bytes, language: str, file_path: str | None = None
    ) -> ParseOutcome:
        if not source.strip():
            return ParseOutcome(
                status=ParseStatus.EMPTY,
                language=language,
                source=source,
                diagnostics=[
                    Diagnostic(
                        severity=DiagnosticSeverity.INFO,
                        code="parse.empty",
                        message="file contains no tokens",
                        file_path=file_path,
                        language=language,
                        recovery_action=RECOVERY_NONE,
                    )
                ],
            )

        try:
            parser = _build_parser(language)
        except GrammarUnavailableError as error:
            return ParseOutcome(
                status=ParseStatus.UNSUPPORTED,
                language=language,
                source=source,
                diagnostics=[
                    Diagnostic(
                        severity=DiagnosticSeverity.WARNING,
                        code="parse.grammar_unavailable",
                        message=str(error),
                        file_path=file_path,
                        language=language,
                        recovery_action=RECOVERY_NONE,
                    )
                ],
            )

        tree = parser.parse(source)
        root = tree.root_node

        node_count, max_depth, error_count, missing_count, error_nodes, missing_nodes = (
            _walk_iteratively(root)
        )

        if error_count == 0 and missing_count == 0:
            status = ParseStatus.OK
        elif not _has_clean_top_level_statement(root):
            # Nothing at the top level parsed. Either the root is a single
            # ERROR node, or every statement is broken.
            status = ParseStatus.FAILED
        else:
            status = ParseStatus.PARTIAL

        diagnostics = _diagnostics_for(error_nodes, missing_nodes, language, file_path)
        if status is ParseStatus.FAILED:
            diagnostics.append(
                Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="parse.no_clean_statements",
                    message="no top-level statement parsed; file yields no symbols",
                    file_path=file_path,
                    language=language,
                    recovery_action=RECOVERY_FILE,
                )
            )

        return ParseOutcome(
            status=status,
            language=language,
            source=source,
            tree=tree,
            diagnostics=diagnostics[: self.max_diagnostics + 1],
            node_count=node_count,
            max_depth=max_depth,
            error_node_count=error_count,
            missing_node_count=missing_count,
        )
