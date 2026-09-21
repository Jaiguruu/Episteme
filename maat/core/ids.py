"""Deterministic entity identity.

Design rules, and why each exists:

1. **IDs are content-addressed, never random.** No ``uuid4``, no counters, no
   ``id()``. The same symbol in the same place must hash to the same ID on a
   different machine, in a different process, on a different day. Spec
   section 12 AC1 requires "identical source produces stable entity IDs".

2. **``model_version`` is NOT part of any ID.** It is tempting to include it --
   every entity carries a version -- but doing so would give an *unchanged*
   symbol a fresh ID on every reindex, which breaks the incremental reuse that
   Stage 21 depends on. Version is an attribute of the entity, not part of its
   identity.

3. **Fields are joined with a separator that cannot appear in them.** ``\\x1f``
   (ASCII unit separator) is not legal in a POSIX path, a qualified name, or an
   enum value, so ``("a", "b|c")`` and ``("a|b", "c")`` cannot collide.

4. **The digest is truncated to 16 hex chars (64 bits).** At 64 bits, the
   birthday bound for a 1M-symbol repository is roughly 2.7e-8 -- far below the
   rate at which a resolver would produce a wrong-but-stable answer. Longer IDs
   buy nothing and make every log line and graph node unreadable.
"""

from __future__ import annotations

import hashlib
from typing import Final

#: ASCII unit separator. Illegal in paths, qualified names and enum values.
_SEP: Final[str] = "\x1f"

#: Digest length in hex characters.
_ID_LEN: Final[int] = 16

#: Prefixes. Each entity family gets one so an ID is self-describing in logs
#: and so a mismatched ID is obvious rather than silently accepted.
FILE_PREFIX: Final[str] = "file_"
SYMBOL_PREFIX: Final[str] = "sym_"
RELATIONSHIP_PREFIX: Final[str] = "rel_"
EVIDENCE_PREFIX: Final[str] = "ev_"
CHUNK_PREFIX: Final[str] = "chunk_"
BINDING_PREFIX: Final[str] = "bind_"
VERSION_PREFIX: Final[str] = "mv_"

#: Placeholder ID scheme for relationship targets that did not resolve.
UNRESOLVED_PREFIX: Final[str] = "unresolved:"

#: Identity of the *pipeline*, not of the repository (D27).
#:
#: Before M2 a version ID was a pure function of file content, which was correct while
#: the pipeline only ever observed: the same bytes always produced the same model.
#: Resolution breaks that. Stage 6 rewrites relationship targets without touching a
#: single file, so two genuinely different models -- one with every edge unresolved,
#: one with edges resolved -- would carry the *same* content hash and therefore the
#: same version ID. Incremental reuse keys off that ID, so it would happily serve the
#: unresolved model and report it as current.
#:
#: Folding this token into the digest separates them. Bump it when a change alters what
#: the pipeline *derives* from unchanged source; leave it alone when a change only
#: alters how the same facts are computed (a refactor, or a faster query with identical
#: output), because a bump invalidates every cached index.
#:
#: The value must be a source constant. Reading it from the environment, a timestamp,
#: or the installed version would make version IDs vary between identical runs and
#: break section 9 AC2.
PIPELINE_FINGERPRINT: Final[str] = "offline.stages=0-5;semantic=absent"

#: The fingerprint for a run that also executed Stage 6.
#:
#: Kept as a distinct constant rather than a mutable flag, so a version ID is always
#: reproducible from the artifact alone: the token recorded on the model says exactly
#: which pipeline produced it, and comparing two models' tokens says whether they are
#: comparable.
PIPELINE_FINGERPRINT_RESOLVED: Final[str] = "offline.stages=0-5;semantic=stages6-8"


def _digest(*parts: object) -> str:
    """Hash the parts and return the first ``_ID_LEN`` hex characters."""
    joined = _SEP.join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:_ID_LEN]


def file_id(path: str) -> str:
    """Identity of a file, from its repository-relative path alone.

    Path-only, deliberately. Hashing the content would make every edit change
    the file's identity, so a file could never be recognised as "the same file,
    changed" -- which is exactly what change detection needs to detect.
    """
    return FILE_PREFIX + _digest(path)


def symbol_id(path: str, symbol_type: str, qualified_name: str) -> str:
    """Identity of a symbol.

    ``path`` is included so two classes with the same name in different modules
    stay distinct (section 13 AC2). ``symbol_type`` is included so a class and a
    function that happen to share a qualified name do not collide.
    """
    return SYMBOL_PREFIX + _digest(path, symbol_type, qualified_name)


def relationship_id(
    source_symbol_id: str,
    relationship_type: str,
    target_key: str,
    start_line: int,
    start_col: int,
) -> str:
    """Identity of a relationship.

    The source *position* participates because one function may legitimately
    call the same target several times. Two calls to ``foo()`` on different
    lines are two distinct observations with distinct evidence, and collapsing
    them would lose the second call site's provenance.

    The column is included alongside the line because ``f(); g()`` on a single
    line is two calls at one line number; without the column they would hash
    identically and one would be silently dropped as a duplicate.
    """
    return RELATIONSHIP_PREFIX + _digest(
        source_symbol_id, relationship_type, target_key, start_line, start_col
    )


def evidence_id(
    entity_id: str,
    file_id_value: str,
    start_line: int,
    end_line: int,
    retrieval_source: str,
) -> str:
    return EVIDENCE_PREFIX + _digest(
        entity_id, file_id_value, start_line, end_line, retrieval_source
    )


def chunk_id(symbol_id_value: str, chunk_type: str) -> str:
    return CHUNK_PREFIX + _digest(symbol_id_value, chunk_type)


def binding_id(
    path: str,
    scope: str,
    bound_name: str,
    enclosing_qualified_name: str | None,
    start_line: int,
    start_col: int,
) -> str:
    """Identity of a name-to-type binding.

    The source *position* participates, for the same reason it does in
    :func:`relationship_id`: ``x = A(); x = B()`` is two genuine bindings, and
    collapsing them would move the resolver's "last write wins" decision out of
    Stage 6 and into the extractor. The enclosing qualified name participates
    because a local ``repository`` and a field ``repository`` in one method are
    different bindings that may hold different types -- see ``BindingScope``.
    """
    return BINDING_PREFIX + _digest(
        path,
        scope,
        bound_name,
        enclosing_qualified_name or "",
        start_line,
        start_col,
    )


def model_version_id(
    file_hashes_digest: str, pipeline_fingerprint: str = PIPELINE_FINGERPRINT
) -> str:
    """Identity of a model version.

    Derived from the *combined content hash of every file in the snapshot*, the
    identity of the pipeline that derived the model from them, and nothing else.
    That gives versioning a property worth having: the version is a pure function of
    repository state *and stage set*, so reindexing a repository that has not actually
    changed yields the same version ID and does not manufacture a new one. Section 9
    AC2 expects a no-change run to reparse nothing, and inventing a version for it
    would be a lie about the repository having moved.

    The fingerprint argument is D27. It defaults to the current pipeline identity, so
    callers that predate the second dimension keep working, but the pipeline threads
    it explicitly because Stage 6 must mint a *different* ID for a resolved model
    built from identical bytes.

    The parent version is deliberately *not* an input. It is recorded on
    :class:`~maat.core.contracts.ModelVersion` as lineage metadata, but making
    it part of the identity would break idempotence: the second run over an
    unchanged repository would hash a different parent and produce a different
    version every time.

    A consequence worth stating: two repositories with byte-identical content and an
    identical pipeline produce the same version ID. Version IDs are only ever
    meaningful within the index directory they were built into, so this is harmless.
    """
    return VERSION_PREFIX + _digest(file_hashes_digest, pipeline_fingerprint)


def unresolved_target_id(target_key: str) -> str:
    """A stand-in target for a relationship that did not resolve.

    Section 4.2: prefer an explicit unresolved relationship over an incorrect
    confident one. The relationship is still recorded -- with its real source
    location and evidence -- but its target is this clearly-marked placeholder,
    never a guessed symbol.
    """
    return UNRESOLVED_PREFIX + target_key


def is_unresolved_target(entity_id: str) -> bool:
    return entity_id.startswith(UNRESOLVED_PREFIX)
