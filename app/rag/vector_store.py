"""Persistent FAISS vector store module.

Provides index creation, persistence, incremental updates, synchronization,
and semantic vector similarity search.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.rag.chunker import TextChunk

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """FAISS-backed persistent vector store for document chunks."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.index: faiss.Index = faiss.IndexFlatIP(dimension)  # Cosine similarity for normalized vectors
        self.chunks: list[TextChunk] = []
        self._chunk_ids: set[str] = set()

    def __len__(self) -> int:
        return len(self.chunks)

    def add_chunks(self, chunks: list[TextChunk], embeddings: np.ndarray) -> int:
        """Add new chunks and their corresponding embeddings to the vector store.

        Deduplicates by chunk_id to avoid redundant vectors.

        Args:
            chunks: List of TextChunk objects.
            embeddings: Float32 numpy array of shape (len(chunks), dimension).

        Returns:
            Number of newly added chunks.
        """
        if len(chunks) == 0:
            return 0

        if len(chunks) != len(embeddings):
            raise ValueError(f"Mismatch between chunks count ({len(chunks)}) and embeddings ({len(embeddings)})")

        new_chunks: list[TextChunk] = []
        new_vectors: list[np.ndarray] = []

        for chunk, emb in zip(chunks, embeddings):
            if chunk.chunk_id not in self._chunk_ids:
                new_chunks.append(chunk)
                new_vectors.append(emb)
                self._chunk_ids.add(chunk.chunk_id)

        if not new_chunks:
            logger.debug("No new unique chunks to add (all already indexed).")
            return 0

        vec_array = np.vstack(new_vectors).astype(np.float32)
        # Ensure vectors are normalized for inner product cosine similarity
        faiss.normalize_L2(vec_array)

        self.index.add(vec_array)
        self.chunks.extend(new_chunks)

        logger.info("Added %d new chunks to FAISS index. Total indexed: %d", len(new_chunks), len(self.chunks))
        return len(new_chunks)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        score_threshold: float = 0.25,
    ) -> list[tuple[TextChunk, float]]:
        """Perform semantic similarity search for a query vector.

        Args:
            query_vector: Normalized 1D float32 vector of shape (dimension,).
            top_k: Maximum number of results to retrieve.
            score_threshold: Minimum cosine similarity score (between -1.0 and 1.0).

        Returns:
            List of (TextChunk, similarity_score) pairs sorted by relevance.
        """
        if len(self.chunks) == 0 or self.index.ntotal == 0:
            logger.debug("Vector store is empty, returning no results.")
            return []

        q_vec = query_vector.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(q_vec)

        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(q_vec, k)

        results: list[tuple[TextChunk, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            sim_score = float(score)
            if sim_score >= score_threshold:
                results.append((self.chunks[idx], sim_score))

        return results

    def save(self, directory: Path) -> None:
        """Persist FAISS index and metadata to directory."""
        directory.mkdir(parents=True, exist_ok=True)
        index_file = directory / "index.faiss"
        meta_file = directory / "metadata.json"

        # Write FAISS index
        faiss.write_index(self.index, str(index_file))

        # Write metadata safely using JSON
        meta_data = {
            "dimension": self.dimension,
            "count": len(self.chunks),
            "chunks": [c.to_dict() for c in self.chunks],
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=2)

        logger.info("Persisted FAISS index (%d vectors) to %s", self.index.ntotal, directory)

    def load(self, directory: Path) -> bool:
        """Load FAISS index and metadata from directory."""
        index_file = directory / "index.faiss"
        meta_file = directory / "metadata.json"

        if not index_file.exists() or not meta_file.exists():
            logger.debug("No existing FAISS index found at %s", directory)
            return False

        try:
            self.index = faiss.read_index(str(index_file))
            with open(meta_file, "r", encoding="utf-8") as f:
                raw_meta = json.load(f)

            self.dimension = raw_meta.get("dimension", self.dimension)
            self.chunks = [TextChunk.from_dict(d) for d in raw_meta.get("chunks", [])]
            self._chunk_ids = {c.chunk_id for c in self.chunks}

            if self.index.ntotal != len(self.chunks):
                logger.warning(
                    "Index count mismatch: FAISS has %d, metadata has %d. Rebuilding...",
                    self.index.ntotal,
                    len(self.chunks),
                )
                return False

            logger.info("Loaded FAISS index with %d chunks from %s", len(self.chunks), directory)
            return True
        except Exception as e:
            logger.error("Failed to load FAISS index from %s: %s", directory, e)
            return False

    def clear(self) -> None:
        """Reset index and stored chunks."""
        self.index = faiss.IndexFlatIP(self.dimension)
        self.chunks.clear()
        self._chunk_ids.clear()

