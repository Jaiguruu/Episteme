"""Module 5 of the generated Python layer."""

from __future__ import annotations

from pkg.module4 import Service4


class Base5:
    """Base class for service 5."""


class Service5(Base5):
    """Service 5."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service4().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_5(value):
    """Module-level helper."""
    return value
