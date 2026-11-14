"""Unit tests for FAISS vector store, retrieval, and source attribution."""

from pathlib import Path
import numpy as np
import pytest

from app.rag.chunker import TextChunk
from app.rag.retriever import SemanticRetriever
from app.rag.vector_store import FAISSVectorStore


class MockEmbedder:
    """Mock embedder providing deterministic embeddings for fast unit testing."""

    def __init__(self, dimension: int = 4):
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        vectors = []
        for t in texts:
            # Deterministic vector based on content
            val = float(len(t) % 10) + 1.0
            vec = np.array([val, val * 0.5, 0.1, 0.2], dtype=np.float32)
            vectors.append(vec / np.linalg.norm(vec))
        return np.vstack(vectors)

    def embed_query(self, query: str) -> np.ndarray:
        val = float(len(query) % 10) + 1.0
        vec = np.array([val, val * 0.5, 0.1, 0.2], dtype=np.float32)
        return (vec / np.linalg.norm(vec)).astype(np.float32)


def test_faiss_vector_store_add_and_deduplicate():
    """Test FAISS store adds chunks and prevents duplicate chunk IDs."""
    store = FAISSVectorStore(dimension=4)

    chunk1 = TextChunk(chunk_id="c1", content="Hello world", source="doc1.docx", metadata={"filename": "doc1.docx"})
    chunk2 = TextChunk(chunk_id="c2", content="Second text", source="doc2.docx", metadata={"filename": "doc2.docx"})
    embeddings = np.array([[1.0, 0, 0, 0], [0, 1.0, 0, 0]], dtype=np.float32)

    added = store.add_chunks([chunk1, chunk2], embeddings)
    assert added == 2
    assert len(store) == 2

    # Attempt re-adding chunk1 (duplicate) and chunk3 (new)
    chunk3 = TextChunk(chunk_id="c3", content="Third text", source="doc3.docx", metadata={"filename": "doc3.docx"})
    embeddings2 = np.array([[1.0, 0, 0, 0], [0, 0, 1.0, 0]], dtype=np.float32)
    added_second = store.add_chunks([chunk1, chunk3], embeddings2)

    assert added_second == 1  # Only chunk3 was added
    assert len(store) == 3


def test_faiss_persistence(tmp_path: Path):
    """Test saving and loading vector store index and metadata from disk."""
    store = FAISSVectorStore(dimension=4)
    chunk = TextChunk(chunk_id="c1", content="Policy details", source="policy.docx", metadata={"filename": "policy.docx"})
    emb = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    store.add_chunks([chunk], emb)

    # Save
    store.save(tmp_path)
    assert (tmp_path / "index.faiss").exists()
    assert (tmp_path / "metadata.json").exists()

    # Load into a fresh store
    new_store = FAISSVectorStore(dimension=4)
    loaded = new_store.load(tmp_path)
    assert loaded is True
    assert len(new_store) == 1
    assert new_store.chunks[0].chunk_id == "c1"
    assert new_store.chunks[0].source == "policy.docx"


def test_semantic_retriever_source_attribution():
    """Test semantic retrieval correctly attributes sources and extracts context."""
    store = FAISSVectorStore(dimension=4)
    chunk1 = TextChunk(chunk_id="c1", content="Vacation policy text", source="handbook.docx", metadata={"filename": "handbook.docx"})
    chunk2 = TextChunk(chunk_id="c2", content="Medical benefits text", source="benefits.docx", metadata={"filename": "benefits.docx"})

    emb1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    emb2 = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
    store.add_chunks([chunk1, chunk2], np.vstack([emb1, emb2]))

    mock_embedder = MockEmbedder(dimension=4)
    # Query aligned with chunk1
    mock_embedder.embed_query = lambda q: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    retriever = SemanticRetriever(vector_store=store, embedder=mock_embedder, top_k=2, score_threshold=0.1)
    result = retriever.retrieve("vacation policy")

    assert result.has_context
    assert "handbook.docx" in result.sources
    assert len(result.chunks) >= 1
    assert "Vacation policy text" in result.formatted_context

