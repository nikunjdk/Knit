"""Vector scoring utilities — Python mirrors of the equivalent Postgres functions."""

import numpy as np


def canonical_pair(a: str, b: str) -> tuple[str, str]:
    """Return (smaller, larger) UUID string. Mirrors the Postgres canonical_pair() function.

    Must stay in sync with the DB function — all symmetric table inserts (connections,
    icebreaker_cache, profile_similarity, event_attendee_scores) depend on this ordering.
    """
    return (a, b) if a < b else (b, a)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in [0, 1] for two 768-d embedding vectors; 0.0 for zero-norm inputs."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if norm == 0.0:
        return 0.0
    return float(np.dot(va, vb) / norm)
