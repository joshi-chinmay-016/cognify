"""Unit tests for Excel parser and registry."""

from pathlib import Path
import pandas as pd
import pytest

from app.ingestion.document_loader import DocumentLoader, ExcelRegistry
from app.ingestion.excel_parser import ExcelParser


def create_sample_workbook(path: Path) -> Path:
    """Helper to create a multi-sheet Excel file with numbers, dates, and missing values."""
    sales_data = {
        "Date": ["2025-01-15", "2025-02-20", "2025-03-10", "2025-04-05"],
        "Region": ["North", "South", "North", "West"],
        "Product": ["Alpha", "Beta", "Alpha", "Gamma"],
        "Revenue": [15000.50, 22000.00, None, 18500.25],
        "Units": [150, 210, 120, 190],
    }
    targets_data = {
        "Region": ["North", "South", "West", "East"],
        "TargetRevenue": [30000.0, 25000.0, 20000.0, 15000.0],
    }

    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        pd.DataFrame(sales_data).to_excel(writer, sheet_name="Sales", index=False)
        pd.DataFrame(targets_data).to_excel(writer, sheet_name="Targets", index=False)

    return path


def test_excel_parser_multiple_sheets_and_types(tmp_path: Path):
    """Test Excel parsing preserves multiple sheets, detects numeric and date columns."""
    excel_path = tmp_path / "sales_2025.xlsx"
    create_sample_workbook(excel_path)

    parsed = ExcelParser.parse(excel_path, file_id="excel_2025", filename="sales_2025.xlsx")

    assert not parsed.is_empty
    assert parsed.filename == "sales_2025.xlsx"
    assert "Sales" in parsed.sheets
    assert "Targets" in parsed.sheets

    sales_sheet = parsed.sheets["Sales"]
    assert "Revenue" in sales_sheet.numeric_columns
    assert "Units" in sales_sheet.numeric_columns
    assert "Date" in sales_sheet.date_columns
    assert "Region" in sales_sheet.text_columns
    assert sales_sheet.row_count == 4

    # Check text representation generation
    assert "Sales" in sales_sheet.text_representation
    assert "Summary Statistics" in sales_sheet.text_representation


def test_excel_registry_and_document_loader(tmp_path: Path):
    """Test loading through DocumentLoader and querying ExcelRegistry."""
    excel_path = tmp_path / "sales_2025.xlsx"
    create_sample_workbook(excel_path)

    registry = ExcelRegistry()
    loader = DocumentLoader(excel_registry=registry)
    result = loader.load_directory(tmp_path)

    assert len(result.excel_workbooks) == 1
    assert "sales_2025.xlsx" in registry.list_workbooks()

    # Query sheet
    sheet_data = registry.get_sheet("sales_2025.xlsx", "Sales")
    assert sheet_data is not None
    assert sheet_data.row_count == 4

    # Query first sheet if name omitted
    first_sheet = registry.get_sheet("sales_2025.xlsx")
    assert first_sheet is not None

