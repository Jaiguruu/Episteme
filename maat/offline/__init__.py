"""Offline knowledge plane: snapshot, parse, extract, build semantic IR."""

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
