"""Unit tests for Matplotlib Chart Generation."""

from pathlib import Path
import pandas as pd
import pytest

from app.analytics.chart_generator import ChartGenerationError, ChartGenerator
from app.config import AppConfig
from app.ingestion.document_loader import ExcelRegistry


def test_chart_generation_bar_line_pie(tmp_path: Path):
    """Test generating bar, line, and pie charts and verifying PNG creation."""
    chart_dir = tmp_path / "charts"
    cfg = AppConfig(charts_dir=chart_dir)
    reg = ExcelRegistry()
    generator = ChartGenerator(config=cfg, registry=reg)

    df = pd.DataFrame({
        "Region": ["North", "South", "East", "West"],
        "Revenue": [12000.0, 18000.0, 9500.0, 14200.0],
        "Month": ["Jan", "Feb", "Mar", "Apr"],
    })

    # 1. Bar Chart
    bar_path = generator.create_bar_chart(df, category_col="Region", value_col="Revenue", title="Revenue by Region")
    assert bar_path.exists()
    assert bar_path.suffix == ".png"
    assert bar_path.stat().st_size > 1000

    # 2. Line Chart
    line_path = generator.create_line_chart(df, x_col="Month", y_col="Revenue", title="Monthly Revenue")
    assert line_path.exists()
    assert line_path.suffix == ".png"
    assert line_path.stat().st_size > 1000

    # 3. Pie Chart
    pie_path = generator.create_pie_chart(df, category_col="Region", value_col="Revenue", title="Regional Share")
    assert pie_path.exists()
    assert pie_path.suffix == ".png"
    assert pie_path.stat().st_size > 1000


def test_chart_generation_invalid_columns(tmp_path: Path):
    """Test ChartGenerator raises ChartGenerationError on missing columns."""
    cfg = AppConfig(charts_dir=tmp_path / "charts")
    generator = ChartGenerator(config=cfg, registry=ExcelRegistry())

    df = pd.DataFrame({"A": [1, 2]})
    with pytest.raises(ChartGenerationError):
        generator.create_bar_chart(df, category_col="NonExistent", value_col="A")

