"""Word document parser using python-docx.

Extracts headings, paragraphs, tables, and metadata while handling
corrupted or empty documents gracefully.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docx
from docx.opc.exceptions import PackageNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class DocumentSection:
    """Represents a discrete structural section in a Word document."""

    section_type: str  # 'heading', 'paragraph', 'table'
    content: str
    level: int = 0  # 1-6 for headings, 0 for normal text


@dataclass
class ParsedWordDocument:
    """Structured representation of a parsed Word document."""

    filename: str
    file_id: str
    file_type: str = "docx"
    title: str = ""
    author: str = ""
    full_text: str = ""
    sections: list[DocumentSection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_empty: bool = False


class WordParser:
    """Parser for .docx documents."""

    @staticmethod
    def parse(file_path: Path, file_id: str = "", filename: str = "") -> ParsedWordDocument:
        """Parse a Word document into structured sections and unified text.

        Args:
            file_path: Path to the .docx file on disk.
            file_id: Unique identifier for the file (e.g. Drive ID).
            filename: Original name of the document.

        Returns:
            ParsedWordDocument containing extracted text, sections, and metadata.
        """
        doc_name = filename or file_path.name
        doc_id = file_id or doc_name

        if not file_path.exists():
            logger.error("Word file does not exist: %s", file_path)
            return ParsedWordDocument(
                filename=doc_name,
                file_id=doc_id,
                is_empty=True,
                metadata={"error": "File not found"},
            )

        try:
            doc = docx.Document(str(file_path))
        except PackageNotFoundError:
            logger.error("File is not a valid docx package: %s", file_path)
            return ParsedWordDocument(
                filename=doc_name,
                file_id=doc_id,
                is_empty=True,
                metadata={"error": "PackageNotFoundError: corrupted or invalid docx file"},
            )
        except Exception as e:
            logger.error("Failed to parse Word document %s: %s", file_path, e)
            return ParsedWordDocument(
                filename=doc_name,
                file_id=doc_id,
                is_empty=True,
                metadata={"error": str(e)},
            )

        sections: list[DocumentSection] = []
        text_parts: list[str] = []

        # Extract core properties/metadata
        author = ""
        title = ""
        try:
            props = doc.core_properties
            author = props.author or ""
            title = props.title or ""
        except Exception as e:
            logger.debug("Could not read core properties for %s: %s", doc_name, e)

        # Iterate through block-level elements in document order
        for block in doc.element.body:
            tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag

            if tag == "p":
                # Paragraph
                p = docx.text.paragraph.Paragraph(block, doc)
                text = p.text.strip()
                if not text:
                    continue

                style_name = p.style.name if p.style else ""
                if style_name.startswith("Heading"):
                    try:
                        level = int(style_name.split()[-1])
                    except (ValueError, IndexError):
                        level = 1
                    prefix = "#" * level
                    formatted = f"{prefix} {text}"
                    sections.append(DocumentSection(section_type="heading", content=formatted, level=level))
                    text_parts.append(formatted)
                else:
                    sections.append(DocumentSection(section_type="paragraph", content=text, level=0))
                    text_parts.append(text)

            elif tag == "tbl":
                # Table
                t = docx.table.Table(block, doc)
                table_lines: list[str] = []
                for row_idx, row in enumerate(t.rows):
                    cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    if any(cells):
                        line = " | ".join(cells)
                        table_lines.append(f"| {line} |")
                        if row_idx == 0:
                            # Add markdown separator
                            separator = " | ".join(["---"] * len(cells))
                            table_lines.append(f"| {separator} |")

                if table_lines:
                    table_content = "\n".join(table_lines)
                    sections.append(DocumentSection(section_type="table", content=table_content))
                    text_parts.append(f"\n[Table in {doc_name}]\n{table_content}\n")

        full_text = "\n\n".join(text_parts).strip()
        is_empty = len(full_text) == 0

        metadata = {
            "author": author,
            "title": title,
            "section_count": len(sections),
            "char_count": len(full_text),
            "table_count": sum(1 for s in sections if s.section_type == "table"),
        }

        logger.info(
            "Parsed Word document '%s': %d chars, %d sections, %d tables.",
            doc_name,
            len(full_text),
            len(sections),
            metadata["table_count"],
        )

        return ParsedWordDocument(
            filename=doc_name,
            file_id=doc_id,
            file_type="docx",
            title=title,
            author=author,
            full_text=full_text,
            sections=sections,
            metadata=metadata,
            is_empty=is_empty,
        )

