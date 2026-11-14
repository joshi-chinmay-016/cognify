"""Document loader and DataFrame registry module.

Coordinates ingestion of Word and Excel documents from disk or Drive,
populates the ExcelRegistry for analytical operations, and prepares
text blocks for RAG chunking and vector storage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from app.ingestion.excel_parser import ExcelParser, ExcelSheetData, ParsedExcelWorkbook
from app.ingestion.word_parser import ParsedWordDocument, WordParser
from app.utils.metadata import MetadataRegistry

logger = logging.getLogger(__name__)


class ExcelRegistry:
    """Central structured registry of loaded Excel workbooks and sheets.

    Provides safe, controlled access to raw DataFrames for the Pandas analytics engine.
    """

    def __init__(self) -> None:
        self._workbooks: dict[str, ParsedExcelWorkbook] = {}
        # Mapping (normalized_book_name, normalized_sheet_name) -> ExcelSheetData
        self._sheets: dict[tuple[str, str], ExcelSheetData] = {}

    def register_workbook(self, workbook: ParsedExcelWorkbook) -> None:
        """Register a parsed Excel workbook and all its worksheets."""
        norm_book = workbook.filename.lower()
        self._workbooks[norm_book] = workbook

        for s_name, sheet_data in workbook.sheets.items():
            key = (norm_book, s_name.lower())
            self._sheets[key] = sheet_data

        logger.debug("Registered workbook '%s' with %d sheets.", workbook.filename, len(workbook.sheets))

    def get_workbook(self, name: str) -> ParsedExcelWorkbook | None:
        """Find workbook by name (case-insensitive, matching with or without .xlsx)."""
        norm_name = name.lower()
        if norm_name in self._workbooks:
            return self._workbooks[norm_name]
        for key, wb in self._workbooks.items():
            if Path(key).stem == Path(norm_name).stem:
                return wb
        return None

    def get_sheet(self, workbook_name: str, sheet_name: str | None = None) -> ExcelSheetData | None:
        """Find specific sheet in a workbook. If sheet_name is None, returns first sheet."""
        wb = self.get_workbook(workbook_name)
        if not wb or not wb.sheets:
            return None

        if sheet_name:
            norm_sheet = sheet_name.lower()
            for s_name, data in wb.sheets.items():
                if s_name.lower() == norm_sheet:
                    return data
            return None

        # Return the first worksheet
        first_sheet_name = next(iter(wb.sheets))
        return wb.sheets[first_sheet_name]

    def find_all_matching_sheets(self, candidate_name: str) -> list[ExcelSheetData]:
        """Find sheets across any workbook where sheet name or workbook matches."""
        results: list[ExcelSheetData] = []
        target = candidate_name.lower()
        for (wb_name, s_name), sheet_data in self._sheets.items():
            if target in wb_name or target in s_name:
                results.append(sheet_data)
        return results

    def list_workbooks(self) -> list[str]:
        """Return names of all registered workbooks."""
        return [wb.filename for wb in self._workbooks.values()]

    def list_all_sheets(self) -> list[dict[str, Any]]:
        """Return metadata summary for all registered sheets."""
        summaries = []
        for sheet_data in self._sheets.values():
            summaries.append({
                "workbook": sheet_data.workbook_name,
                "sheet": sheet_data.sheet_name,
                "rows": sheet_data.row_count,
                "columns": sheet_data.columns,
                "numeric_columns": sheet_data.numeric_columns,
                "date_columns": sheet_data.date_columns,
            })
        return summaries

    def clear(self) -> None:
        self._workbooks.clear()
        self._sheets.clear()


@dataclass
class TextDocumentForRAG:
    """Unified document representation for the text chunker."""

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    """Summary of ingested documents."""

    word_documents: list[ParsedWordDocument] = field(default_factory=list)
    excel_workbooks: list[ParsedExcelWorkbook] = field(default_factory=list)
    rag_documents: list[TextDocumentForRAG] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DocumentLoader:
    """Loads and routes documents from disk into parsers and registries."""

    def __init__(self, excel_registry: ExcelRegistry | None = None, metadata_registry: MetadataRegistry | None = None):
        self.excel_registry = excel_registry or ExcelRegistry()
        self.metadata_registry = metadata_registry

    def load_directory(self, directory: Path) -> IngestionResult:
        """Scan directory and load all supported .docx, .xlsx, .xls files."""
        result = IngestionResult()
        if not directory.exists():
            result.errors.append(f"Directory not found: {directory}")
            return result

        supported_files: list[Path] = []
        for ext in ["*.docx", "*.xlsx", "*.xls"]:
            supported_files.extend(directory.glob(ext))

        logger.info("Found %d supported files in %s", len(supported_files), directory)

        for file_path in supported_files:
            try:
                suffix = file_path.suffix.lower()
                if suffix == ".docx":
                    parsed_doc = WordParser.parse(file_path, filename=file_path.name)
                    if not parsed_doc.is_empty:
                        result.word_documents.append(parsed_doc)
                        result.rag_documents.append(
                            TextDocumentForRAG(
                                content=parsed_doc.full_text,
                                metadata={
                                    "source": parsed_doc.filename,
                                    "filename": parsed_doc.filename,
                                    "file_id": parsed_doc.file_id,
                                    "file_type": "docx",
                                    "title": parsed_doc.title,
                                    "author": parsed_doc.author,
                                },
                            )
                        )
                    else:
                        logger.warning("Empty or unparsable Word document: %s", file_path.name)

                elif suffix in [".xlsx", ".xls"]:
                    parsed_wb = ExcelParser.parse(file_path, filename=file_path.name)
                    if not parsed_wb.is_empty:
                        result.excel_workbooks.append(parsed_wb)
                        self.excel_registry.register_workbook(parsed_wb)

                        # Create searchable RAG chunks from worksheets
                        for s_name, s_data in parsed_wb.sheets.items():
                            if s_data.text_representation:
                                result.rag_documents.append(
                                    TextDocumentForRAG(
                                        content=s_data.text_representation,
                                        metadata={
                                            "source": parsed_wb.filename,
                                            "filename": parsed_wb.filename,
                                            "file_id": parsed_wb.file_id,
                                            "file_type": "xlsx",
                                            "sheet_name": s_name,
                                            "columns": ", ".join(s_data.columns),
                                        },
                                    )
                                )
                    else:
                        logger.warning("Empty or unparsable Excel workbook: %s", file_path.name)

            except Exception as e:
                err = f"Failed to ingest {file_path.name}: {e}"
                logger.error(err)
                result.errors.append(err)

        return result

