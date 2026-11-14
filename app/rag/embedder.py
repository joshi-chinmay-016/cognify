"""Local embedding generation using Sentence Transformers.

Produces dense vector embeddings locally without any paid or external APIs.
"""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class LocalEmbedder:
    """Wrapper around SentenceTransformer for local embedding generation."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        self._dimension: int | None = None

    def _ensure_loaded(self) -> SentenceTransformer:
        """Lazy load the embedding model."""
        if self._model is None:
            logger.info("Loading local embedding model '%s'...", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            # Determine dimension
            test_emb = self._model.encode(["test"], convert_to_numpy=True)
            self._dimension = int(test_emb.shape[1])
            logger.info("Embedding model loaded. Dimension: %d", self._dimension)
        return self._model

    @property
    def dimension(self) -> int:
        """Embedding vector dimension (e.g. 384 for all-MiniLM-L6-v2)."""
        if self._dimension is None:
            self._ensure_loaded()
        return self._dimension or 384

    def embed_texts(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
        """Generate normalized float32 embeddings for a sequence of texts.

        Args:
            texts: List of text strings.
            batch_size: Batch size for encoding.

        Returns:
            np.ndarray of shape (len(texts), dimension), dtype float32.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        model = self._ensure_loaded()
        embeddings = model.encode(
            list(texts),
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,  # Normalized for cosine similarity
        )
        return embeddings.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """Generate normalized float32 embedding for a single search query."""
        model = self._ensure_loaded()
        emb = model.encode(
            [query],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return emb[0].astype(np.float32)
