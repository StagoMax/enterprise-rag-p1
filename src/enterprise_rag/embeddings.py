import hashlib
import re
from collections.abc import Sequence
from typing import Protocol

import numpy as np


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...


class Reranker(Protocol):
    def score(self, query: str, documents: Sequence[str]) -> np.ndarray: ...


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


class HashingEmbeddingProvider:
    """Deterministic local backend for tests and the no-model bootstrap path."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.findall(r"[a-z0-9_-]+|[\u4e00-\u9fff]", text.lower())

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        output = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in self._tokens(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                value = int.from_bytes(digest, "little")
                index = value % self.dimensions
                sign = 1.0 if value & 1 else -1.0
                output[row, index] += sign
        return _l2_normalize(output)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts)


class NemotronEmbeddingProvider:
    """Lazy Sentence Transformers adapter for NVIDIA Nemotron 3 Embed."""

    def __init__(
        self,
        model_id: str,
        dimensions: int = 1024,
        device: str = "cuda",
        batch_size: int = 8,
    ) -> None:
        if dimensions not in {512, 1024, 2048}:
            raise ValueError("Nemotron 3 Embed 1B supports 512, 1024, or 2048 dimensions")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Nemotron backend requires the 'models' extra: uv sync --extra models"
            ) from exc

        self.dimensions = dimensions
        self._batch_size = batch_size
        self._model = SentenceTransformer(model_id, device=device)
        self._model.max_seq_length = 32768

    def _embed(self, texts: Sequence[str], prefix: str) -> np.ndarray:
        vectors = self._model.encode(
            [f"{prefix}: {text}" for text in texts],
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 32,
        ).astype(np.float32)
        vectors = vectors[:, : self.dimensions]
        return _l2_normalize(vectors)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts, "query")

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts, "passage")


class BgeM3EmbeddingProvider:
    """BGE-M3 comparison adapter used by the P1 model benchmark."""

    dimensions = 1024

    def __init__(self, model_id: str = "BAAI/bge-m3", device: str = "cuda") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "BGE backend requires the 'models' extra: uv sync --extra models"
            ) from exc
        self._model = SentenceTransformer(model_id, device=device)
        self._model.max_seq_length = 8192

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        return self._model.encode(
            list(texts),
            batch_size=16,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 32,
        ).astype(np.float32)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts)


class CrossEncoderReranker:
    def __init__(self, model_id: str, device: str = "cuda") -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "Cross-encoder reranking requires the 'models' extra: uv sync --extra models"
            ) from exc
        self._model = CrossEncoder(model_id, device=device, max_length=512)

    def score(self, query: str, documents: Sequence[str]) -> np.ndarray:
        if not documents:
            return np.empty(0, dtype=np.float32)
        pairs = [(query, document) for document in documents]
        return np.asarray(
            self._model.predict(pairs, batch_size=32, show_progress_bar=False),
            dtype=np.float32,
        ).reshape(-1)
