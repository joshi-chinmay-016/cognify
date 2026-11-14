"""Unit tests for Pandas Analytics Engine."""

from pathlib import Path
import pandas as pd
import pytest

from app.analytics.pandas_engine import PandasAnalyticsEngine
from app.ingestion.document_loader import ExcelRegistry
from app.ingestion.excel_parser import ExcelParser


def create_mock_registry(tmp_path: Path) -> ExcelRegistry:
    """Helper to populate an ExcelRegistry with known test numbers."""
    data = {
        "Region": ["North", "South", "North", "West", "East"],
        "Product": ["Alpha", "Beta", "Beta", "Alpha", "Gamma"],
        "Revenue": [1000.0, 2000.0, 3000.0, 4000.0, 5000.0],
        "Units": [10, 20, 30, 40, 50],
    }
    file_path = tmp_path / "sales_2025.xlsx"
    pd.DataFrame(data).to_excel(str(file_path), index=False)

    parsed = ExcelParser.parse(file_path, filename="sales_2025.xlsx")
    registry = ExcelRegistry()
    registry.register_workbook(parsed)
    return registry


def test_calculate_summary_metrics(tmp_path: Path):
    """Test sum, average, min, max, and count calculations."""
    registry = create_mock_registry(tmp_path)
    engine = PandasAnalyticsEngine(registry)

    # Total Sum: 1000 + 2000 + 3000 + 4000 + 5000 = 15000.0
    res_sum = engine.calculate_summary_metric(metric_col="revenue", operation="sum")
    assert res_sum.error is None
    assert res_sum.result_value == 15000.0
    assert "sales_2025.xlsx" in res_sum.sources

    # Average: 15000 / 5 = 3000.0
    res_mean = engine.calculate_summary_metric(metric_col="revenue", operation="mean")
    assert res_mean.result_value == 3000.0

    # Max: 5000.0
    res_max = engine.calculate_summary_metric(metric_col="revenue", operation="max")
    assert res_max.result_value == 5000.0

    # Min: 1000.0
    res_min = engine.calculate_summary_metric(metric_col="revenue", operation="min")
    assert res_min.result_value == 1000.0

    # Count: 5
    res_count = engine.calculate_summary_metric(metric_col="revenue", operation="count")
    assert res_count.result_value == 5


def test_group_by_aggregation(tmp_path: Path):
    """Test grouping total revenue by region."""
    registry = create_mock_registry(tmp_path)
    engine = PandasAnalyticsEngine(registry)

    # North has 1000 + 3000 = 4000
    res_group = engine.group_by_aggregate(group_by_col="Region", metric_col="Revenue", operation="sum")
    assert res_group.error is None
    assert res_group.table is not None

    north_row = res_group.table[res_group.table["Region"] == "North"]
    assert len(north_row) == 1
    assert north_row.iloc[0]["Total Revenue"] == 4000.0


def test_find_highest_entity(tmp_path: Path):
    """Test identifying entity with highest revenue."""
    registry = create_mock_registry(tmp_path)
    engine = PandasAnalyticsEngine(registry)

    res = engine.find_highest_or_lowest(group_by_col="Region", metric_col="Revenue", find_highest=True)
    assert res.error is None
    assert res.result_value["entity"] == "East"
    assert res.result_value["value"] == 5000.0
