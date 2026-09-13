"""Stage 5 — building the semantic IR from facts.

This is where facts acquire identity. Three things happen here that do not
happen anywhere else, and each of them is a decision worth stating.

**Stable IDs, with collision handling.** A symbol's ID is a hash of
``(path, symbol_type, qualified_name)``. That is stable across runs and
machines, and it keeps two same-named classes in different files distinct. But
it collides for *overloads*: two Java methods named ``process`` in the same
class share a qualified name and therefore a hash. Rather than put a line number
into every ID -- which would make every symbol below an inserted line change
identity -- collisions are detected and resolved only where they actually occur,
by appending a short digest of the signature. The common case stays stable; the
overload case gets a deterministic disambiguator.

**CONTAINS is resolved exactly; everything else is unresolved.** Structural
containment is not a reference. When a method is parsed inside a class, both
endpoints are known with certainty from the parse alone, so the edge is
``RESOLVED_EXACT``. Imports, calls and inheritance name things that may live
outside the file, so they are recorded ``UNRESOLVED`` with their raw target
text intact (section 4.2: prefer an explicit unresolved relationship over an
incorrect confident one). The resolver in a later stage upgrades them.

**Evidence is produced eagerly.** Section 13 AC6 requires every relationship to
point back at source evidence, and section 41 Rule 3 forbids trusting any answer
without it. Producing evidence at build time -- rather than reconstructing it
when someone asks -- means an entity either has provenance or is rejected
(section 14), and there is no path by which an unsupported claim reaches a
reader.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from ..core import ids as idgen
from ..core.contracts import (
    Diagnostic,
    Evidence,
    FileRecord,
    Relationship,
    SemanticChunk,
    Symbol,
)
from ..core.enums import (
    RECOVERY_NONE,
    DiagnosticSeverity,
    RelationshipType,
    ResolutionStatus,
    SymbolType,
)
from ..core.locations import SourceSpan
from .extractors.base import ExtractionFacts, SymbolFact

#: Provenance label for evidence produced by the offline parser.
#: Later stages add "graph", "fts" and "vector" values for retrieval-produced
#: evidence; keeping the vocabulary shared lets the validator tell a build-time
#: fact apart from a retrieval hit (section 25.2, "Confidence").
SOURCE_OFFLINE_AST = "offline.ast"

#: Rough characters-per-token ratio used for the token budget. Deliberately
#: crude: it exists so section 22 AC6 has something to enforce, and it must not
#: depend on a tokeniser library that would tie the model to one provider.
CHARS_PER_TOKEN = 4

#: Relationship types that are structurally determined and therefore exactly
#: resolvable within a single file.
STRUCTURAL_TYPES = frozenset({RelationshipType.CONTAINS})


@dataclass
class FileIR:
    """The semantic IR contributed by one file."""

    symbols: list[Symbol] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    chunks: list[SemanticChunk] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Source slicing
# ---------------------------------------------------------------------------


def _slice_lines(source: bytes, span: SourceSpan) -> str:
    """Return the text of a span, by whole lines.

    Lines rather than byte offsets: ``SourceSpan`` deliberately stores line and
    column rather than byte positions, because byte offsets are meaningless
    once a file is read as text. Column-level slicing would also have to reckon
    with tree-sitter reporting columns in *bytes* while Python strings are
    indexed in *characters*, which diverges on any file containing non-ASCII
    text. Whole-line slicing sidesteps that entirely and is what a reader
    actually wants to see.
    """
    text = source.decode("utf-8", errors="replace")
    lines = text.splitlines()
    start = max(0, span.start_line - 1)
    end = min(len(lines), span.end_line)
    if start >= end:
        return ""
    return "\n".join(lines[start:end])


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN) if text else 0


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# ID assignment
# ---------------------------------------------------------------------------


def _assign_symbol_ids(
    facts: list[SymbolFact], file_path: str
) -> tuple[dict[int, str], list[Diagnostic]]:
    """Assign a stable, unique ID to every symbol fact.

    Returns ``({id(fact): symbol_id}, diagnostics)``. Keyed by ``id(fact)``
    because two facts can share a qualified name and so cannot be keyed by name.
    """
    diagnostics: list[Diagnostic] = []
    groups: dict[tuple[SymbolType, str], list[SymbolFact]] = {}
    for fact in facts:
        groups.setdefault((fact.symbol_type, fact.qualified_name), []).append(fact)

    assigned: dict[int, str] = {}
    for (symbol_type, qualified_name), group in groups.items():
        if len(group) == 1:
            assigned[id(group[0])] = idgen.symbol_id(
                file_path, str(symbol_type), qualified_name
            )
            continue

        # Overloads: same type, same qualified name. Disambiguate on the
        # signature, which differs between genuine overloads and is stable
        # across edits that do not touch the signature.
        diagnostics.append(
            Diagnostic(
                severity=DiagnosticSeverity.INFO,
                code="ir.overload",
                message=(
                    f"{len(group)} declarations share the qualified name "
                    f"{qualified_name!r}; disambiguating by signature"
                ),
                file_path=file_path,
                span=group[0].span,
                recovery_action=RECOVERY_NONE,
            )
        )
        for fact in sorted(group, key=lambda f: f.span.start_line):
            signature = fact.signature or ""
            suffix = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:6]
            assigned[id(fact)] = idgen.symbol_id(
                file_path, str(symbol_type), f"{qualified_name}#{suffix}"
            )

    # Final guard: if two facts still hash identically (identical overloads,
    # differing only by line), append an ordinal so no ID is silently lost.
    seen: dict[str, int] = {}
    for fact in facts:
        current = assigned.get(id(fact))
        if current is None:
            continue
        count = seen.get(current, 0)
        seen[current] = count + 1
        if count:
            assigned[id(fact)] = f"{current}~{count}"

    return assigned, diagnostics


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_file_ir(
    facts: ExtractionFacts,
    file_record: FileRecord,
    source: bytes,
    model_version: str,
) -> FileIR:
    """Turn one file's facts into validated semantic entities."""
    result = FileIR()
    result.diagnostics.extend(facts.diagnostics)

    if not facts.symbols:
        return result

    symbol_ids, id_diagnostics = _assign_symbol_ids(facts.symbols, file_record.path)
    result.diagnostics.extend(id_diagnostics)

    by_qualified_name: dict[str, str] = {}
    module_fact = facts.symbols[0]
    module_symbol_id = symbol_ids.get(id(module_fact), "")

    # --- symbols ----------------------------------------------------------
    for fact in facts.symbols:
        symbol_id = symbol_ids.get(id(fact))
        if symbol_id is None:
            continue
        text = _slice_lines(source, fact.span)
        symbol = Symbol(
            id=symbol_id,
            file_id=file_record.id,
            name=fact.name,
            qualified_name=fact.qualified_name,
            symbol_type=fact.symbol_type,
            signature=fact.signature,
            location=fact.span,
            documentation=fact.documentation,
            content_hash=_hash_text(text),
            model_version=model_version,
            language=facts.language,
        )
        problems = symbol.problems()
        if problems:
            # Rejected before indexing, per section 12 AC6. Dropping with a
            # reason is the only safe direction: an entity that cannot be
            # validated must not become queryable.
            for problem in problems:
                result.diagnostics.append(
                    Diagnostic(
                        severity=DiagnosticSeverity.ERROR,
                        code="ir.invalid_symbol",
                        message=f"symbol {fact.qualified_name!r} rejected: {problem}",
                        file_path=file_record.path,
                        language=facts.language,
                        span=fact.span,
                        recovery_action=RECOVERY_NONE,
                    )
                )
            continue

        result.symbols.append(symbol)
        by_qualified_name.setdefault(fact.qualified_name, symbol_id)
        result.evidence.append(
            _evidence(
                entity_id=symbol_id,
                file_record=file_record,
                span=fact.span,
                model_version=model_version,
            )
        )

        if text:
            result.chunks.append(
                SemanticChunk(
                    id=idgen.chunk_id(symbol_id, str(fact.symbol_type).lower()),
                    symbol_id=symbol_id,
                    text=text,
                    chunk_type=str(fact.symbol_type).lower(),
                    embedding_id=None,
                    token_count=_estimate_tokens(text),
                    model_version=model_version,
                )
            )

    # --- CONTAINS ---------------------------------------------------------
    for fact in facts.symbols:
        if fact.parent_qualified_name is None:
            continue
        source_id = symbol_ids.get(id(fact))
        target_id = by_qualified_name.get(fact.parent_qualified_name)
        if not source_id or not target_id or source_id == target_id:
            continue
        # Containment is a structural fact, not a reference: both endpoints came
        # from the same parse, so this is exactly resolvable.
        result.relationships.append(
            _relationship(
                source_symbol_id=source_id,
                target_symbol_id=target_id,
                relationship_type=RelationshipType.CONTAINS,
                status=ResolutionStatus.RESOLVED_EXACT,
                confidence=1.0,
                span=fact.span,
                model_version=model_version,
                target_name=fact.parent_qualified_name,
            )
        )

    # --- IMPORTS ----------------------------------------------------------
    for import_fact in facts.imports:
        source_id = _resolve_owner(
            import_fact.enclosing_qualified_name, by_qualified_name, module_symbol_id
        )
        if not source_id:
            continue
        result.relationships.append(
            _relationship(
                source_symbol_id=source_id,
                target_symbol_id=idgen.unresolved_target_id(
                    f"module:{import_fact.module}"
                ),
                relationship_type=RelationshipType.IMPORTS,
                status=ResolutionStatus.UNRESOLVED,
                confidence=0.0,
                span=import_fact.span,
                model_version=model_version,
                target_name=import_fact.module,
            )
        )

    # --- INHERITS ---------------------------------------------------------
    for inherit_fact in facts.inherits:
        source_id = _resolve_owner(
            inherit_fact.enclosing_qualified_name, by_qualified_name, module_symbol_id
        )
        if not source_id:
            continue
        result.relationships.append(
            _relationship(
                source_symbol_id=source_id,
                target_symbol_id=idgen.unresolved_target_id(
                    f"type:{inherit_fact.base_name}"
                ),
                relationship_type=RelationshipType.INHERITS,
                status=ResolutionStatus.UNRESOLVED,
                confidence=0.0,
                span=inherit_fact.span,
                model_version=model_version,
                target_name=inherit_fact.base_name,
            )
        )

    # --- CALLS ------------------------------------------------------------
    for call_fact in facts.calls:
        source_id = _resolve_owner(
            call_fact.enclosing_qualified_name, by_qualified_name, module_symbol_id
        )
        if not source_id:
            continue
        result.relationships.append(
            _relationship(
                source_symbol_id=source_id,
                target_symbol_id=idgen.unresolved_target_id(
                    f"call:{call_fact.target_name}"
                ),
                relationship_type=RelationshipType.CALLS,
                status=ResolutionStatus.UNRESOLVED,
                confidence=0.0,
                span=call_fact.span,
                model_version=model_version,
                target_name=call_fact.target_name,
            )
        )

    # --- file-level chunks -------------------------------------------------
    result.chunks.extend(
        _file_chunks(facts, file_record, source, model_version, module_symbol_id)
    )

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_owner(
    qualified_name: str | None,
    by_qualified_name: dict[str, str],
    module_symbol_id: str,
) -> str | None:
    if qualified_name is None:
        return module_symbol_id or None
    return by_qualified_name.get(qualified_name, module_symbol_id or None)


def _evidence(
    entity_id: str,
    file_record: FileRecord,
    span: SourceSpan,
    model_version: str,
) -> Evidence:
    return Evidence(
        id=idgen.evidence_id(
            entity_id, file_record.id, span.start_line, span.end_line, SOURCE_OFFLINE_AST
        ),
        entity_id=entity_id,
        file_id=file_record.id,
        start_line=span.start_line,
        end_line=span.end_line,
        retrieval_source=SOURCE_OFFLINE_AST,
        score=1.0,
        model_version=model_version,
    )


def _relationship(
    source_symbol_id: str,
    target_symbol_id: str,
    relationship_type: RelationshipType,
    status: ResolutionStatus,
    confidence: float,
    span: SourceSpan,
    model_version: str,
    target_name: str | None,
) -> Relationship:
    return Relationship(
        id=idgen.relationship_id(
            source_symbol_id,
            str(relationship_type),
            target_name or target_symbol_id,
            span.start_line,
            span.start_col,
        ),
        source_symbol_id=source_symbol_id,
        target_symbol_id=target_symbol_id,
        relationship_type=relationship_type,
        resolution_status=status,
        confidence=confidence,
        source_location=span,
        model_version=model_version,
        target_name=target_name,
    )


def _file_chunks(
    facts: ExtractionFacts,
    file_record: FileRecord,
    source: bytes,
    model_version: str,
    module_symbol_id: str,
) -> list[SemanticChunk]:
    """Chunks that belong to the file rather than to one symbol.

    An ``imports`` chunk is emitted even when a file has none, because
    "this module imports nothing" is itself a useful retrieval result and its
    absence would be indistinguishable from "we failed to look". A
    ``parse_error`` chunk is emitted only for degraded files, so the reason a
    file is incomplete is retrievable alongside the code that did parse.
    """
    chunks: list[SemanticChunk] = []
    if not module_symbol_id:
        return chunks

    if facts.imports:
        rendered = "\n".join(
            f"{item.module}" + (f" ({', '.join(item.names)})" if item.names else "")
            for item in facts.imports
        )
    else:
        rendered = "(no imports)"

    chunks.append(
        SemanticChunk(
            id=idgen.chunk_id(module_symbol_id, "imports"),
            symbol_id=module_symbol_id,
            text=rendered,
            chunk_type="imports",
            embedding_id=None,
            token_count=_estimate_tokens(rendered),
            model_version=model_version,
        )
    )

    if file_record.is_degraded:
        messages = "\n".join(
            f"{d.code}: {d.message}" for d in facts.diagnostics
        ) or (file_record.parse_error or "parse failed")
        chunks.append(
            SemanticChunk(
                id=idgen.chunk_id(module_symbol_id, "parse_error"),
                symbol_id=module_symbol_id,
                text=messages,
                chunk_type="parse_error",
                embedding_id=None,
                token_count=_estimate_tokens(messages),
                model_version=model_version,
            )
        )

    return chunks
