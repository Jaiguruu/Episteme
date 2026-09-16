"""Module 4 of the generated Python layer."""

from __future__ import annotations

from pkg.module3 import Service3


class Base4:
    """Base class for service 4."""


class Service4(Base4):
    """Service 4."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service3().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_4(value):
    """Module-level helper."""
    return value
