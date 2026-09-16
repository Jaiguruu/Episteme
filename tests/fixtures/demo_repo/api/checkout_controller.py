"""HTTP entry point for checkout."""

from services.checkout_service import CheckoutService


class CheckoutController:
    """Handles the checkout request."""

    def handle(self, request) -> bool:
        """Delegate the request to the checkout service."""
        service = CheckoutService()
        return service.checkout(request.cart)
