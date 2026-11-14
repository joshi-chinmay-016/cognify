"""Semantic retrieval module.

Retrieves top-k context chunks based on vector similarity, preserves source
attribution, and structures augmented context for the LLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.rag.chunker import TextChunk
from app.rag.embedder import LocalEmbedder
from app.rag.vector_store import FAISSVectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievedContext:
    """Aggregated retrieval result ready for LLM context augmentation."""

    chunks: list[TextChunk] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    formatted_context: str = ""

    @property
    def has_context(self) -> bool:
        return len(self.chunks) > 0


class SemanticRetriever:
    """Retriever engine executing vector search and structuring context."""

    def __init__(
        self,
        vector_store: FAISSVectorStore,
        embedder: LocalEmbedder,
        top_k: int = 5,
        score_threshold: float = 0.25,
    ):
        self.vector_store = vector_store
        self.embedder = embedder
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        score_threshold: float | None = None,
    ) -> RetrievedContext:
        """Retrieve most relevant chunks for a user query.

        Args:
            query: Natural language query string.
            top_k: Optional override for top-k results.
            score_threshold: Optional override for minimum similarity score.

        Returns:
            RetrievedContext containing chunks, source files, and formatted prompt context.
        """
        k = top_k or self.top_k
        threshold = score_threshold if score_threshold is not None else self.score_threshold

        query_emb = self.embedder.embed_query(query)
        search_results = self.vector_store.search(query_emb, top_k=k, score_threshold=threshold)

        if not search_results:
            logger.info("No chunks matched query '%s' above threshold %.2f", query, threshold)
            return RetrievedContext()

        chunks: list[TextChunk] = []
        sources_set: set[str] = set()
        sources_ordered: list[str] = []
        scores: list[float] = []
        context_blocks: list[str] = []

        for chunk, score in search_results:
            chunks.append(chunk)
            scores.append(score)

            src = chunk.metadata.get("filename") or chunk.source or "unknown_document"
            if src not in sources_set:
                sources_set.add(src)
                sources_ordered.append(src)

            header = f"[Document: {src}"
            if "sheet_name" in chunk.metadata:
                header += f" | Sheet: {chunk.metadata['sheet_name']}"
            header += f" | Similarity: {score:.2f}]"

            context_blocks.append(f"{header}\n{chunk.content}")

        formatted_context = "\n\n---\n\n".join(context_blocks)

        logger.info(
            "Retrieved %d chunks across %d sources for query: '%s'",
            len(chunks),
            len(sources_ordered),
            query,
        )

        return RetrievedContext(
            chunks=chunks,
            sources=sources_ordered,
            scores=scores,
            formatted_context=formatted_context,
        )
