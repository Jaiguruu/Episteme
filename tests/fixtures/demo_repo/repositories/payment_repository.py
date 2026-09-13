"""Persistence for payments."""

from models.payment import Payment


class PaymentRepository:
    """Stores payments."""

    def save(self, payment: Payment) -> None:
        """Persist a payment."""
        self._write(payment)

    def _write(self, payment: Payment) -> None:
        """Write to the backing store."""
        raise NotImplementedError
