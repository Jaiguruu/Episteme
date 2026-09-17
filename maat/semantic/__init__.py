"""Resolution: turn observed references into edges to real symbols.

M2 Stage 6. Sibling of :mod:`maat.offline` rather than a module inside it, so the
syntax tier stays free of meaning (D30).

The one rule this package inherits: nothing here may know a language's shape. The
resolver reads the language-neutral model -- symbols, relationships, bindings --
and never a grammar. ``self`` is handled, but as a linguistic fact carried in one
shared vocabulary (D31), not as a Python special case.
"""

from .ladder import ResolutionRung, resolve_qualified_name
from .resolver import Resolver, ResolutionReport, resolve_ir

__all__ = [
    "ResolutionRung",
    "ResolutionReport",
    "Resolver",
    "resolve_ir",
    "resolve_qualified_name",
]
