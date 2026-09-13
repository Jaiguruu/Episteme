"""Refund handling.

Second caller of PaymentService, which is what makes
``find_callers(PaymentService)`` return two results rather than one.
"""

from models.payment import Payment
from repositories.payment_repository import PaymentRepository
from services.payment_service import PaymentService


class RefundService:
    """Issues refunds through the payment service."""

    def __init__(self) -> None:
        self.payment_service = PaymentService(PaymentRepository())

    def refund(self, payment: Payment) -> bool:
        """Process a refund as a negative payment."""
        return self.payment_service.process(payment)
