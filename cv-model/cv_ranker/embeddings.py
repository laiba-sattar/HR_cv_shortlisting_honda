"""
Embedding backends for semantic matching.

This is where "ReactJS == React" comes from. The understanding is inherited
from a pre-trained model, not learned from Honda's data — so the model choice
here matters more than any amount of fine-tuning would.
"""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache

import numpy as np

from .config import settings

log = logging.getLogger(__name__)


class BaseEmbedder:
    name = "base"
    is_real = True

    def encode(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError


class SentenceTransformerEmbedder(BaseEmbedder):
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        log.info("Loading embedding model %s (first run downloads it)", model_name)
        self._model = SentenceTransformer(model_name, trust_remote_code=True)
        self.name = model_name

    def encode(self, texts):
        return self._model.encode(
            texts,
            batch_size=settings.embed_batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self, model_name: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.llm_api_key or None)
        self.name = model_name

    def encode(self, texts):
        resp = self._client.embeddings.create(model=self.name, input=texts)
        vecs = np.array([d.embedding for d in resp.data], dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.clip(norms, 1e-9, None)


class HashEmbedder(BaseEmbedder):
    """Deterministic offline stand-in.

    Character-trigram hashing. It gives non-zero similarity for strings that
    share substrings ("React"/"ReactJS") which is enough to exercise the
    pipeline offline, but it has NO semantic understanding: "customer support"
    and "client relations" score ~0. Never use for a real ranking — the
    pipeline logs a warning when this is active.
    """

    name = "hash-trigram (NOT semantic)"
    is_real = False
    DIM = 512

    def _one(self, text: str) -> np.ndarray:
        v = np.zeros(self.DIM, dtype=np.float32)
        t = f"  {text.lower().strip()}  "
        for i in range(len(t) - 2):
            tri = t[i:i + 3]
            idx = int(hashlib.md5(tri.encode()).hexdigest(), 16) % self.DIM
            v[idx] += 1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode(self, texts):
        return np.vstack([self._one(t) for t in texts])


@lru_cache(maxsize=1)
def get_embedder() -> BaseEmbedder:
    provider = settings.embed_provider
    if provider == "sentence_transformers":
        return SentenceTransformerEmbedder(settings.embed_model)
    if provider == "openai":
        return OpenAIEmbedder(settings.embed_model)
    if provider == "hash":
        log.warning(
            "EMBED_PROVIDER=hash is a structural stand-in with no semantic "
            "understanding. Rankings produced with it are meaningless."
        )
        return HashEmbedder()
    raise ValueError(f"Unknown EMBED_PROVIDER {provider!r}")


def cosine_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity. Inputs are already L2-normalised."""
    if a.ndim == 1:
        a = a[None, :]
    if b.ndim == 1:
        b = b[None, :]
    return a @ b.T


def embed_texts(texts: list[str]) -> np.ndarray:
    """Encode, with empty strings mapped to zero vectors (similarity 0)."""
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)
    embedder = get_embedder()
    cleaned = [t if t and t.strip() else " " for t in texts]
    vecs = embedder.encode(cleaned)
    for i, t in enumerate(texts):
        if not t or not t.strip():
            vecs[i] = 0.0
    return vecs
