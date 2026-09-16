"""Checkout orchestration."""

from models.payment import Payment
from repositories.payment_repository import PaymentRepository
from services.payment_service import PaymentService


class CheckoutService:
    """Turns a cart into a payment."""

    def __init__(self) -> None:
        self.payment_service = PaymentService(PaymentRepository())

    def checkout(self, cart) -> bool:
        """Create a payment and hand it to the payment service."""
        payment = Payment(cart.total)
        return self.payment_service.process(payment)
