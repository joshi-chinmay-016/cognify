"""Unit tests for DocumentChunker."""

import pytest

from app.ingestion.document_loader import TextDocumentForRAG
from app.rag.chunker import DocumentChunker


def test_chunker_splits_and_preserves_metadata():
    """Test chunker splits text while preserving source metadata and chunk index."""
    chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
    long_text = "This is a detailed sentence. " * 20

    metadata = {"filename": "handbook.docx", "file_id": "doc_123", "file_type": "docx"}
    chunks = chunker.split_text(long_text, base_metadata=metadata)

    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.source == "handbook.docx"
        assert chunk.metadata["filename"] == "handbook.docx"
        assert chunk.metadata["chunk_index"] == i
        assert len(chunk.content) <= 120  # Roughly within chunk_size


def test_chunker_handles_empty_text():
    """Test chunker returns empty list for empty or whitespace text."""
    chunker = DocumentChunker()
    assert chunker.split_text("") == []
    assert chunker.split_text("   \n\n  ") == []


def test_chunker_split_documents():
    """Test chunking multiple documents in batch."""
    chunker = DocumentChunker(chunk_size=150, chunk_overlap=20)
    docs = [
        TextDocumentForRAG(content="Doc 1 content. " * 10, metadata={"source": "doc1.docx"}),
        TextDocumentForRAG(content="Doc 2 content. " * 10, metadata={"source": "doc2.docx"}),
    ]
    all_chunks = chunker.split_documents(docs)
    sources = {c.source for c in all_chunks}
    assert "doc1.docx" in sources
    assert "doc2.docx" in sources
