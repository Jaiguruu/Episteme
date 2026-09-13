"""Module 12 of the generated Python layer."""

from __future__ import annotations

from pkg.module11 import Service11


class Base12:
    """Base class for service 12."""


class Service12(Base12):
    """Service 12."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service11().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_12(value):
    """Module-level helper."""
    return value
