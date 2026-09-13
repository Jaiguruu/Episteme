"""Module 8 of the generated Python layer."""

from __future__ import annotations

from pkg.module7 import Service7


class Base8:
    """Base class for service 8."""


class Service8(Base8):
    """Service 8."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service7().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_8(value):
    """Module-level helper."""
    return value
