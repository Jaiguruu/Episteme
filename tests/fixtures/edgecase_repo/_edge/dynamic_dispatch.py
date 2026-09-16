"""Calls that cannot be resolved statically."""

import importlib


def dispatch(name, *args):
    """Resolve a callable at runtime."""
    module = importlib.import_module(name)
    handler = getattr(module, 'handle')
    return handler(*args)


def chained(obj):
    return obj.first().second().third()
