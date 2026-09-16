"""Payment domain service.

The centre of the fixture's expected dependency graph: both CheckoutService and
RefundService reach PaymentService, and PaymentService reaches
PaymentRepository.
"""

from models.payment import Payment
from repositories.payment_repository import PaymentRepository


class PaymentService:
    """Validates and persists payments."""

    def __init__(self, repository: PaymentRepository) -> None:
        self.repository = repository

    def process(self, payment: Payment) -> bool:
        """Validate, then persist."""
        if not self.validate(payment):
            return False
        self.repository.save(payment)
        return True

    def validate(self, payment: Payment) -> bool:
        """A payment is valid when its amount is positive."""
        return payment.amount > 0
