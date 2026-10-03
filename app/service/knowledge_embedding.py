"""Optional, revision-pinned local embeddings; no implicit model download."""
from __future__ import annotations

import math
from pathlib import Path
from threading import Lock

MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
MODEL_CACHE = Path(__file__).resolve().parents[2] / "data" / "private" / "model-cache"


class LocalKnowledgeEmbedder:
    model_id = MODEL_ID
    revision = MODEL_REVISION

    def __init__(self):
        self._model = None
        self._lock = Lock()

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    MODEL_ID, revision=MODEL_REVISION, local_files_only=True,
                    trust_remote_code=False, device="cpu", cache_folder=str(MODEL_CACHE),
                )
            prefix = "query: " if query else "passage: "
            output = self._model.encode(
                [prefix + text for text in texts], normalize_embeddings=True,
                batch_size=16, show_progress_bar=False,
            )
            return [[float(value) for value in vector] for vector in output]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("embedding dimensions differ")
    if not all(math.isfinite(value) for value in (*left, *right)):
        raise ValueError("embedding must contain finite values")
    norm = math.sqrt(sum(value * value for value in left) * sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / norm if norm else 0.0
