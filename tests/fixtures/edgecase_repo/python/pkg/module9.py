"""Module 9 of the generated Python layer."""

from __future__ import annotations

from pkg.module8 import Service8


class Base9:
    """Base class for service 9."""


class Service9(Base9):
    """Service 9."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service8().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_9(value):
    """Module-level helper."""
    return value
