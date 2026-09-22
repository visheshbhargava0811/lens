"""Embedding tier (config/models.yaml `embedding`): BGE-M3 dense + sparse (+ optional ColBERT)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import numpy as np

from lens.core.config_files import load_yaml


@dataclass
class Encoded:
    dense: np.ndarray  # (n, dim) float32, L2-normalized
    sparse: list[dict[int, float]]  # token id -> weight
    colbert: list[np.ndarray] | None  # per text (tokens, dim), only when requested


class Embedder(Protocol):
    name: str
    dim: int

    def encode(self, texts: list[str], *, sparse: bool = True, colbert: bool = False) -> Encoded: ...


class BGEM3Embedder:
    """BAAI/bge-m3 through FlagEmbedding. Loaded lazily; needs the `ml` extra."""

    def __init__(self, model: str, device: str | None = None, batch_size: int = 32, max_length: int = 512) -> None:
        import os

        os.environ.setdefault("TQDM_DISABLE", "1")  # FlagEmbedding prints a progress bar per batch
        from FlagEmbedding import BGEM3FlagModel  # heavy import, only when used

        self.name, self.dim = model, 1024
        self.batch_size, self.max_length = batch_size, max_length
        self._m = BGEM3FlagModel(model, use_fp16=False, devices=device or _best_device())

    def encode(self, texts: list[str], *, sparse: bool = True, colbert: bool = False) -> Encoded:
        if not texts:
            return Encoded(np.zeros((0, self.dim), np.float32), [], [] if colbert else None)
        out: dict[str, Any] = self._m.encode(
            texts,
            batch_size=self.batch_size,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=sparse,
            return_colbert_vecs=colbert,
        )
        dense = np.asarray(out["dense_vecs"], dtype=np.float32)
        dense /= np.linalg.norm(dense, axis=1, keepdims=True).clip(min=1e-12)
        lex = [{int(k): float(v) for k, v in w.items()} for w in out["lexical_weights"]] if sparse else []
        cb = [np.asarray(c, dtype=np.float32) for c in out["colbert_vecs"]] if colbert else None
        return Encoded(dense, lex, cb)


class HashEmbedder:
    """Deterministic stand-in for tests: bag of hashed word features, L2-normalized. No model download."""

    name, dim = "hash-test", 256

    def encode(self, texts: list[str], *, sparse: bool = True, colbert: bool = False) -> Encoded:
        from lens.nlp.textkeys import _tokens

        dense = np.zeros((len(texts), self.dim), np.float32)
        lex: list[dict[int, float]] = []
        for i, t in enumerate(texts):
            weights: dict[int, float] = {}
            for tok in _tokens(t):
                h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=4).digest(), "big")
                dense[i, h % self.dim] += 1.0
                weights[h] = weights.get(h, 0.0) + 1.0
            lex.append(weights)
        dense /= np.linalg.norm(dense, axis=1, keepdims=True).clip(min=1e-12)
        return Encoded(dense, lex if sparse else [], [dense[i : i + 1] for i in range(len(texts))] if colbert else None)


def _best_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache
def get_embedder() -> Embedder:
    tier = load_yaml("models.yaml")["tiers"]["embedding"]
    if tier.get("provider") == "local" and tier.get("model") == "BAAI/bge-m3":
        return BGEM3Embedder(tier["model"], tier.get("device"))
    if tier.get("provider") == "test":
        return HashEmbedder()
    raise ValueError(f"unsupported embedding tier: {tier}")


def article_text(title: str, snippet: str | None) -> str:
    """Text for the clustering vector: the article's own words only, no outlet or date prefix,
    so articles from the same outlet are not pulled together (ADR-0016)."""
    return f"{title}\n{snippet}" if snippet else title


def chunk_embed_text(outlet: str, date: str, headline: str, chunk: str) -> str:
    """Retrieval text for a chunk (docs/03): prefix is embedded, never stored."""
    return f"{outlet} | {date} | {headline}\n{chunk}"
