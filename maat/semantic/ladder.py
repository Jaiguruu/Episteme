"""The resolution precedence ladder (D24).

D24 chose a ladder over a confidence score, for one reason: **the status is the
explanation.** A score of ``0.73`` tells a reader nothing about why an edge was
accepted, and nothing about whether it is safe to trust. A rung name says exactly
which syntactic fact justified the edge, so an audit is a matter of reading the
name rather than re-deriving a weight.

The ladder is ordered by how much the evidence constrains the answer. A rung is
tried only if every rung above it failed, so a stronger fact is never overridden
by a weaker one:

======  ==========================  ==========================================
Rung    Evidence                    Why it is where it is
======  ==========================  ==========================================
S1      Same file, exact name       The narrowest possible scope. If a symbol
                                    is visible in the caller's own file and
                                    matches exactly, nothing else can be more
                                    authoritative.
S2      Receiver's own class        ``self.validate`` -- the owner is known from
                                    the enclosing symbol, so the class body is a
                                    closed set. Still certain, but one
                                    indirection less local than S1.
S3      Bound receiver's class      ``self.payment_service.process`` -- the type
                                    comes from a ``Binding``, which is an
                                    annotation the author wrote. Certain when the
                                    binding is, which is why it sits below S2
                                    but above any name-based guess.
S4      Imported module symbol      A bare name that matches a class or function
                                    in a module this file imports. Certain, but
                                    reached through an import rather than scope.
S5      Same package, unique name   No import, no local match, exactly one symbol
                                    of that name anywhere in the model. Weak
                                    evidence, unique answer.
S6      Same package, several       Several candidates, all equally plausible.
                                    Recorded as AMBIGUOUS with the candidate
                                    list, never guessed (AC3).
S7      Attribute chain, resolved   ``a.b.c`` where the head resolved and the tail
S8      Attribute chain, ambiguous  is a member -- or where it is not.
S9      Nothing matched             UNRESOLVED, kept explicitly (AC4, D29).
======  ==========================  ==========================================

``RESOLVED_HEURISTIC`` is deliberately *not* used by any rung above S4. It is
reserved for a resolution that is probable but not certain, and nothing in the
current model provides evidence of that quality. Inventing a rung to use it would
be exactly the "confident wrong edge" section 4.2 forbids, so the ladder leaves it
unfired rather than manufacturing a use for it.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from ..core.enums import ResolutionStatus


class ResolutionRung(str, Enum):
    """Which syntactic fact justified an edge. Ordered strongest first."""

    SAME_FILE_EXACT = "S1_SAME_FILE_EXACT"
    RECEIVER_CLASS_MEMBER = "S2_RECEIVER_CLASS_MEMBER"
    BOUND_TYPE_MEMBER = "S3_BOUND_TYPE_MEMBER"
    IMPORTED_MODULE_SYMBOL = "S4_IMPORTED_MODULE_SYMBOL"
    UNIQUE_IN_MODEL = "S5_UNIQUE_IN_MODEL"
    AMBIGUOUS_IN_MODEL = "S6_AMBIGUOUS_IN_MODEL"
    ATTRIBUTE_CHAIN = "S7_ATTRIBUTE_CHAIN"
    ATTRIBUTE_CHAIN_AMBIGUOUS = "S8_ATTRIBUTE_CHAIN_AMBIGUOUS"
    NONE = "S9_NONE"

    @property
    def order(self) -> int:
        """1-based position in the ladder, for sorting and for tests."""
        return _LADDER_ORDER[self]

    @property
    def status(self) -> ResolutionStatus:
        """The resolution status a rung produces."""
        return _RUNG_STATUS[self]

    @property
    def confidence(self) -> float:
        """The declared confidence policy for this rung (D24).

        Confidence is a *policy*, not a measurement. These are declared once here
        so that no call site can tune them, and so a reader can see the whole
        policy in one place rather than inferring it from scattered constants.
        """
        return _RUNG_CONFIDENCE[self]


_LADDER_ORDER: Final[dict[ResolutionRung, int]] = {
    rung: index for index, rung in enumerate(ResolutionRung, start=1)
}

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

#: Confidence by rung. Every exact rung is 1.0 -- an exact answer is not 90%
#: certain, it is exact, and a fraction below 1.0 would imply we distrusted our
#: own evidence. Ambiguity and failure carry the values their meaning implies.
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

#: Receivers that mean "the instance of the class I am defined in".
#:
#: D31: a single shared vocabulary rather than a per-language rule. These are
#: linguistic facts -- every object language has some pronoun for "this receiver"
#: -- so adding a language means adding a word here, not writing Python. Kept
#: deliberately small: a wrong entry here silently retargets calls.
INSTANCE_RECEIVERS: Final[frozenset[str]] = frozenset({"self", "this", "cls", "Self"})


def resolve_qualified_name(
    qualified_name: str, model_names: frozenset[str]
) -> tuple[ResolutionRung, list[str]]:
    """Resolve a *dotted* name against the set of qualified names in the model.

    Used for an attribute chain whose head did not resolve to a binding, such as
    ``service.checkout``. The chain is progressively shortened from the left until
    a prefix matches a known symbol, and the remainder is treated as a member.

    Returns the rung and the candidate symbol qualified names, so an ambiguous
    result carries the evidence a reader needs (AC3) rather than only a verdict.
    """
    if not qualified_name:
        return ResolutionRung.NONE, []

    head, _, tail = qualified_name.partition(".")
    if not tail:
        # A bare name with no binding: uniqueness decides, and the caller checks it.
        if qualified_name in model_names:
            return ResolutionRung.UNIQUE_IN_MODEL, [qualified_name]
        return ResolutionRung.NONE, []

    # Try the longest prefix that names a real symbol, so the most specific
    # interpretation wins over a shorter coincidental match.
    parts = qualified_name.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:cut])
        suffix = parts[cut:]
        if prefix in model_names:
            member = suffix[-1]
            candidate = f"{prefix}:{member}"
            if candidate in model_names:
                return ResolutionRung.ATTRIBUTE_CHAIN, [candidate]
            return ResolutionRung.NONE, []
        # Also accept a prefix that appears as a member of any known symbol, as
        # in ``PaymentService.process`` where only the member name is carried.
        matches = sorted(
            name for name in model_names if name.endswith(f":{prefix}")
        )
        if len(matches) == 1:
            member = suffix[-1]
            candidate = f"{matches[0]}:{member}"
            if candidate in model_names:
                return ResolutionRung.ATTRIBUTE_CHAIN, [candidate]
            return ResolutionRung.NONE, []
        if len(matches) > 1:
            member = suffix[-1]
            candidates = sorted(
                f"{match}:{member}"
                for match in matches
                if f"{match}:{member}" in model_names
            )
            if len(candidates) == 1:
                return ResolutionRung.ATTRIBUTE_CHAIN, candidates
            if candidates:
                return ResolutionRung.ATTRIBUTE_CHAIN_AMBIGUOUS, candidates
            return ResolutionRung.NONE, []

    return ResolutionRung.NONE, []
