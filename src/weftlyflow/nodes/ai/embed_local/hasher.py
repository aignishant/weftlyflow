"""Deterministic hashing embedder used by the ``embed_local`` node.

The algorithm is a *feature-hashing* bag-of-words: lowercase the input,
tokenise on non-alphanumeric runs, hash each token to a bucket in
``[0, dimensions)`` using BLAKE2b, and increment (or decrement,
depending on a sign hash) the corresponding coordinate. The result
vector is optionally L2-normalised so cosine similarity behaves the
same as for learned embeddings.

This is *not* a semantic embedder - "bank" (river) and "bank"
(finance) collide - but it is:

* deterministic across processes / Python runs (cryptographic hash,
  no ``hash()`` randomisation),
* dependency-free,
* fast enough to test a full RAG pipeline without an API key.

Pairs with :mod:`weftlyflow.nodes.ai.text_splitter` and
:mod:`weftlyflow.nodes.ai.vector_memory` to demo retrieval end-to-end
without contacting OpenAI or any other provider.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final

_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
_HASH_BYTES: Final[int] = 8  # 64 bits of bucket/sign entropy per token
_SIGN_BIT_MASK: Final[int] = 1 << 63


def embed(
    text: str,
    *,
    dimensions: int,
    normalize: bool = True,
) -> list[float]:
    """Return a ``dimensions``-length feature vector for ``text``.

    Args:
        text: Input text. Non-alphanumerics become token boundaries.
        dimensions: Vector length. Must be > 0.
        normalize: When ``True``, return a unit vector so cosine and
            dot-product metrics agree. When ``False``, coordinates are
            raw signed counts - useful if you want length to carry
            document-size signal.

    Returns:
        A list of length ``dimensions``. Empty input yields a zero
        vector.

    Raises:
        ValueError: if ``dimensions`` is not strictly positive.
    """
    if dimensions <= 0:
        msg = f"dimensions must be > 0, got {dimensions}"
        raise ValueError(msg)
    vector = [0.0] * dimensions
    for token in _tokenise(text):
        bucket, sign = _bucket_and_sign(token, dimensions)
        vector[bucket] += sign
    if not normalize:
        return vector
    return _l2_normalise(vector)


def _tokenise(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _bucket_and_sign(token: str, dimensions: int) -> tuple[int, int]:
    """Hash ``token`` to ``(bucket, sign)`` in ``[0, dims) x {-1, +1}``.

    Uses BLAKE2b truncated to 8 bytes (64 bits). The high bit picks
    the sign; the remaining 63 bits index the bucket. The sign hash
    cancels collisions on average, which keeps hashed vectors close
    to their unhashed counterparts in expectation.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=_HASH_BYTES).digest()
    value = int.from_bytes(digest, "big")
    sign = 1 if value & _SIGN_BIT_MASK else -1
    bucket = (value & ~_SIGN_BIT_MASK) % dimensions
    return bucket, sign


def _l2_normalise(vector: list[float]) -> list[float]:
    norm_sq = sum(x * x for x in vector)
    if norm_sq == 0.0:
        return vector
    inv_norm = 1.0 / (norm_sq ** 0.5)
    return [x * inv_norm for x in vector]
