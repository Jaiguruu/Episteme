"""Module 7 of the generated Python layer."""

from __future__ import annotations

from pkg.module6 import Service6


class Base7:
    """Base class for service 7."""


class Service7(Base7):
    """Service 7."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service6().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_7(value):
    """Module-level helper."""
    return value
