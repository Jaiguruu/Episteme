"""Module 3 of the generated Python layer."""

from __future__ import annotations

from pkg.module2 import Service2


class Base3:
    """Base class for service 3."""


class Service3(Base3):
    """Service 3."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service2().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_3(value):
    """Module-level helper."""
    return value
