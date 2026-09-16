"""Module 1 of the generated Python layer."""

from __future__ import annotations

from pkg.module0 import Service0


class Base1:
    """Base class for service 1."""


class Service1(Base1):
    """Service 1."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service0().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_1(value):
    """Module-level helper."""
    return value
