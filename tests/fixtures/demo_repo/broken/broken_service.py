"""A service with deliberately broken syntax.

Section 7 requires the fixture to contain one intentionally malformed file, so
that fault isolation (section 30) is exercised by the standard fixture rather
than only by a dedicated test. The class header and the import above it are
valid; the method bodies are not. That is the interesting case: the file must be
reported degraded while the valid parts of the repository keep working.
"""

from models.payment import Payment


class BrokenService:
    """This class body does not parse cleanly."""

    def run(self, payment: Payment) -> bool
        return payment.amount > 0

    def also_broken(self:
        return False
