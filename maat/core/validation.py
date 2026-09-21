"""Stage 7: validate the model before it is published (section 14).

The validator answers one question: **may this model be published?** It returns a
report rather than raising, because failure is data everywhere else in this project
and validation is not an exception to that.

Two rules shape the whole module:

1. **Do not re-derive what ``problems()`` already checks.** ``SemanticIR.problems()``
   and the per-entity ``problems()`` methods already enforce referential integrity,
   duplicate *IDs*, confidence/status consistency and source-location validity. This
   module calls ``problems()`` once and turns each string into a finding. A second
   implementation of the same rule would be a second source of truth, and the two
   would drift.
2. **Only structural invalidity blocks publication.** An unresolved edge is correct
   behaviour, not a defect (section 4.2, D29), so it is reported and the model still
   publishes. A dangling reference, an invalid span or a duplicate edge is a defect,
   and publication is refused.

Spec references (section numbers refer to SPEC.md):
    section 14  -- relationship validation (the acceptance criteria)
    section 4.2 -- an explicit unresolved edge beats a confident wrong one
    D14         -- a relationship ID includes line *and* column
    D26         -- a bounded candidate list, not a payload
    D29         -- unresolved edges are reported, never failed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from .contracts import SemanticIR
from .enums import DiagnosticSeverity, ResolutionStatus
from .locations import SourceSpan

# ---------------------------------------------------------------------------
# Finding codes
# ---------------------------------------------------------------------------

#: A string produced by ``SemanticIR.problems()``. Carries the raw text.
CODE_MODEL_PROBLEM: Final[str] = "model.problem"
#: Two relationships with the same source, type, target *and* location.
CODE_DUPLICATE_EDGE: Final[str] = "relationship.duplicate_edge"
#: Several relationships sharing source, type and target at different locations.
#: Legal (D14) but worth reporting.
CODE_REPEATED_EDGE: Final[str] = "relationship.repeated_edge"
#: An ``Evidence.entity_id`` that names neither a symbol nor a relationship.
CODE_ORPHAN_EVIDENCE: Final[str] = "evidence.orphan"
#: An entity stamped with a different ``model_version`` than the model itself.
CODE_VERSION_MISMATCH: Final[str] = "entity.version_mismatch"
#: A heuristic edge below the confidence threshold.
CODE_HEURISTIC_LOW: Final[str] = "relationship.heuristic_low_confidence"
#: A heuristic edge at or above the threshold.
CODE_HEURISTIC_EDGE: Final[str] = "relationship.heuristic_edge"
#: One or more relationships are explicitly unresolved.
CODE_UNRESOLVED_EDGES: Final[str] = "model.unresolved_edges"
#: One or more relationships are ambiguous.
CODE_AMBIGUOUS_EDGES: Final[str] = "model.ambiguous_edges"

#: The confidence at or above which a heuristic edge is reported as ordinary.
#:
#: The only place a non-blocking confidence judgement is made, so the whole policy
#: is auditable in one line. Nothing in the model currently produces a heuristic
#: edge -- no rung of the ladder claims ``RESOLVED_HEURISTIC`` -- so this is a
#: declared policy waiting for the first resolver rung that needs it.
HEURISTIC_MIN: Final[float] = 0.5

#: Upper bound on the ids recorded in a summary finding's details.
#:
#: The same reasoning as the resolver's candidate cap (D26): a report exists so a
#: reader can *act*, and a model with 177 unresolved edges would otherwise turn one
#: diagnostic into a 177-element payload.
MAX_SAMPLE: Final[int] = 8

#: Sort order for findings, so ``to_dict()`` is stable regardless of insertion.
_SEVERITY_RANK: Final[dict[DiagnosticSeverity, int]] = {
    DiagnosticSeverity.ERROR: 0,
    DiagnosticSeverity.WARNING: 1,
    DiagnosticSeverity.INFO: 2,
}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class ValidationFinding:
    """One thing validation noticed, and how much it matters."""

    severity: DiagnosticSeverity
    code: str
    message: str
    entity_id: str | None = None
    entity_kind: str | None = None
    location: SourceSpan | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": str(self.severity),
            "code": self.code,
            "message": self.message,
            "entity_id": self.entity_id,
            "entity_kind": self.entity_kind,
            "location": self.location.to_dict() if self.location else None,
            "details": self.details,
        }


@dataclass
class ValidationReport:
    """What one validation pass found, and whether it blocks publication.

    Deliberately separate from the model: a finding is evidence *about* the model's
    construction, not an attribute of an entity, so persisting findings into the
    model would tie the schema to the checks that happened to exist.
    """

    model_version: str
    findings: list[ValidationFinding] = field(default_factory=list)
    #: The raw ``ir.problems()`` strings, kept so nothing is lost in translation.
    problems: list[str] = field(default_factory=list)
    #: How many relationships were examined.
    checked_relationships: int = 0
    duplicate_edges: int = 0
    orphan_entities: int = 0
    #: Relationships left explicitly unresolved, and why that is not an error (D29).
    unresolved_relationships: int = 0
    ambiguous_relationships: int = 0

    @property
    def errors(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.severity is DiagnosticSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.severity is DiagnosticSeverity.WARNING]

    @property
    def infos(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.severity is DiagnosticSeverity.INFO]

    @property
    def blocks_publication(self) -> bool:
        """Only a structural defect stops a model being written (section 14 AC6)."""
        return bool(self.errors)

    @property
    def is_valid(self) -> bool:
        return not self.blocks_publication

    def counts(self) -> dict[str, int]:
        return {
            DiagnosticSeverity.ERROR.value: len(self.errors),
            DiagnosticSeverity.WARNING.value: len(self.warnings),
            DiagnosticSeverity.INFO.value: len(self.infos),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "valid": self.is_valid,
            "blocks_publication": self.blocks_publication,
            "counts": self.counts(),
            "checked_relationships": self.checked_relationships,
            "duplicate_edges": self.duplicate_edges,
            "orphan_entities": self.orphan_entities,
            "unresolved_relationships": self.unresolved_relationships,
            "ambiguous_relationships": self.ambiguous_relationships,
            "findings": [f.to_dict() for f in self.findings],
            "problems": self.problems,
        }


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def _edge_key(relationship: Any) -> tuple[Any, ...]:
    """Identity of an edge *including* its location.

    The location is part of the key because D14 makes two call sites on one line two
    distinct relationships. Without it, ``f(); g()`` would look like a duplicate.
    """
    return (
        relationship.source_symbol_id,
        relationship.relationship_type.value,
        relationship.target_symbol_id,
        relationship.source_location.start_line,
        relationship.source_location.start_col,
    )


def duplicate_edge_findings(ir: SemanticIR) -> list[ValidationFinding]:
    """Section 14 AC1 -- duplicate relationships are rejected.

    A duplicate is the *same edge twice*: same source, type, target and location.
    Two calls to the same target from different places are not duplicates (D14) and
    are reported as ordinary repeats instead.
    """
    findings: list[ValidationFinding] = []
    seen: dict[tuple[Any, ...], str] = {}
    for relationship in ir.relationships:
        key = _edge_key(relationship)
        first = seen.get(key)
        if first is not None:
            findings.append(
                ValidationFinding(
                    severity=DiagnosticSeverity.ERROR,
                    code=CODE_DUPLICATE_EDGE,
                    message=(
                        f"{relationship.id} duplicates {first} "
                        f"(same source, type, target and location)"
                    ),
                    entity_id=relationship.id,
                    entity_kind="relationship",
                    location=relationship.source_location,
                    details={"duplicate_of": first},
                )
            )
            continue
        seen[key] = relationship.id

    # Repeats at *different* locations are legal, so they are reported, not rejected.
    members: dict[tuple[Any, ...], list[str]] = {}
    locations: dict[tuple[Any, ...], set[tuple[int, int]]] = {}
    for relationship in ir.relationships:
        wide = (
            relationship.source_symbol_id,
            relationship.relationship_type.value,
            relationship.target_symbol_id,
        )
        members.setdefault(wide, []).append(relationship.id)
        locations.setdefault(wide, set()).add(
            (
                relationship.source_location.start_line,
                relationship.source_location.start_col,
            )
        )
    for wide in sorted(locations, key=str):
        if len(locations[wide]) > 1:
            ids = sorted(members[wide])
            findings.append(
                ValidationFinding(
                    severity=DiagnosticSeverity.INFO,
                    code=CODE_REPEATED_EDGE,
                    message=(
                        f"{len(ids)} relationships share source, type and target "
                        f"at {len(locations[wide])} distinct locations"
                    ),
                    entity_id=ids[0],
                    entity_kind="relationship",
                    details={"relationship_ids": ids[:MAX_SAMPLE]},
                )
            )
    return findings


def orphan_findings(ir: SemanticIR) -> list[ValidationFinding]:
    """Section 14 -- the orphan detector.

    Only ``Evidence.entity_id`` is checked here. ``SemanticIR.problems()`` already
    covers ``chunk.symbol_id`` and ``binding.enclosing_symbol_id``, and it checks
    evidence by ``file_id`` -- but nothing checks that evidence points at an entity
    that exists. That is the gap this fills.
    """
    known = {symbol.id for symbol in ir.symbols} | {
        relationship.id for relationship in ir.relationships
    }
    findings: list[ValidationFinding] = []
    for evidence in ir.evidence:
        if evidence.entity_id not in known:
            findings.append(
                ValidationFinding(
                    severity=DiagnosticSeverity.ERROR,
                    code=CODE_ORPHAN_EVIDENCE,
                    message=(
                        f"evidence.entity_id {evidence.entity_id!r} names neither "
                        f"a symbol nor a relationship"
                    ),
                    entity_id=evidence.id,
                    entity_kind="evidence",
                    details={"missing_entity_id": evidence.entity_id},
                )
            )
    return findings


def version_findings(ir: SemanticIR) -> list[ValidationFinding]:
    """Section 14 -- version consistency.

    Every entity in a model must belong to that model. A mismatch means an entity
    survived a rebuild it should have been replaced by, which would make the model
    a blend of two versions.
    """
    findings: list[ValidationFinding] = []
    collections = (
        ("file", ir.files),
        ("symbol", ir.symbols),
        ("relationship", ir.relationships),
        ("binding", ir.bindings),
        ("evidence", ir.evidence),
        ("chunk", ir.chunks),
    )
    for kind, entities in collections:
        for entity in entities:
            if entity.model_version != ir.model_version:
                findings.append(
                    ValidationFinding(
                        severity=DiagnosticSeverity.ERROR,
                        code=CODE_VERSION_MISMATCH,
                        message=(
                            f"{kind} {entity.id} records model_version "
                            f"{entity.model_version!r}, but the model is "
                            f"{ir.model_version!r}"
                        ),
                        entity_id=entity.id,
                        entity_kind=kind,
                        details={
                            "expected": ir.model_version,
                            "found": entity.model_version,
                        },
                    )
                )
    return findings


def confidence_findings(ir: SemanticIR) -> list[ValidationFinding]:
    """Section 14 -- the confidence policy.

    Only ``RESOLVED_HEURISTIC`` needs a judgement: every other status/confidence
    pairing is already an error in ``Relationship.problems()``, so repeating those
    rules here would be the second source of truth this module exists to avoid.
    """
    findings: list[ValidationFinding] = []
    for relationship in ir.relationships:
        if relationship.resolution_status is not ResolutionStatus.RESOLVED_HEURISTIC:
            continue
        low = relationship.confidence < HEURISTIC_MIN
        findings.append(
            ValidationFinding(
                severity=(
                    DiagnosticSeverity.WARNING if low else DiagnosticSeverity.INFO
                ),
                code=CODE_HEURISTIC_LOW if low else CODE_HEURISTIC_EDGE,
                message=(
                    f"{relationship.id} is heuristic with confidence "
                    f"{relationship.confidence}"
                    + (f", below the {HEURISTIC_MIN} threshold" if low else "")
                ),
                entity_id=relationship.id,
                entity_kind="relationship",
                location=relationship.source_location,
                details={
                    "confidence": relationship.confidence,
                    "threshold": HEURISTIC_MIN,
                },
            )
        )
    return findings


def resolution_findings(ir: SemanticIR) -> list[ValidationFinding]:
    """Section 14 AC4 and D29 -- unresolved and ambiguous edges are *reported*.

    One finding per category rather than one per edge. A model can legitimately hold
    hundreds of unresolved edges, and emitting a finding for each would turn a
    diagnostic into a payload -- the same mistake the resolver's candidate cap (D26)
    exists to prevent. The count is exact; the id sample is bounded.
    """
    findings: list[ValidationFinding] = []
    unresolved = [
        r.id
        for r in ir.relationships
        if r.resolution_status is ResolutionStatus.UNRESOLVED
    ]
    ambiguous = [
        r.id
        for r in ir.relationships
        if r.resolution_status is ResolutionStatus.AMBIGUOUS
    ]
    if unresolved:
        findings.append(
            ValidationFinding(
                severity=DiagnosticSeverity.INFO,
                code=CODE_UNRESOLVED_EDGES,
                message=(
                    f"{len(unresolved)} relationships are explicitly unresolved; "
                    f"this is correct behaviour, not a failure (D29)"
                ),
                entity_kind="model",
                details={
                    "count": len(unresolved),
                    "sample": sorted(unresolved)[:MAX_SAMPLE],
                },
            )
        )
    if ambiguous:
        findings.append(
            ValidationFinding(
                severity=DiagnosticSeverity.INFO,
                code=CODE_AMBIGUOUS_EDGES,
                message=(
                    f"{len(ambiguous)} relationships are ambiguous and keep their "
                    f"placeholder target"
                ),
                entity_kind="model",
                details={
                    "count": len(ambiguous),
                    "sample": sorted(ambiguous)[:MAX_SAMPLE],
                },
            )
        )
    return findings


def _model_problem_findings(ir: SemanticIR) -> list[ValidationFinding]:
    """Turn each ``ir.problems()`` string into an ERROR finding.

    This is the delegation rule: the checks already exist, so they are consumed
    rather than re-implemented.
    """
    return [
        ValidationFinding(
            severity=DiagnosticSeverity.ERROR,
            code=CODE_MODEL_PROBLEM,
            message=problem,
            entity_kind="model",
        )
        for problem in ir.problems()
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def validate_ir(ir: SemanticIR) -> ValidationReport:
    """Validate ``ir`` and return the report. Never raises.

    ``ir.problems()`` is called exactly once, and its raw strings are preserved on
    the report so a caller that only wants the old behaviour still has it.
    """
    problems = ir.problems()
    findings = _model_problem_findings(ir)
    findings.extend(duplicate_edge_findings(ir))
    findings.extend(orphan_findings(ir))
    findings.extend(version_findings(ir))
    findings.extend(confidence_findings(ir))
    findings.extend(resolution_findings(ir))

    # Sorted so the report is byte-stable for identical input.
    findings.sort(
        key=lambda f: (
            _SEVERITY_RANK[f.severity],
            f.code,
            f.entity_id or "",
        )
    )

    report = ValidationReport(
        model_version=ir.model_version,
        findings=findings,
        problems=problems,
        checked_relationships=len(ir.relationships),
    )
    report.duplicate_edges = sum(
        1 for f in findings if f.code == CODE_DUPLICATE_EDGE
    )
    report.orphan_entities = sum(
        1 for f in findings if f.code == CODE_ORPHAN_EVIDENCE
    )
    report.unresolved_relationships = sum(
        1
        for r in ir.relationships
        if r.resolution_status is ResolutionStatus.UNRESOLVED
    )
    report.ambiguous_relationships = sum(
        1
        for r in ir.relationships
        if r.resolution_status is ResolutionStatus.AMBIGUOUS
    )
    return report


def deduplicate_edges(ir: SemanticIR) -> list[str]:
    """Remove exact duplicate edges, returning the ids removed.

    Opt-in, and deliberately not called by the validator. Section 14 AC1 allows
    duplicates to be "removed *or* rejected", and this module rejects by default:
    silently rewriting the model would hide the extractor bug that produced the
    duplicate, and the model is meant to be the source of truth. A caller who
    genuinely wants the repair asks for it.
    """
    seen: set[tuple[Any, ...]] = set()
    kept: list[Any] = []
    removed: list[str] = []
    for relationship in ir.relationships:
        key = _edge_key(relationship)
        if key in seen:
            removed.append(relationship.id)
            continue
        seen.add(key)
        kept.append(relationship)
    ir.relationships[:] = kept
    return removed
