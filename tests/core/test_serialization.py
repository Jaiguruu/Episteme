"""``maat/core/serialization.py`` — canonical JSON, atomic writes, hash combining.

This module exists so that byte-identical output is the path of least resistance.
Determinism is a tested property here rather than an aspiration, and
``combine_hashes`` is the sharpest case: it derives every model version ID and had
zero references anywhere in ``tests/`` before this module existed.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from maat.core.contracts import SemanticIR, Symbol
from maat.core.enums import ParseStatus, SymbolType
from maat.core.locations import SourceSpan
from maat.core.serialization import (
    canonical_json,
    combine_hashes,
    model_digest,
    read_json,
    write_json,
)


class _WithToDict:
    def to_dict(self) -> dict[str, int]:
        return {"n": 1}


class _Opaque:
    """Neither an enum nor a to_dict object: must be loud, not stringified."""

    def __repr__(self) -> str:  # pragma: no cover - only used in failure output
        return "<opaque>"


class CanonicalJsonTests(unittest.TestCase):
    def test_keys_are_sorted(self) -> None:
        """Dict insertion order must never leak into the output."""
        self.assertEqual(
            canonical_json({"b": 1, "a": 2}),
            canonical_json({"a": 2, "b": 1}),
        )
        text = canonical_json({"b": 1, "a": 2})
        self.assertLess(text.index('"a"'), text.index('"b"'))

    def test_key_value_separator_is_colon_space(self) -> None:
        self.assertIn('"a": 2', canonical_json({"a": 2}))

    def test_unicode_is_preserved_not_escaped(self) -> None:
        """``ensure_ascii=False`` so unicode identifiers round-trip readably."""
        text = canonical_json({"name": "Données"})
        self.assertIn("Données", text)
        self.assertNotIn("\\u", text)

    def test_enums_serialise_to_their_bare_value(self) -> None:
        self.assertEqual(canonical_json(ParseStatus.OK), '"OK"')
        self.assertEqual(canonical_json(SymbolType.METHOD), '"METHOD"')

    def test_objects_with_to_dict_are_serialised(self) -> None:
        self.assertEqual(json.loads(canonical_json(_WithToDict())), {"n": 1})

    def test_an_unserialisable_object_is_loud(self) -> None:
        """Silently stringifying an unknown object would corrupt the model."""
        with self.assertRaises(TypeError):
            canonical_json({"bad": _Opaque()})

    def test_a_set_is_rejected_rather_than_ordered_arbitrarily(self) -> None:
        with self.assertRaises(TypeError):
            canonical_json({"items": {1, 2, 3}})

    def test_empty_containers_serialise_compactly(self) -> None:
        self.assertEqual(canonical_json([]), "[]")
        self.assertEqual(canonical_json({}), "{}")

    def test_output_is_reproducible(self) -> None:
        payload = {"z": [1, {"b": 2, "a": 3}], "a": "é"}
        self.assertEqual(canonical_json(payload), canonical_json(payload))


class CombineHashesTests(unittest.TestCase):
    """The digest behind every ``model_version_id``."""

    def test_order_does_not_matter(self) -> None:
        """Discovery order must not influence the version.

        This is the entire reason the function sorts before hashing: ``os.walk``
        order is not part of the repository's identity.
        """
        self.assertEqual(
            combine_hashes(["sha256:a", "sha256:b", "sha256:c"]),
            combine_hashes(["sha256:c", "sha256:a", "sha256:b"]),
        )

    def test_duplicates_still_affect_the_result(self) -> None:
        """Sorting must not deduplicate; two files with equal content are two files."""
        self.assertNotEqual(
            combine_hashes(["sha256:a", "sha256:b"]),
            combine_hashes(["sha256:a", "sha256:a", "sha256:b"]),
        )

    def test_content_change_changes_the_digest(self) -> None:
        self.assertNotEqual(
            combine_hashes(["sha256:a", "sha256:b"]),
            combine_hashes(["sha256:a", "sha256:c"]),
        )

    def test_empty_input_is_stable_and_non_empty(self) -> None:
        digest = combine_hashes([])
        self.assertEqual(digest, combine_hashes([]))
        self.assertEqual(len(digest), 64)

    def test_result_is_a_hex_digest(self) -> None:
        digest = combine_hashes(["sha256:a"])
        int(digest, 16)
        self.assertEqual(digest, digest.lower())


class ModelDigestTests(unittest.TestCase):
    def _ir(self, version: str = "mv_1") -> SemanticIR:
        return SemanticIR(model_version=version)

    def _with_symbol(self, version: str = "mv_1") -> SemanticIR:
        ir = self._ir(version)
        ir.symbols.append(
            Symbol(
                id="sym_1",
                file_id="file_1",
                name="Thing",
                qualified_name="mod:Thing",
                symbol_type=SymbolType.CLASS,
                signature=None,
                location=SourceSpan(1, 0, 1, 10),
                documentation=None,
                content_hash="sha256:x",
                model_version=version,
            )
        )
        return ir

    def test_digest_is_reproducible(self) -> None:
        self.assertEqual(model_digest(self._ir()), model_digest(self._ir()))

    def test_digest_changes_when_content_changes(self) -> None:
        self.assertNotEqual(
            model_digest(self._ir()), model_digest(self._with_symbol())
        )

    def test_digest_changes_with_the_model_version(self) -> None:
        self.assertNotEqual(model_digest(self._ir("mv_1")), model_digest(self._ir("mv_2")))

    def test_digest_ignores_the_derived_counts_block(self) -> None:
        """``counts`` is derived from the collections, so it must not be hashed.

        Hashing it would mean a model and its own re-derivation could disagree,
        and ``counts`` is recomputed on every ``to_dict()`` call.
        """
        ir = self._with_symbol()
        payload = ir.to_dict()
        self.assertIn("counts", payload)
        without_counts = {k: v for k, v in payload.items() if k != "counts"}
        self.assertEqual(
            model_digest(ir),
            hashlib.sha256(canonical_json(without_counts).encode("utf-8")).hexdigest(),
        )


class JsonIoTests(unittest.TestCase):
    def test_write_then_read_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ir.json"
            payload = {"model_version": "mv_1", "name": "Données", "n": 2}
            write_json(target, payload)
            self.assertEqual(read_json(target), payload)

    def test_missing_parent_directories_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "deeper" / "ir.json"
            write_json(target, {"a": 1})
            self.assertTrue(target.is_file())

    def test_output_uses_lf_line_endings(self) -> None:
        """CRLF would change the bytes, and the bytes are what get hashed."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "x.json"
            write_json(target, {"a": 1, "b": 2})
            self.assertNotIn(b"\r\n", target.read_bytes())

    def test_write_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ir.json"
            write_json(target, {"a": 1})
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name.startswith(".tmp-")]
            self.assertEqual(leftovers, [])

    def test_a_failed_serialisation_leaves_the_previous_file_intact(self) -> None:
        """Section 9 AC6 — an interrupted or failed write must not corrupt state."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ir.json"
            write_json(target, {"good": True})

            with self.assertRaises(TypeError):
                write_json(target, {"bad": _Opaque()})

            self.assertEqual(read_json(target), {"good": True})
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name.startswith(".tmp-")]
            self.assertEqual(leftovers, [])

    def test_overwriting_replaces_rather_than_appends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ir.json"
            write_json(target, {"a": 1, "b": 2, "c": 3})
            write_json(target, {"a": 1})
            self.assertEqual(read_json(target), {"a": 1})


if __name__ == "__main__":
    unittest.main()
