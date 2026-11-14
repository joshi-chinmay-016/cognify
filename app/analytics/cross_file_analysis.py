"""Cross-Workbook Analytics module for Cognify.

Performs deterministic multi-file comparisons, difference calculations,
growth percentages, and schema validations across distinct Excel spreadsheets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.ingestion.document_loader import ExcelRegistry

logger = logging.getLogger(__name__)


@dataclass
class CrossFileComparisonResult:
    """Structured result of comparative analysis between two Excel files."""

    metric_name: str
    file1_name: str
    file1_total: float
    file2_name: str
    file2_total: float
    difference: float
    percentage_growth: float | None
    sources: list[str] = field(default_factory=list)
    comparison_table: pd.DataFrame | None = None
    category_breakdown: pd.DataFrame | None = None
    summary_text: str = ""
    error: str | None = None

    def format_output(self) -> str:
        """Render readable terminal output with both source files attributed."""
        if self.error:
            return f"Cross-File Analysis Error: {self.error}"

        lines = [self.summary_text]

        if self.comparison_table is not None and not self.comparison_table.empty:
            lines.append("\nSummary Comparison Table:")
            lines.append(self.comparison_table.to_markdown(index=False))

        if self.category_breakdown is not None and not self.category_breakdown.empty:
            lines.append("\nDetailed Breakdown:")
            lines.append(self.category_breakdown.to_markdown(index=False))

        lines.append("\nSources:")
        for src in self.sources:
            lines.append(f"- {src}")

        return "\n".join(lines)


class CrossFileAnalyzer:
    """Performs multi-workbook analytical comparisons."""

    def __init__(self, registry: ExcelRegistry):
        self.registry = registry

    def _resolve_column(self, df: pd.DataFrame, target_name: str) -> str | None:
        """Resolve column name with fuzzy matching and synonyms."""
        clean = target_name.strip().lower()
        for col in df.columns:
            if col.strip().lower() == clean:
                return col
        for col in df.columns:
            if clean in col.strip().lower():
                return col
        synonyms = ["revenue", "sales", "turnover", "amount", "total"]
        if clean in synonyms:
            for s in synonyms:
                for col in df.columns:
                    if s in col.strip().lower():
                        return col
        return None

    def compare_workbooks(
        self,
        file1_name: str,
        file2_name: str,
        metric_col: str = "revenue",
        group_by_col: str | None = None,
    ) -> CrossFileComparisonResult:
        """Compare aggregate metric across two separate Excel workbooks.

        Args:
            file1_name: Name or path of first Excel file (e.g. 'sales_2025.xlsx').
            file2_name: Name or path of second Excel file (e.g. 'sales_2026.xlsx').
            metric_col: Metric to compare (e.g. 'revenue' or 'sales').
            group_by_col: Optional column for category/regional breakdown.

        Returns:
            CrossFileComparisonResult containing totals, difference, growth %, and sources.
        """
        wb1 = self.registry.get_workbook(file1_name)
        wb2 = self.registry.get_workbook(file2_name)

        if not wb1:
            return CrossFileComparisonResult(
                metric_name=metric_col,
                file1_name=file1_name,
                file1_total=0.0,
                file2_name=file2_name,
                file2_total=0.0,
                difference=0.0,
                percentage_growth=None,
                error=f"First workbook '{file1_name}' is not found in loaded documents.",
            )

        if not wb2:
            return CrossFileComparisonResult(
                metric_name=metric_col,
                file1_name=file1_name,
                file1_total=0.0,
                file2_name=file2_name,
                file2_total=0.0,
                difference=0.0,
                percentage_growth=None,
                error=f"Second workbook '{file2_name}' is not found in loaded documents.",
            )

        # Retrieve first sheets
        sheet1 = next(iter(wb1.sheets.values()))
        sheet2 = next(iter(wb2.sheets.values()))

        df1 = sheet1.df.copy()
        df2 = sheet2.df.copy()

        # Validate columns
        col1 = self._resolve_column(df1, metric_col)
        col2 = self._resolve_column(df2, metric_col)

        if not col1:
            return CrossFileComparisonResult(
                metric_name=metric_col,
                file1_name=wb1.filename,
                file1_total=0.0,
                file2_name=wb2.filename,
                file2_total=0.0,
                difference=0.0,
                percentage_growth=None,
                error=f"Metric column '{metric_col}' not found in '{wb1.filename}'.",
            )

        if not col2:
            return CrossFileComparisonResult(
                metric_name=metric_col,
                file1_name=wb1.filename,
                file1_total=0.0,
                file2_name=wb2.filename,
                file2_total=0.0,
                difference=0.0,
                percentage_growth=None,
                error=f"Metric column '{metric_col}' not found in '{wb2.filename}'.",
            )

        # Compute totals using Pandas
        s1 = pd.to_numeric(df1[col1], errors="coerce").dropna()
        s2 = pd.to_numeric(df2[col2], errors="coerce").dropna()

        total1 = float(s1.sum())
        total2 = float(s2.sum())

        difference = total2 - total1

        # Percentage growth calculation with division-by-zero protection
        if total1 != 0.0:
            growth_pct = (difference / abs(total1)) * 100.0
            growth_str = f"{growth_pct:+.2f}%"
        else:
            growth_pct = None
            growth_str = "N/A (base year total is 0.00)"

        diff_str = f"{difference:+,.2f}"

        summary_lines = [
            f"Comparison of {metric_col.title()} between '{wb1.filename}' and '{wb2.filename}':",
            f"- Total in {wb1.filename}: {total1:,.2f}",
            f"- Total in {wb2.filename}: {total2:,.2f}",
            f"- Absolute Difference: {diff_str}",
            f"- Percentage Growth: {growth_str}",
        ]
        summary_text = "\n".join(summary_lines)

        # Construct summary table
        comparison_table = pd.DataFrame([
            {"Workbook": wb1.filename, f"Total {col1}": f"{total1:,.2f}"},
            {"Workbook": wb2.filename, f"Total {col2}": f"{total2:,.2f}"},
            {"Workbook": "Difference", f"Total {col1}": diff_str},
            {"Workbook": "Growth %", f"Total {col1}": growth_str},
        ])

        # Optional category breakdown
        breakdown_table = None
        if group_by_col:
            gcol1 = self._resolve_column(df1, group_by_col)
            gcol2 = self._resolve_column(df2, group_by_col)
            if gcol1 and gcol2:
                grp1 = df1.groupby(gcol1)[col1].sum().rename(f"{wb1.filename} ({col1})")
                grp2 = df2.groupby(gcol2)[col2].sum().rename(f"{wb2.filename} ({col2})")
                merged = pd.concat([grp1, grp2], axis=1).fillna(0.0)
                merged["Difference"] = merged.iloc[:, 1] - merged.iloc[:, 0]
                merged["Growth %"] = merged.apply(
                    lambda row: (
                        f"{((row['Difference'] / abs(row.iloc[0])) * 100.0):+.2f}%"
                        if row.iloc[0] != 0
                        else "N/A"
                    ),
                    axis=1,
                )
                breakdown_table = merged.reset_index().rename(columns={"index": group_by_col})

        return CrossFileComparisonResult(
            metric_name=metric_col,
            file1_name=wb1.filename,
            file1_total=total1,
            file2_name=wb2.filename,
            file2_total=total2,
            difference=difference,
            percentage_growth=growth_pct,
            sources=[wb1.filename, wb2.filename],
            comparison_table=comparison_table,
            category_breakdown=breakdown_table,
            summary_text=summary_text,
        )
