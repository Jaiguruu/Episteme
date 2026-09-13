"""Module 6 of the generated Python layer."""

from __future__ import annotations

from pkg.module5 import Service5


class Base6:
    """Base class for service 6."""


class Service6(Base6):
    """Service 6."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service5().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_6(value):
    """Module-level helper."""
    return value
