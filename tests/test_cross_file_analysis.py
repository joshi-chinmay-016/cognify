"""Unit tests for Cross-Workbook Analytics."""

from pathlib import Path
import pandas as pd
import pytest

from app.analytics.cross_file_analysis import CrossFileAnalyzer
from app.ingestion.document_loader import ExcelRegistry
from app.ingestion.excel_parser import ExcelParser


def create_two_sales_files(tmp_path: Path) -> ExcelRegistry:
    """Helper to create sales_2025.xlsx and sales_2026.xlsx."""
    data_2025 = {
        "Date": ["2025-01-01", "2025-06-01"],
        "Region": ["North", "South"],
        "Product": ["Alpha", "Beta"],
        "Revenue": [40000.0, 60000.0],  # Total: 100,000.0
    }
    data_2026 = {
        "Date": ["2026-01-01", "2026-06-01"],
        "Region": ["North", "South"],
        "Product": ["Alpha", "Beta"],
        "Revenue": [50000.0, 75000.0],  # Total: 125,000.0
    }

    f1 = tmp_path / "sales_2025.xlsx"
    f2 = tmp_path / "sales_2026.xlsx"
    pd.DataFrame(data_2025).to_excel(str(f1), index=False)
    pd.DataFrame(data_2026).to_excel(str(f2), index=False)

    p1 = ExcelParser.parse(f1, filename="sales_2025.xlsx")
    p2 = ExcelParser.parse(f2, filename="sales_2026.xlsx")

    reg = ExcelRegistry()
    reg.register_workbook(p1)
    reg.register_workbook(p2)
    return reg


def test_cross_file_revenue_and_growth_calculation(tmp_path: Path):
    """Test mandatory cross-file requirement: comparing 2025 vs 2026 revenue and growth %."""
    registry = create_two_sales_files(tmp_path)
    analyzer = CrossFileAnalyzer(registry)

    result = analyzer.compare_workbooks(
        file1_name="sales_2025.xlsx",
        file2_name="sales_2026.xlsx",
        metric_col="Revenue",
        group_by_col="Region",
    )

    assert result.error is None
    assert result.file1_total == 100000.0
    assert result.file2_total == 125000.0
    assert result.difference == 25000.0
    # Growth = (125,000 - 100,000) / 100,000 * 100 = 25.0%
    assert result.percentage_growth == 25.0

    # Ensure BOTH source files are identified
    assert len(result.sources) == 2
    assert "sales_2025.xlsx" in result.sources
    assert "sales_2026.xlsx" in result.sources

    # Check formatted output contains key metrics
    output = result.format_output()
    assert "100,000.00" in output
    assert "125,000.00" in output
    assert "+25.00%" in output
    assert "sales_2025.xlsx" in output
    assert "sales_2026.xlsx" in output


def test_cross_file_missing_file_error(tmp_path: Path):
    """Test error handling when a requested file does not exist."""
    registry = create_two_sales_files(tmp_path)
    analyzer = CrossFileAnalyzer(registry)

    result = analyzer.compare_workbooks(
        file1_name="sales_2025.xlsx",
        file2_name="nonexistent_2027.xlsx",
    )
    assert result.error is not None
    assert "not found" in result.error.lower()
