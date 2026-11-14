"""Excel spreadsheet parser using Pandas and openpyxl.

Loads all worksheets, detects schemas, preserves numeric/date columns,
and generates structured text representations for semantic document retrieval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ExcelSheetData:
    """Represents a single parsed worksheet from an Excel workbook."""

    workbook_name: str
    file_id: str
    sheet_name: str
    df: pd.DataFrame
    columns: list[str] = field(default_factory=list)
    numeric_columns: list[str] = field(default_factory=list)
    date_columns: list[str] = field(default_factory=list)
    text_columns: list[str] = field(default_factory=list)
    row_count: int = 0
    text_representation: str = ""
    summary_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedExcelWorkbook:
    """Structured representation of an entire parsed Excel workbook."""

    filename: str
    file_id: str
    file_type: str = "xlsx"
    sheets: dict[str, ExcelSheetData] = field(default_factory=dict)
    combined_text: str = ""
    is_empty: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ExcelParser:
    """Parser for .xlsx and .xls Excel workbooks."""

    @staticmethod
    def _detect_and_cast_types(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str], list[str]]:
        """Identify and cleanly cast numeric, datetime, and string columns."""
        clean_df = df.copy()

        # Clean column names (strip whitespace, ensure string type)
        clean_df.columns = [str(c).strip() for c in clean_df.columns]

        numeric_cols: list[str] = []
        date_cols: list[str] = []
        text_cols: list[str] = []

        for col in clean_df.columns:
            series = clean_df[col]

            # Datetime check
            if pd.api.types.is_datetime64_any_dtype(series):
                date_cols.append(col)
                continue

            # Soft conversion for date strings or objects first
            if (pd.api.types.is_string_dtype(series) or series.dtype == object) and not series.dropna().empty:
                try:
                    first_val = str(series.dropna().iloc[0]).strip()
                    if any(char in first_val for char in ["-", "/", "202", "201", "199"]):
                        date_series = pd.to_datetime(series, errors="raise")
                        clean_df[col] = date_series
                        date_cols.append(col)
                        continue
                except (ValueError, TypeError, OverflowError):
                    pass

            # Numeric check
            if pd.api.types.is_numeric_dtype(series):
                numeric_cols.append(col)
                continue

            # Attempt soft conversion for numeric strings
            try:
                num_series = pd.to_numeric(series.dropna(), errors="raise")
                if not num_series.empty:
                    clean_df[col] = pd.to_numeric(series, errors="coerce")
                    numeric_cols.append(col)
                    continue
            except (ValueError, TypeError):
                pass

            text_cols.append(col)

        return clean_df, numeric_cols, date_cols, text_cols

    @classmethod
    def _generate_sheet_text(
        cls,
        workbook_name: str,
        sheet_name: str,
        df: pd.DataFrame,
        numeric_cols: list[str],
        date_cols: list[str],
    ) -> str:
        """Create a detailed, searchable textual representation of a worksheet for RAG."""
        lines: list[str] = [
            f"=== Spreadsheet: {workbook_name} | Worksheet: {sheet_name} ===",
            f"Dimensions: {len(df)} rows, {len(df.columns)} columns",
            f"Columns: {', '.join(df.columns.tolist())}",
        ]

        if numeric_cols:
            lines.append(f"Numeric Columns: {', '.join(numeric_cols)}")
        if date_cols:
            lines.append(f"Date Columns: {', '.join(date_cols)}")

        # Add descriptive statistics for numeric columns
        if numeric_cols and not df.empty:
            lines.append("\nSummary Statistics:")
            for col in numeric_cols:
                valid_vals = df[col].dropna()
                if not valid_vals.empty:
                    total = valid_vals.sum()
                    mean = valid_vals.mean()
                    min_val = valid_vals.min()
                    max_val = valid_vals.max()
                    lines.append(
                        f"- {col}: Total={total:,.2f}, Avg={mean:,.2f}, Min={min_val:,.2f}, Max={max_val:,.2f}"
                    )

        # Include sample preview rows in markdown table format
        if not df.empty:
            preview_count = min(15, len(df))
            preview_df = df.head(preview_count).fillna("")
            table_md = preview_df.to_markdown(index=False)
            lines.append(f"\nPreview Data (first {preview_count} rows):\n{table_md}")

        return "\n".join(lines)

    @classmethod
    def parse(cls, file_path: Path, file_id: str = "", filename: str = "") -> ParsedExcelWorkbook:
        """Parse an Excel workbook, loading all sheets into structured DataFrames."""
        book_name = filename or file_path.name
        doc_id = file_id or book_name

        if not file_path.exists():
            logger.error("Excel file does not exist: %s", file_path)
            return ParsedExcelWorkbook(
                filename=book_name,
                file_id=doc_id,
                is_empty=True,
                metadata={"error": "File not found"},
            )

        try:
            excel_file = pd.ExcelFile(str(file_path))
            sheet_names = excel_file.sheet_names
        except Exception as e:
            logger.error("Failed to open Excel workbook %s: %s", file_path, e)
            return ParsedExcelWorkbook(
                filename=book_name,
                file_id=doc_id,
                is_empty=True,
                metadata={"error": f"Failed to open Excel workbook: {e}"},
            )

        if not sheet_names:
            return ParsedExcelWorkbook(
                filename=book_name,
                file_id=doc_id,
                is_empty=True,
                metadata={"error": "Workbook has no worksheets"},
            )

        sheets_data: dict[str, ExcelSheetData] = {}
        sheet_text_blocks: list[str] = []

        for s_name in sheet_names:
            try:
                raw_df = pd.read_excel(excel_file, sheet_name=s_name)
                clean_df, num_cols, date_cols, text_cols = cls._detect_and_cast_types(raw_df)

                # Compute summary stats
                summary: dict[str, Any] = {}
                for col in num_cols:
                    s = clean_df[col].dropna()
                    if not s.empty:
                        summary[col] = {
                            "sum": float(s.sum()),
                            "mean": float(s.mean()),
                            "min": float(s.min()),
                            "max": float(s.max()),
                            "count": int(s.count()),
                        }

                sheet_text = cls._generate_sheet_text(book_name, s_name, clean_df, num_cols, date_cols)
                sheet_text_blocks.append(sheet_text)

                sheet_obj = ExcelSheetData(
                    workbook_name=book_name,
                    file_id=doc_id,
                    sheet_name=s_name,
                    df=clean_df,
                    columns=clean_df.columns.tolist(),
                    numeric_columns=num_cols,
                    date_columns=date_cols,
                    text_columns=text_cols,
                    row_count=len(clean_df),
                    text_representation=sheet_text,
                    summary_stats=summary,
                )
                sheets_data[s_name] = sheet_obj

            except Exception as e:
                logger.warning("Error reading sheet '%s' in workbook '%s': %s", s_name, book_name, e)

        combined_text = "\n\n".join(sheet_text_blocks).strip()
        is_empty = len(sheets_data) == 0 or all(s.row_count == 0 for s in sheets_data.values())

        metadata = {
            "sheet_count": len(sheets_data),
            "sheet_names": list(sheets_data.keys()),
            "total_rows": sum(s.row_count for s in sheets_data.values()),
        }

        logger.info(
            "Parsed Excel workbook '%s': %d sheets, %d total rows.",
            book_name,
            len(sheets_data),
            metadata["total_rows"],
        )

        return ParsedExcelWorkbook(
            filename=book_name,
            file_id=doc_id,
            file_type="xlsx",
            sheets=sheets_data,
            combined_text=combined_text,
            is_empty=is_empty,
            metadata=metadata,
        )
