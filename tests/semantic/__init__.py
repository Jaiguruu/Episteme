"""Tests for ``maat/semantic/`` -- the resolution tier.

Resolution reads only the language-neutral model -- symbols, relationships and
bindings -- never a grammar and never the filesystem, so these tests build models in
memory and need no fixture repository.
"""
