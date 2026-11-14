"""PDF document parser using pypdf.

Extracts page-by-page text, headings, and document metadata from PDF files
while handling corrupted or empty PDFs gracefully.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pypdf

logger = logging.getLogger(__name__)


@dataclass
class ParsedPDFDocument:
    """Structured representation of a parsed PDF document."""

    filename: str
    file_id: str
    file_type: str = "pdf"
    title: str = ""
    author: str = ""
    page_count: int = 0
    full_text: str = ""
    pages: list[tuple[int, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_empty: bool = False


class PDFParser:
    """Parser for .pdf documents."""

    @staticmethod
    def parse(file_path: Path, file_id: str = "", filename: str = "") -> ParsedPDFDocument:
        """Parse a PDF document into text chunks and metadata."""
        doc_name = filename or file_path.name
        doc_id = file_id or doc_name

        if not file_path.exists():
            logger.error("PDF file does not exist: %s", file_path)
            return ParsedPDFDocument(
                filename=doc_name,
                file_id=doc_id,
                is_empty=True,
                metadata={"error": "File not found"},
            )

        try:
            reader = pypdf.PdfReader(str(file_path))
        except Exception as e:
            logger.error("Failed to read PDF file %s: %s", file_path, e)
            return ParsedPDFDocument(
                filename=doc_name,
                file_id=doc_id,
                is_empty=True,
                metadata={"error": f"Invalid or corrupted PDF: {e}"},
            )

        page_texts: list[tuple[int, str]] = []
        full_text_parts: list[str] = []

        title = ""
        author = ""
        try:
            if reader.metadata:
                title = reader.metadata.title or ""
                author = reader.metadata.author or ""
        except Exception:
            pass

        for page_idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
                clean_text = text.strip()
                if clean_text:
                    page_texts.append((page_idx, clean_text))
                    full_text_parts.append(f"--- [Page {page_idx}] ---\n{clean_text}")
            except Exception as e:
                logger.warning("Error reading page %d in %s: %s", page_idx, doc_name, e)

        full_text = "\n\n".join(full_text_parts).strip()
        is_empty = len(full_text) == 0

        metadata = {
            "title": title,
            "author": author,
            "page_count": len(reader.pages),
            "char_count": len(full_text),
        }

        logger.info(
            "Parsed PDF '%s': %d pages, %d chars.",
            doc_name,
            len(reader.pages),
            len(full_text),
        )

        return ParsedPDFDocument(
            filename=doc_name,
            file_id=doc_id,
            file_type="pdf",
            title=title,
            author=author,
            page_count=len(reader.pages),
            full_text=full_text,
            pages=page_texts,
            metadata=metadata,
            is_empty=is_empty,
        )
