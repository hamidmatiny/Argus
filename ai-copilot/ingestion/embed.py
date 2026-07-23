"""Embeddings — OpenAI-compatible HTTP or deterministic hash (CI / offline)."""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Sequence

import httpx

from agent.config import Settings

DIM = 384


def _hash_embed(text: str, dim: int = DIM) -> list[float]:
    """Deterministic pseudo-embedding for demos/CI without an embeddings API."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vals: list[float] = []
    seed = digest
    while len(vals) < dim:
        seed = hashlib.sha256(seed).digest()
        for i in range(0, len(seed), 4):
            if len(vals) >= dim:
                break
            n = struct.unpack(">I", seed[i : i + 4])[0]
            vals.append((n / 0xFFFFFFFF) * 2.0 - 1.0)
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


class Embedder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dim = DIM

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.settings.embedding_provider == "hash" or not self.settings.llm_api_key:
            return [_hash_embed(t, self.dim) for t in texts]
        return self._openai_embed(list(texts))

    def _openai_embed(self, texts: list[str]) -> list[list[float]]:
        base = (self.settings.llm_api_base or "https://api.openai.com/v1").rstrip("/")
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=60.0) as client:
            res = client.post(
                f"{base}/embeddings",
                headers=headers,
                json={"model": self.settings.embedding_model, "input": texts},
            )
            res.raise_for_status()
            data = res.json()["data"]
            data = sorted(data, key=lambda d: d["index"])
            vectors = [d["embedding"] for d in data]
            self.dim = len(vectors[0])
            return vectors
