"""Canonical serialisation.

Determinism is a testable property (section 8 AC5, section 12 AC1), and JSON is
where it is easiest to lose. Everything here exists to make byte-identical
output the path of least resistance:

* keys sorted, so dict insertion order never leaks into the output
* separators fixed, so no incidental whitespace differences
* ``ensure_ascii=False`` with explicit UTF-8 encoding, so unicode identifiers
  round-trip instead of being escaped differently on different runs
* no timestamps, no ``repr`` of objects, no sets anywhere in the output
* writes go to a temporary file and are then renamed over the target, so an
  interrupted run can never leave a half-written manifest behind
  (section 9 AC6)

The one deliberate exception is ``ModelVersion.created_at``, which is metadata
*about* a build rather than part of the model. It is excluded from equality
comparisons via :func:`model_digest`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .contracts import SemanticIR


def canonical_json(payload: Any) -> str:
    """Serialise to deterministic JSON text."""
    return json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        separators=(",", ": "),
        default=_json_default,
    )


def _json_default(value: Any) -> Any:
    """Fallback for objects that are not natively JSON serialisable.

    Enums are the only expected case; ``str()`` on our ``_StrEnum`` returns the
    bare value. Anything else is a programming error and should be loud rather
    than silently stringified into the model.
    """
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return str(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"cannot serialise {type(value).__name__} to canonical JSON")


def write_json(path: str | Path, payload: Any) -> None:
    """Write ``payload`` atomically as canonical JSON.

    Atomic because section 9 AC6 and section 19 AC2 both require that an
    interrupted or failed run leaves the previous good state untouched. A
    partial write is impossible: the reader sees either the old file or the
    complete new one.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_json(payload)
    handle, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=".tmp-", suffix=".json"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        # Never leave a stray temp file behind on failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def model_digest(ir: SemanticIR) -> str:
    """Content digest of a semantic model, ignoring build metadata.

    Used by the determinism test: two runs over an unchanged repository must
    produce the same digest even though ``created_at`` differs.
    """
    payload = ir.to_dict()
    payload.pop("counts", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def combine_hashes(hashes: list[str]) -> str:
    """Order-independent digest of a set of file content hashes.

    Sorted before hashing so that discovery order cannot influence the result,
    which is what lets an unchanged repository hash to an unchanged model
    version (see :func:`maat.core.ids.model_version_id`).
    """
    joined = "\n".join(sorted(hashes))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
