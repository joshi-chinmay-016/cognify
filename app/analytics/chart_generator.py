"""Matplotlib Chart Generation module for Cognify.

Generates bar charts, line charts, and pie charts on demand from actual
spreadsheet data using a non-interactive backend. Saves PNG files to disk.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
# Use non-interactive backend for headless terminal execution
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from app.config import AppConfig
from app.ingestion.document_loader import ExcelRegistry

logger = logging.getLogger(__name__)


class ChartGenerationError(Exception):
    """Raised when chart rendering or aggregation fails."""


class ChartGenerator:
    """Renders data visualizations from structured spreadsheet DataFrames."""

    def __init__(self, config: AppConfig, registry: ExcelRegistry):
        self.config = config
        self.registry = registry
        self.output_dir = config.charts_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _generate_filename(self, prefix: str) -> Path:
        """Create a timestamped, unique PNG filename."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rand = uuid.uuid4().hex[:6]
        clean_prefix = "".join(c for c in prefix if c.isalnum() or c in "_-").strip("_")
        name = f"{clean_prefix}_{ts}_{rand}.png"
        return self.output_dir / name

    def create_bar_chart(
        self,
        df: pd.DataFrame,
        category_col: str,
        value_col: str,
        title: str = "",
        workbook_name: str = "",
    ) -> Path:
        """Generate a bar chart from DataFrame."""
        if category_col not in df.columns or value_col not in df.columns:
            raise ChartGenerationError(f"Columns '{category_col}' or '{value_col}' missing from data.")

        # Aggregate by category if duplicate categories exist
        clean_df = df.copy()
        clean_df[value_col] = pd.to_numeric(clean_df[value_col], errors="coerce")
        clean_df = clean_df.dropna(subset=[category_col, value_col])
        grouped = clean_df.groupby(category_col, as_index=False)[value_col].sum()
        grouped = grouped.sort_values(by=value_col, ascending=False).head(15)

        if grouped.empty:
            raise ChartGenerationError("No data available to plot bar chart after filtering nulls.")

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(
            grouped[category_col].astype(str),
            grouped[value_col],
            color="#2563eb",
            edgecolor="#1d4ed8",
            alpha=0.85,
        )

        ax.set_title(title or f"{value_col.title()} by {category_col.title()}", fontsize=14, fontweight="bold", pad=15)
        ax.set_xlabel(category_col.title(), fontsize=11, labelpad=10)
        ax.set_ylabel(value_col.title(), fontsize=11, labelpad=10)
        ax.grid(axis="y", linestyle="--", alpha=0.5)

        # Rotate labels if many categories
        if len(grouped) > 5 or any(len(str(x)) > 8 for x in grouped[category_col]):
            plt.xticks(rotation=40, ha="right")

        # Format y-axis with comma separation
        ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))

        plt.tight_layout()
        out_path = self._generate_filename(f"bar_{category_col}_{value_col}")
        fig.savefig(out_path, dpi=200)
        plt.close(fig)

        logger.info("Saved bar chart to %s", out_path)
        return out_path

    def create_line_chart(
        self,
        df: pd.DataFrame,
        x_col: str,
        y_col: str,
        title: str = "",
        series_col: str | None = None,
    ) -> Path:
        """Generate a line chart (e.g. trends over time or comparing multiple workbooks)."""
        if x_col not in df.columns or y_col not in df.columns:
            raise ChartGenerationError(f"Columns '{x_col}' or '{y_col}' missing from data.")

        clean_df = df.copy()
        clean_df[y_col] = pd.to_numeric(clean_df[y_col], errors="coerce")
        clean_df = clean_df.dropna(subset=[x_col, y_col])

        if clean_df.empty:
            raise ChartGenerationError("No valid data available to plot line chart.")

        fig, ax = plt.subplots(figsize=(10, 6))

        if series_col and series_col in clean_df.columns:
            for series_name, group in clean_df.groupby(series_col):
                grp_sorted = group.sort_values(by=x_col)
                ax.plot(
                    grp_sorted[x_col].astype(str),
                    grp_sorted[y_col],
                    marker="o",
                    linewidth=2,
                    label=str(series_name),
                )
            ax.legend(title=series_col.title())
        else:
            sorted_df = clean_df.sort_values(by=x_col)
            ax.plot(
                sorted_df[x_col].astype(str),
                sorted_df[y_col],
                marker="o",
                color="#059669",
                linewidth=2.5,
            )

        ax.set_title(title or f"{y_col.title()} Trend over {x_col.title()}", fontsize=14, fontweight="bold", pad=15)
        ax.set_xlabel(x_col.title(), fontsize=11, labelpad=10)
        ax.set_ylabel(y_col.title(), fontsize=11, labelpad=10)
        ax.grid(True, linestyle="--", alpha=0.5)

        plt.xticks(rotation=40, ha="right")
        ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))

        plt.tight_layout()
        out_path = self._generate_filename(f"line_{x_col}_{y_col}")
        fig.savefig(out_path, dpi=200)
        plt.close(fig)

        logger.info("Saved line chart to %s", out_path)
        return out_path

    def create_pie_chart(
        self,
        df: pd.DataFrame,
        category_col: str,
        value_col: str,
        title: str = "",
    ) -> Path:
        """Generate a pie chart showing proportions / distribution."""
        if category_col not in df.columns or value_col not in df.columns:
            raise ChartGenerationError(f"Columns '{category_col}' or '{value_col}' missing from data.")

        clean_df = df.copy()
        clean_df[value_col] = pd.to_numeric(clean_df[value_col], errors="coerce")
        clean_df = clean_df.dropna(subset=[category_col, value_col])
        grouped = clean_df.groupby(category_col, as_index=False)[value_col].sum()
        grouped = grouped[grouped[value_col] > 0].sort_values(by=value_col, ascending=False)

        if grouped.empty:
            raise ChartGenerationError("No positive values available for pie chart.")

        # Top 7 plus 'Other' if too many slices
        if len(grouped) > 7:
            top7 = grouped.head(7)
            other_sum = grouped.iloc[7:][value_col].sum()
            other_row = pd.DataFrame([{category_col: "Other", value_col: other_sum}])
            grouped = pd.concat([top7, other_row], ignore_index=True)

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(
            grouped[value_col],
            labels=grouped[category_col].astype(str),
            autopct="%1.1f%%",
            startangle=140,
            colors=plt.cm.Paired.colors,
        )

        ax.set_title(title or f"{value_col.title()} Distribution by {category_col.title()}", fontsize=14, fontweight="bold", pad=20)
        plt.tight_layout()

        out_path = self._generate_filename(f"pie_{category_col}_{value_col}")
        fig.savefig(out_path, dpi=200)
        plt.close(fig)

        logger.info("Saved pie chart to %s", out_path)
        return out_path
