"""Stage 2 — incremental change detection (spec section 9).

Compares the current snapshot against the persisted manifest and classifies
every path as new, changed, deleted or unchanged.

Two design points worth stating:

**Renames are detected by content hash, not by similarity.** A rename is
claimed only when a deleted path and a new path have byte-identical content. A
similarity heuristic would occasionally pair two unrelated files and silently
mislabel a deletion plus an addition as a move, which is worse than missing the
rename. The pairing is one-to-one and resolved in sorted order, so the result is
deterministic even when several files share a hash.

**A missing or corrupt manifest is not an error.** It means "we have never
indexed this repository", so every file is new. Section 9 AC1 expects exactly
that: no previous manifest, 100 files, 100 files scheduled. Crashing instead
would make first-run indexing impossible to recover from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.contracts import ChangeSet, RepositorySnapshot


def load_manifest(path: str | Path) -> dict[str, str] | None:
    """Read a persisted manifest into ``{path: content_hash}``.

    Returns ``None`` for a missing, unreadable or malformed manifest. The caller
    treats that as an initial index rather than a failure.
    """
    payload = _read_manifest_payload(path)
    if payload is None:
        return None

    entries = payload.get("entries")
    if not isinstance(entries, list):
        return None

    manifest: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, dict) and "path" in entry and "content_hash" in entry:
            manifest[str(entry["path"])] = str(entry["content_hash"])
    return manifest


def manifest_version(path: str | Path) -> str | None:
    """Read just the model version recorded in a manifest, if any."""
    payload = _read_manifest_payload(path)
    if payload is None:
        return None
    version = payload.get("model_version")
    return str(version) if version else None


def _read_manifest_payload(path: str | Path) -> dict[str, Any] | None:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, ValueError):
        # A truncated manifest from an interrupted run lands here. Treating it
        # as absent means the next run reindexes from scratch, which is the
        # safe direction to fail (section 9 AC6, section 34 "Failed indexing").
        return None
    return payload if isinstance(payload, dict) else None


def _detect_renames(
    deleted_paths: list[str],
    new_paths: list[str],
    deleted_hashes: dict[str, str],
    current_hashes: dict[str, str],
) -> list[tuple[str, str]]:
    """Pair deleted paths with new paths holding byte-identical content.

    One-to-one: once a new path is claimed it is unavailable to another deleted
    path. Both sides are iterated in sorted order, so the pairing is a pure
    function of the input and never depends on discovery order.
    """
    available_by_hash: dict[str, list[str]] = {}
    for path in sorted(new_paths):
        digest = current_hashes.get(path)
        if digest:
            available_by_hash.setdefault(digest, []).append(path)

    pairs: list[tuple[str, str]] = []
    for old_path in sorted(deleted_paths):
        digest = deleted_hashes.get(old_path)
        if not digest:
            continue
        candidates = available_by_hash.get(digest)
        if candidates:
            pairs.append((old_path, candidates.pop(0)))
    return pairs


def diff_snapshot(
    previous: dict[str, str] | None,
    current: RepositorySnapshot,
    previous_version: str | None = None,
) -> ChangeSet:
    """Classify every path in ``current`` relative to ``previous``.

    ``previous`` maps path -> content hash. ``None`` means "no previous
    manifest", which makes every file new.
    """
    current_hashes = {record.path: record.content_hash for record in current.files}

    if previous is None:
        return ChangeSet(
            previous_version=None,
            current_version=current.model_version,
            new=sorted(current_hashes),
            changed=[],
            deleted=[],
            unchanged=[],
            renamed=[],
        )

    previous_paths = set(previous)
    current_paths = set(current_hashes)

    new_paths = sorted(current_paths - previous_paths)
    deleted_paths = sorted(previous_paths - current_paths)
    common = sorted(current_paths & previous_paths)

    changed = [p for p in common if previous.get(p) != current_hashes.get(p)]
    unchanged = [p for p in common if previous.get(p) == current_hashes.get(p)]

    deleted_hashes = {p: previous[p] for p in deleted_paths if previous.get(p)}
    renamed = _detect_renames(
        deleted_paths, new_paths, deleted_hashes, current_hashes
    )

    renamed_old = {old for old, _ in renamed}
    renamed_new = {new for _, new in renamed}

    return ChangeSet(
        previous_version=previous_version,
        current_version=current.model_version,
        new=[p for p in new_paths if p not in renamed_new],
        changed=changed,
        deleted=[p for p in deleted_paths if p not in renamed_old],
        unchanged=unchanged,
        renamed=renamed,
    )
