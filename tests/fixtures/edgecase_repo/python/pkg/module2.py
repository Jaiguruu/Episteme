"""Module 2 of the generated Python layer."""

from __future__ import annotations

from pkg.module1 import Service1


class Base2:
    """Base class for service 2."""


class Service2(Base2):
    """Service 2."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service1().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_2(value):
    """Module-level helper."""
    return value
