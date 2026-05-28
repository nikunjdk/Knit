import numpy as np


def canonical_pair(a: str, b: str) -> tuple[str, str]:
    """Return (smaller, larger) UUID string. Mirrors the Postgres canonical_pair() function."""
    return (a, b) if a < b else (b, a)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if norm == 0.0:
        return 0.0
    return float(np.dot(va, vb) / norm)
