"""Pandas Analytics Engine module for Cognify.

Performs deterministic, safe numerical calculations, aggregations,
groupings, rankings, and filtering directly on structured DataFrames.
Does NOT execute arbitrary Python code or unrestricted LLM expressions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.ingestion.document_loader import ExcelRegistry, ExcelSheetData

logger = logging.getLogger(__name__)


@dataclass
class CalculationResult:
    """Result of an analytics calculation."""

    operation: str
    metric: str
    result_value: Any
    sources: list[str] = field(default_factory=list)
    summary_text: str = ""
    table: pd.DataFrame | None = None
    error: str | None = None

    def format_output(self) -> str:
        """Format the analytical result for display."""
        if self.error:
            return f"Calculation Error: {self.error}"

        lines = [self.summary_text]
        if self.table is not None and not self.table.empty:
            lines.append("\n" + self.table.to_markdown(index=False))

        if self.sources:
            lines.append("\nSources:")
            for s in self.sources:
                lines.append(f"- {s}")

        return "\n".join(lines)


class PandasAnalyticsEngine:
    """Dedicated analytics engine for spreadsheet data."""

    def __init__(self, registry: ExcelRegistry):
        self.registry = registry

    def _resolve_sheet(self, workbook_name: str | None, sheet_name: str | None = None) -> ExcelSheetData | None:
        """Find the target worksheet from workbook and sheet names."""
        if workbook_name:
            sheet = self.registry.get_sheet(workbook_name, sheet_name)
            if sheet:
                return sheet

        # If workbook_name not specified or not found, try finding across all registered sheets
        all_sheets = self.registry.list_all_sheets()
        if not all_sheets:
            return None

        # Return the first available sheet if only one workbook exists
        workbooks = self.registry.list_workbooks()
        if len(workbooks) >= 1:
            return self.registry.get_sheet(workbooks[0])
        return None

    def _find_column(self, df: pd.DataFrame, target_name: str) -> str | None:
        """Fuzzy match column name (case-insensitive, substring, common synonyms)."""
        if not target_name:
            return None

        clean_target = target_name.strip().lower()

        # Exact case-insensitive match
        for col in df.columns:
            if col.strip().lower() == clean_target:
                return col

        # Substring match
        for col in df.columns:
            if clean_target in col.strip().lower() or col.strip().lower() in clean_target:
                return col

        # Synonym matching
        synonyms: dict[str, list[str]] = {
            "revenue": ["sales", "turnover", "income", "amount", "total_revenue"],
            "sales": ["revenue", "amount", "turnover"],
            "date": ["time", "day", "period", "month", "year"],
            "region": ["territory", "location", "area", "zone", "state"],
            "product": ["item", "sku", "category", "service"],
            "units": ["quantity", "count", "volume", "qty"],
            "profit": ["margin", "net_income", "earnings"],
        }

        candidates = synonyms.get(clean_target, [])
        for candidate in candidates:
            for col in df.columns:
                if candidate in col.strip().lower():
                    return col

        return None

    def calculate_summary_metric(
        self,
        metric_col: str,
        operation: str = "sum",  # 'sum', 'mean', 'min', 'max', 'count'
        workbook_name: str | None = None,
        sheet_name: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> CalculationResult:
        """Compute aggregate metric (sum, average, min, max, count) on a column."""
        sheet = self._resolve_sheet(workbook_name, sheet_name)
        if not sheet:
            return CalculationResult(
                operation=operation,
                metric=metric_col,
                result_value=None,
                error="No spreadsheet found in registry to perform calculation.",
            )

        df = sheet.df.copy()
        target_col = self._find_column(df, metric_col)
        if not target_col:
            avail_cols = ", ".join(df.columns)
            return CalculationResult(
                operation=operation,
                metric=metric_col,
                result_value=None,
                error=f"Column '{metric_col}' not found in {sheet.workbook_name}. Available columns: {avail_cols}",
            )

        # Apply optional filters
        if filters:
            for filter_col, filter_val in filters.items():
                matched_fcol = self._find_column(df, filter_col)
                if matched_fcol:
                    if isinstance(filter_val, list):
                        df = df[df[matched_fcol].isin(filter_val)]
                    else:
                        df = df[df[matched_fcol].astype(str).str.lower() == str(filter_val).lower()]

        # Ensure numeric conversion
        series = pd.to_numeric(df[target_col], errors="coerce").dropna()
        if series.empty:
            return CalculationResult(
                operation=operation,
                metric=target_col,
                result_value=0.0,
                sources=[sheet.workbook_name],
                summary_text=f"No valid numeric data found for '{target_col}' in {sheet.workbook_name}.",
            )

        op = operation.lower()
        if op in ["sum", "total"]:
            val = float(series.sum())
            desc = f"Total {target_col}"
        elif op in ["mean", "average", "avg"]:
            val = float(series.mean())
            desc = f"Average {target_col}"
        elif op in ["min", "minimum", "lowest"]:
            val = float(series.min())
            desc = f"Minimum {target_col}"
        elif op in ["max", "maximum", "highest"]:
            val = float(series.max())
            desc = f"Maximum {target_col}"
        elif op in ["count", "rows"]:
            val = int(series.count())
            desc = f"Count of {target_col}"
        else:
            return CalculationResult(
                operation=operation,
                metric=target_col,
                result_value=None,
                error=f"Unsupported calculation operation: '{operation}'",
            )

        summary = f"{desc} in '{sheet.workbook_name}': {val:,.2f}"
        return CalculationResult(
            operation=op,
            metric=target_col,
            result_value=val,
            sources=[sheet.workbook_name],
            summary_text=summary,
        )

    def group_by_aggregate(
        self,
        group_by_col: str,
        metric_col: str,
        operation: str = "sum",
        workbook_name: str | None = None,
        sheet_name: str | None = None,
        sort_desc: bool = True,
        limit: int | None = None,
    ) -> CalculationResult:
        """Perform group-by aggregation (e.g. total revenue by region)."""
        sheet = self._resolve_sheet(workbook_name, sheet_name)
        if not sheet:
            return CalculationResult(
                operation="group_by",
                metric=metric_col,
                result_value=None,
                error="No spreadsheet found in registry.",
            )

        df = sheet.df.copy()
        matched_group = self._find_column(df, group_by_col)
        matched_metric = self._find_column(df, metric_col)

        if not matched_group or not matched_metric:
            return CalculationResult(
                operation="group_by",
                metric=metric_col,
                result_value=None,
                error=f"Columns '{group_by_col}' or '{metric_col}' not found in {sheet.workbook_name}.",
            )

        df[matched_metric] = pd.to_numeric(df[matched_metric], errors="coerce")
        df = df.dropna(subset=[matched_group, matched_metric])

        if df.empty:
            return CalculationResult(
                operation="group_by",
                metric=matched_metric,
                result_value=None,
                sources=[sheet.workbook_name],
                summary_text=f"No valid data to group '{matched_metric}' by '{matched_group}'.",
            )

        op = operation.lower()
        if op in ["mean", "average", "avg"]:
            grouped = df.groupby(matched_group, as_index=False)[matched_metric].mean()
            col_label = f"Average {matched_metric}"
        elif op in ["count"]:
            grouped = df.groupby(matched_group, as_index=False)[matched_metric].count()
            col_label = f"Count of {matched_metric}"
        else:
            grouped = df.groupby(matched_group, as_index=False)[matched_metric].sum()
            col_label = f"Total {matched_metric}"

        grouped.rename(columns={matched_metric: col_label}, inplace=True)
        if sort_desc:
            grouped = grouped.sort_values(by=col_label, ascending=False)
        else:
            grouped = grouped.sort_values(by=col_label, ascending=True)

        if limit:
            grouped = grouped.head(limit)

        summary = f"Grouped {col_label} by {matched_group} in '{sheet.workbook_name}':"
        return CalculationResult(
            operation="group_by",
            metric=matched_metric,
            result_value=grouped.to_dict(orient="records"),
            sources=[sheet.workbook_name],
            summary_text=summary,
            table=grouped,
        )

    def find_highest_or_lowest(
        self,
        group_by_col: str,
        metric_col: str,
        find_highest: bool = True,
        workbook_name: str | None = None,
        sheet_name: str | None = None,
    ) -> CalculationResult:
        """Find the top or bottom entity by a metric (e.g. which region had highest revenue)."""
        res = self.group_by_aggregate(
            group_by_col=group_by_col,
            metric_col=metric_col,
            operation="sum",
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            sort_desc=find_highest,
            limit=1,
        )
        if res.error or res.table is None or res.table.empty:
            return res

        top_row = res.table.iloc[0]
        entity = top_row.iloc[0]
        val = top_row.iloc[1]
        qualifier = "highest" if find_highest else "lowest"

        summary = (
            f"The {group_by_col} with the {qualifier} {metric_col} is '{entity}' "
            f"with {val:,.2f}."
        )
        return CalculationResult(
            operation="ranking",
            metric=metric_col,
            result_value={"entity": entity, "value": val},
            sources=res.sources,
            summary_text=summary,
            table=res.table,
        )

