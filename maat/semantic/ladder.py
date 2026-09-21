"""The resolution precedence ladder (D24).

D24 chose a ladder over a confidence score, for one reason: **the status is the
explanation.** A score of ``0.73`` tells a reader nothing about why an edge was
accepted, nor whether it is safe to trust. A rung name says exactly which syntactic
fact justified the edge, so an audit is a matter of reading the name rather than
re-deriving a weight.

``confidence`` is therefore *derived* from the rung (see ``ResolutionRung.confidence``)
rather than stored beside it, so a stored confidence can never contradict a stored
status.

The ladder is ordered by how much the evidence constrains the answer. A rung is tried
only if every rung above it failed, so a stronger fact is never overridden by a weaker
one:

======  ==========================  ==========================================
Rung    Evidence                    Why it is where it is
======  ==========================  ==========================================
S1      Same file, exact name       The narrowest possible scope. If a symbol is
                                    visible in the caller's own file and matches
                                    exactly, nothing else can be more
                                    authoritative.
S2      Receiver's own class        ``self.validate`` -- the owner is known from
                                    the enclosing symbol, so the class body is a
                                    closed set. Still certain, one indirection
                                    less local than S1.
S3      Bound receiver's class      ``self.payment_service.process`` -- the type
                                    comes from a ``Binding``, which is an
                                    annotation the author wrote. Certain when the
                                    binding is, which is why it sits below S2 but
                                    above any name-based guess.
S4      Imported module symbol      A bare name matching a class or function in a
                                    module this file imports. Certain, but reached
                                    through an import rather than through scope.
S5      Unique name in the model    No import, no local match, exactly one symbol
                                    of that name anywhere. Weak evidence, unique
                                    answer.
S6      Several equally plausible   Recorded as AMBIGUOUS with the candidate list,
                                    never guessed (section 13 AC3, D26).
S7      Attribute chain, resolved   ``a.b.c`` where the head resolved and the tail
                                    is a member of it.
S8      Attribute chain, ambiguous  ... or where it did not resolve to one thing.
S9      Nothing matched             UNRESOLVED, kept explicitly (section 13 AC4,
                                    D29).
======  ==========================  ==========================================

``RESOLVED_HEURISTIC`` is deliberately *not* produced by any rung. It is reserved for
a resolution that is probable but not certain, and nothing in the current model
provides evidence of that quality. Inventing a rung to use it would be exactly the
"confident wrong edge" section 4.2 forbids, so the ladder leaves it unfired rather
than manufacturing a use for it. A test asserts this, so adding one is a deliberate
act rather than an accident.

Spec references (section numbers refer to SPEC.md):
    section 13  -- symbol and relationship resolution (AC1-AC6)
    section 4.2 -- an explicit unresolved edge beats a confident wrong one
    D24         -- the ladder decision
    D26         -- an ambiguous edge lists its candidates
    D28         -- an ambiguous edge keeps its placeholder target
    D29         -- unresolved edges are reported, never failed
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..core.enums import ResolutionStatus


class ResolutionRung(str, Enum):
    """Which syntactic fact justified an edge. Ordered strongest evidence first."""

    SAME_FILE_EXACT = "S1_SAME_FILE_EXACT"
    RECEIVER_CLASS_MEMBER = "S2_RECEIVER_CLASS_MEMBER"
    BOUND_TYPE_MEMBER = "S3_BOUND_TYPE_MEMBER"
    IMPORTED_MODULE_SYMBOL = "S4_IMPORTED_MODULE_SYMBOL"
    UNIQUE_IN_MODEL = "S5_UNIQUE_IN_MODEL"
    AMBIGUOUS_IN_MODEL = "S6_AMBIGUOUS_IN_MODEL"
    ATTRIBUTE_CHAIN = "S7_ATTRIBUTE_CHAIN"
    ATTRIBUTE_CHAIN_AMBIGUOUS = "S8_ATTRIBUTE_CHAIN_AMBIGUOUS"
    NONE = "S9_NONE"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value

    @property
    def order(self) -> int:
        """1-based position in the ladder, for sorting and for tests."""
        return _LADDER_ORDER[self]

    @property
    def status(self) -> ResolutionStatus:
        """The resolution status this rung produces."""
        return _RUNG_STATUS[self]

    @property
    def confidence(self) -> float:
        """The confidence this rung produces.

        Derived from the rung rather than stored next to it, so the two can never
        disagree.
        """
        return _RUNG_CONFIDENCE[self]


#: Ladder position, strongest evidence first.
#:
#: Contiguity from 1 is asserted by a test. A gap would silently change which rung
#: wins -- and because the ordering *is* the correctness argument, an ordering bug
#: would otherwise be invisible in a passing suite.
_LADDER_ORDER: Final[dict[ResolutionRung, int]] = {
    ResolutionRung.SAME_FILE_EXACT: 1,
    ResolutionRung.RECEIVER_CLASS_MEMBER: 2,
    ResolutionRung.BOUND_TYPE_MEMBER: 3,
    ResolutionRung.IMPORTED_MODULE_SYMBOL: 4,
    ResolutionRung.UNIQUE_IN_MODEL: 5,
    ResolutionRung.AMBIGUOUS_IN_MODEL: 6,
    ResolutionRung.ATTRIBUTE_CHAIN: 7,
    ResolutionRung.ATTRIBUTE_CHAIN_AMBIGUOUS: 8,
    ResolutionRung.NONE: 9,
}

#: The status each rung produces. Only S6 and S8 are ambiguous; only S9 fails.
_RUNG_STATUS: Final[dict[ResolutionRung, ResolutionStatus]] = {
    ResolutionRung.SAME_FILE_EXACT: ResolutionStatus.RESOLVED_EXACT,
    ResolutionRung.RECEIVER_CLASS_MEMBER: ResolutionStatus.RESOLVED_EXACT,
    ResolutionRung.BOUND_TYPE_MEMBER: ResolutionStatus.RESOLVED_EXACT,
    ResolutionRung.IMPORTED_MODULE_SYMBOL: ResolutionStatus.RESOLVED_EXACT,
    ResolutionRung.UNIQUE_IN_MODEL: ResolutionStatus.RESOLVED_EXACT,
    ResolutionRung.AMBIGUOUS_IN_MODEL: ResolutionStatus.AMBIGUOUS,
    ResolutionRung.ATTRIBUTE_CHAIN: ResolutionStatus.RESOLVED_EXACT,
    ResolutionRung.ATTRIBUTE_CHAIN_AMBIGUOUS: ResolutionStatus.AMBIGUOUS,
    ResolutionRung.NONE: ResolutionStatus.UNRESOLVED,
}

#: Confidence per rung.
#:
#: Certainty is binary here on purpose. Every rung above S5 rests on a declared
#: syntactic fact, so it is certain; the two ambiguous rungs and the failure rung are
#: not. There is no partial credit, because a partial score would have to be justified
#: by evidence the model does not carry -- which is what ``RESOLVED_HEURISTIC`` is
#: reserved for.
_RUNG_CONFIDENCE: Final[dict[ResolutionRung, float]] = {
    ResolutionRung.SAME_FILE_EXACT: 1.0,
    ResolutionRung.RECEIVER_CLASS_MEMBER: 1.0,
    ResolutionRung.BOUND_TYPE_MEMBER: 1.0,
    ResolutionRung.IMPORTED_MODULE_SYMBOL: 1.0,
    ResolutionRung.UNIQUE_IN_MODEL: 1.0,
    ResolutionRung.AMBIGUOUS_IN_MODEL: 0.0,
    ResolutionRung.ATTRIBUTE_CHAIN: 1.0,
    ResolutionRung.ATTRIBUTE_CHAIN_AMBIGUOUS: 0.0,
    ResolutionRung.NONE: 0.0,
}

#: Receiver names that mean "the current instance or type".
#:
#: This is the only cross-language knowledge in the module, and it is deliberately
#: data rather than branching: ``this`` (Java, TypeScript), ``self`` (Python, Ruby),
#: and ``cls`` / ``Self`` (Rust) all denote the same thing, so the resolver can treat
#: them identically without knowing which grammar produced the symbol. That is what
#: lets one resolver serve every extractable language.
INSTANCE_RECEIVERS: Final[frozenset[str]] = frozenset({"self", "this", "cls", "Self"})


def resolve_qualified_name(
    qualified_name: str, model_names: frozenset[str]
) -> tuple[ResolutionRung, list[str]]:
    """Match a dotted name against the model's known qualified names.

    Returns the rung the match justifies together with the matching names, or
    ``(ResolutionRung.NONE, [])`` when nothing matches. It returns *evidence*; it
    decides nothing about an edge.

    A name matches when a known qualified name equals it, or ends with it at a
    segment boundary (preceded by ``:`` or ``.``). The boundary check is what stops
    ``b.c`` from matching ``x.abc`` -- without it a short name would silently pick up
    unrelated symbols, which is worse than an explicit miss.

    One match is a resolved chain (S7); several are reported as ambiguous (S8) rather
    than resolved by an arbitrary pick (section 13 AC3). Matches are sorted, so the
    result is deterministic.
    """
    if not qualified_name:
        return ResolutionRung.NONE, []

    matches = sorted(
        name
        for name in model_names
        if name == qualified_name
        or name.endswith(f":{qualified_name}")
        or name.endswith(f".{qualified_name}")
    )
    if not matches:
        return ResolutionRung.NONE, []
    if len(matches) == 1:
        return ResolutionRung.ATTRIBUTE_CHAIN, matches
    return ResolutionRung.ATTRIBUTE_CHAIN_AMBIGUOUS, matches
