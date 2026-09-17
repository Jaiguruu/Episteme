"""Tests for ``maat/semantic/`` — resolution, validation, the canonical model.

M2. These tests build models in memory rather than reading a fixture, because
resolution is a pure function of the model: an in-memory input keeps the tests
about the algorithm and the rungs, while the end-to-end path over the real
fixtures lives in ``tests/offline/test_pipeline.py``.
"""
