"""Module 11 of the generated Python layer."""

from __future__ import annotations

from pkg.module10 import Service10


class Base11:
    """Base class for service 11."""


class Service11(Base11):
    """Service 11."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service10().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_11(value):
    """Module-level helper."""
    return value
