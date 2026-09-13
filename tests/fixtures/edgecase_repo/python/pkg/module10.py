"""Module 10 of the generated Python layer."""

from __future__ import annotations

from pkg.module9 import Service9


class Base10:
    """Base class for service 10."""


class Service10(Base10):
    """Service 10."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service9().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_10(value):
    """Module-level helper."""
    return value
