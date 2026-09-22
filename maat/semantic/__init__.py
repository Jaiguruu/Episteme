"""Semantic tier: resolve observed references into edges to real symbols.

Stage 6 lives in its own package rather than inside ``maat/offline/`` so the syntax
tier stays free of meaning (D30). This package depends only on ``maat/core`` -- never
on ``maat/offline`` -- which is what lets one resolver cover every extractable language
with no per-language branch.

Nothing here may know a language's shape. The resolver reads the language-neutral model
-- symbols, relationships, bindings -- and never a grammar. ``self`` is handled, but as
a linguistic fact carried in one shared vocabulary (D31), not as a Python special case.
"""

from .ladder import (
    INSTANCE_RECEIVERS,
    ResolutionRung,
    resolve_qualified_name,
)
from .resolver import Resolver, ResolutionReport, resolve_ir
from .store import (
    ModelNotPublishedError,
    ModelStore,
    PublishedVersionError,
    append_version,
)

__all__ = [
    "INSTANCE_RECEIVERS",
    "ModelNotPublishedError",
    "ModelStore",
    "PublishedVersionError",
    "append_version",
    "ResolutionReport",
    "ResolutionRung",
    "Resolver",
    "resolve_ir",
    "resolve_qualified_name",
]
