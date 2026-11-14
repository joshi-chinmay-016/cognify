"""Text chunking module using RecursiveCharacterTextSplitter.

Segments documents into semantically coherent chunks while preserving
source attribution and hierarchy metadata.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.document_loader import TextDocumentForRAG

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """Represents an atomic text chunk prepared for embedding and retrieval."""

    chunk_id: str
    content: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "source": self.source,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TextChunk:
        return cls(
            chunk_id=data["chunk_id"],
            content=data["content"],
            source=data["source"],
            metadata=data.get("metadata", {}),
        )


class DocumentChunker:
    """Chunking engine using configurable recursive character splitting."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
            keep_separator=True,
        )

    def split_text(self, text: str, base_metadata: dict[str, Any] | None = None) -> list[TextChunk]:
        """Split a raw text string into chunks, attaching preserved metadata."""
        if not text or not text.strip():
            return []

        meta = dict(base_metadata or {})
        source = meta.get("source") or meta.get("filename") or "unknown"
        file_id = meta.get("file_id") or source

        raw_chunks = self.splitter.split_text(text)
        chunks: list[TextChunk] = []

        for idx, chunk_text in enumerate(raw_chunks):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue

            # Deterministic chunk ID
            hash_id = hashlib.sha256(f"{file_id}_{idx}_{chunk_text[:30]}".encode("utf-8")).hexdigest()[:16]
            chunk_id = f"{file_id}#chunk_{idx}_{hash_id}"

            chunk_meta = dict(meta)
            chunk_meta["chunk_index"] = idx
            chunk_meta["total_chunks"] = len(raw_chunks)
            chunk_meta["source"] = source

            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    content=chunk_text,
                    source=source,
                    metadata=chunk_meta,
                )
            )

        logger.debug("Split document '%s' into %d chunks.", source, len(chunks))
        return chunks

    def split_documents(self, documents: list[TextDocumentForRAG]) -> list[TextChunk]:
        """Split a batch of TextDocumentForRAG instances."""
        all_chunks: list[TextChunk] = []
        for doc in documents:
            chunks = self.split_text(doc.content, doc.metadata)
            all_chunks.extend(chunks)

        logger.info("Total chunks generated across %d documents: %d", len(documents), len(all_chunks))
        return all_chunks

