"""End-to-End RAG Pipeline module for Cognify.

Orchestrates document chunking, embedding generation, FAISS indexing,
semantic context retrieval, and local LLM grounded question answering.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from app.config import AppConfig
from app.ingestion.document_loader import TextDocumentForRAG
from app.llm.generator import OllamaLLM
from app.rag.chunker import DocumentChunker, TextChunk
from app.rag.embedder import LocalEmbedder
from app.rag.retriever import RetrievedContext, SemanticRetriever
from app.rag.vector_store import FAISSVectorStore

logger = logging.getLogger(__name__)


@dataclass
class RAGResponse:
    """Complete structured response from the RAG pipeline."""

    question: str
    answer: str
    sources: list[str] = field(default_factory=list)
    retrieved_chunks: list[TextChunk] = field(default_factory=list)
    has_context: bool = False
    error: str | None = None

    def format_output(self) -> str:
        """Format answer and source attribution for terminal output."""
        output = f"{self.answer}\n"
        if self.sources:
            output += "\nSources:\n"
            for src in self.sources:
                output += f"- {src}\n"
        return output.strip()


class RAGPipeline:
    """Unified RAG pipeline managing indexing and question answering."""

    def __init__(
        self,
        config: AppConfig,
        vector_store: FAISSVectorStore | None = None,
        embedder: LocalEmbedder | None = None,
        chunker: DocumentChunker | None = None,
        llm: OllamaLLM | None = None,
    ):
        self.config = config
        self.chunker = chunker or DocumentChunker(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )
        self.embedder = embedder or LocalEmbedder(model_name=config.embedding_model)
        self.vector_store = vector_store or FAISSVectorStore(dimension=self.embedder.dimension)
        self.llm = llm or OllamaLLM.from_config(config)
        self.retriever = SemanticRetriever(
            vector_store=self.vector_store,
            embedder=self.embedder,
            top_k=config.top_k,
            score_threshold=config.similarity_threshold if config.similarity_threshold < 1.0 else 0.25,
        )

    def load_or_initialize_index(self) -> bool:
        """Attempt to load existing persisted index; returns True if loaded."""
        loaded = self.vector_store.load(self.config.vector_store_dir)
        if loaded:
            logger.info("Loaded persisted vector store with %d chunks.", len(self.vector_store))
        return loaded

    def persist_index(self) -> None:
        """Save vector store to disk."""
        self.vector_store.save(self.config.vector_store_dir)

    def index_documents(self, documents: Sequence[TextDocumentForRAG]) -> int:
        """Chunk, embed, and index a collection of documents.

        Args:
            documents: Sequence of TextDocumentForRAG objects.

        Returns:
            Number of newly indexed chunks.
        """
        if not documents:
            logger.warning("No documents provided for indexing.")
            return 0

        chunks = self.chunker.split_documents(list(documents))
        if not chunks:
            logger.warning("No chunks generated from documents.")
            return 0

        texts = [c.content for c in chunks]
        logger.info("Generating embeddings for %d text chunks...", len(texts))
        embeddings = self.embedder.embed_texts(texts)

        added_count = self.vector_store.add_chunks(chunks, embeddings)
        self.persist_index()
        logger.info("Successfully indexed %d new chunks into FAISS vector store.", added_count)
        return added_count

    def query(self, question: str, top_k: int | None = None) -> RAGResponse:
        """Answer a natural language question using grounded semantic retrieval.

        Args:
            question: User inquiry.
            top_k: Optional override for retrieved chunk count.

        Returns:
            RAGResponse with grounded answer and actual source file attribution.
        """
        # Retrieve relevant context
        retrieved: RetrievedContext = self.retriever.retrieve(question, top_k=top_k)

        if not retrieved.has_context:
            logger.info("No relevant context found for question: '%s'", question)
            return RAGResponse(
                question=question,
                answer="The provided documents do not contain information regarding this question.",
                sources=[],
                retrieved_chunks=[],
                has_context=False,
            )

        try:
            # Generate grounded answer via local Ollama LLM
            answer = self.llm.answer_with_context(
                question=question,
                context=retrieved.formatted_context,
            )

            return RAGResponse(
                question=question,
                answer=answer,
                sources=retrieved.sources,
                retrieved_chunks=retrieved.chunks,
                has_context=True,
            )

        except Exception as e:
            logger.error("Error generating answer with local LLM: %s", e)
            return RAGResponse(
                question=question,
                answer=f"Could not generate answer due to local model error: {e}",
                sources=retrieved.sources,
                retrieved_chunks=retrieved.chunks,
                has_context=True,
                error=str(e),
            )

