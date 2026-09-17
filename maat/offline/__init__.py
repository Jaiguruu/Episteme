"""Offline knowledge plane: snapshot, parse, extract, build semantic IR.

Stage 6 (resolution) lives in the sibling package :mod:`maat.semantic` rather
than here, so this tier stays free of meaning (D30). It is reachable from this
package through ``index_repository(..., resolve=True)``, which is the intended
entry point; import ``maat.semantic`` directly only if you have a model already.
"""

from .pipeline import (
    DEFAULT_INDEX_DIRNAME,
    OfflinePipeline,
    PipelineResult,
    PipelineStats,
    index_repository,
)

__all__ = [
    "DEFAULT_INDEX_DIRNAME",
    "OfflinePipeline",
    "PipelineResult",
    "PipelineStats",
    "index_repository",
]
