"""Query classification and routing module for Cognify.

Performs deterministic intent classification, syntactic parameter extraction,
and semantic disambiguation to route user inquiries to Document RAG,
Pandas Analytics, Cross-File Analytics, or Chart Generation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.ingestion.document_loader import ExcelRegistry

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    """Enumeration of supported user query intents."""

    RAG = "rag"
    EXCEL_ANALYTICS = "excel_analytics"
    CROSS_FILE_ANALYTICS = "cross_file_analytics"
    CHART = "chart"
    CLARIFICATION = "clarification"


@dataclass
class RouteDecision:
    """Structured routing outcome with extracted execution parameters."""

    intent: QueryIntent
    confidence: float
    parameters: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    clarification_prompt: str | None = None


class QueryRouter:
    """Classifies user queries and extracts parameters for appropriate execution engines."""

    def __init__(self, excel_registry: ExcelRegistry | None = None):
        self.excel_registry = excel_registry or ExcelRegistry()

    def route(self, query: str) -> RouteDecision:
        """Route query to one of the execution engines."""
        text = query.strip()
        lower = text.lower()

        if not text or len(text) < 2:
            return RouteDecision(
                intent=QueryIntent.CLARIFICATION,
                confidence=1.0,
                clarification_prompt="Please provide a question about your documents or spreadsheets.",
                reasoning="Empty or trivial query.",
            )

        # 1. Check for Document/Policy-specific keywords that supersede arithmetic
        # e.g. "Explain the company's revenue policy", "What is the vacation policy?"
        doc_signals = [
            "policy", "handbook", "rule", "procedure", "guideline", "eligible",
            "benefit", "clause", "agreement", "contract", "leave", "vacation",
            "sick", "notice period", "code of conduct", "mission", "vision"
        ]
        is_explicit_policy_query = any(re.search(rf"\b{re.escape(w)}\b", lower) for w in doc_signals)
        is_explain_query = re.search(r"\b(explain|describe|summarize the policy|what is the policy)\b", lower)

        if is_explicit_policy_query or is_explain_query:
            # Check if user specifically requested a chart of a policy (very rare)
            if not any(w in lower for w in ["chart", "plot", "graph"]):
                return RouteDecision(
                    intent=QueryIntent.RAG,
                    confidence=0.95,
                    reasoning="Query asks for textual explanation, policy, or qualitative guidelines.",
                )

        # 2. Check for Chart Generation intent
        chart_keywords = ["chart", "plot", "graph", "histogram", "pie chart", "bar chart", "line chart", "visualize"]
        if any(re.search(rf"\b{re.escape(w)}\b", lower) for w in chart_keywords):
            chart_type = "bar"
            if "line" in lower or "trend" in lower:
                chart_type = "line"
            elif "pie" in lower or "distribution" in lower or "share" in lower:
                chart_type = "pie"

            # Detect dimension / category
            category_col = "region"
            if "product" in lower or "item" in lower:
                category_col = "product"
            elif "month" in lower or "date" in lower or "year" in lower:
                category_col = "date"
            elif "region" in lower or "territory" in lower:
                category_col = "region"

            # Detect metric
            metric_col = "revenue"
            if "sales" in lower:
                metric_col = "sales"
            elif "units" in lower or "quantity" in lower:
                metric_col = "units"
            elif "profit" in lower:
                metric_col = "profit"

            # Detect workbooks mentioned
            workbooks = self._extract_mentioned_workbooks(lower)

            return RouteDecision(
                intent=QueryIntent.CHART,
                confidence=0.95,
                parameters={
                    "chart_type": chart_type,
                    "category_col": category_col,
                    "metric_col": metric_col,
                    "workbooks": workbooks,
                },
                reasoning=f"User requested data visualization ({chart_type} chart).",
            )

        # 3. Check for Cross-File Excel Analytics intent
        # Signs: "compare ... 2025 and 2026", "growth between", mentions two files or two year spreadsheets
        years = re.findall(r"\b(202\d|201\d)\b", lower)
        mentioned_files = self._extract_mentioned_workbooks(lower)
        has_compare_word = any(w in lower for w in ["compare", "growth", "difference", "versus", "vs", "between"])

        if (len(mentioned_files) >= 2) or (has_compare_word and len(set(years)) >= 2):
            metric_col = "revenue"
            if "sales" in lower:
                metric_col = "sales"
            elif "units" in lower or "volume" in lower:
                metric_col = "units"
            elif "profit" in lower:
                metric_col = "profit"

            # Identify target workbooks from mentioned files or years
            wb1, wb2 = self._resolve_two_workbooks(mentioned_files, years)

            return RouteDecision(
                intent=QueryIntent.CROSS_FILE_ANALYTICS,
                confidence=0.95,
                parameters={
                    "file1": wb1,
                    "file2": wb2,
                    "metric": metric_col,
                    "group_by": "region" if "region" in lower else ("product" if "product" in lower else None),
                },
                reasoning="Query compares metrics across two distinct workbooks or time periods.",
            )

        # 4. Check for Single-File Excel Analytics intent
        analytics_operators = [
            "total", "sum", "average", "mean", "avg", "highest", "lowest",
            "maximum", "max", "minimum", "min", "count", "rank", "which region",
            "which product", "per region", "by region", "per product", "by product",
            "revenue in", "sales in"
        ]
        has_analytics_word = any(re.search(rf"\b{re.escape(w)}\b", lower) for w in analytics_operators)

        # Numerical columns mentioned
        has_numeric_col = any(w in lower for w in ["revenue", "sales", "units", "profit", "amount", "target"])

        if has_analytics_word and (has_numeric_col or any(w in lower for w in ["region", "product", "rows", "records"])):
            op = "sum"
            if any(w in lower for w in ["average", "mean", "avg"]):
                op = "mean"
            elif any(w in lower for w in ["highest", "max", "maximum", "top"]):
                op = "max"
            elif any(w in lower for w in ["lowest", "min", "minimum", "bottom"]):
                op = "min"
            elif any(w in lower for w in ["count", "how many rows", "number of"]):
                op = "count"

            # Group by extraction
            group_by = None
            if "by region" in lower or "which region" in lower or "per region" in lower:
                group_by = "region"
            elif "by product" in lower or "which product" in lower or "per product" in lower:
                group_by = "product"

            # Metric extraction
            metric = "revenue"
            if "sales" in lower:
                metric = "sales"
            elif "units" in lower or "quantity" in lower:
                metric = "units"
            elif "profit" in lower:
                metric = "profit"

            # Target workbook
            workbooks = self._extract_mentioned_workbooks(lower)
            wb_name = workbooks[0] if workbooks else (years[0] if years else None)

            return RouteDecision(
                intent=QueryIntent.EXCEL_ANALYTICS,
                confidence=0.90,
                parameters={
                    "operation": op,
                    "metric": metric,
                    "group_by": group_by,
                    "workbook": wb_name,
                },
                reasoning=f"User requested numerical computation ({op} of {metric}).",
            )

        # 5. Default to Document RAG for informational questions
        rag_starters = ["what", "who", "when", "where", "why", "how", "can", "is", "are", "tell me"]
        if any(lower.startswith(w) for w in rag_starters) or len(lower.split()) > 3:
            return RouteDecision(
                intent=QueryIntent.RAG,
                confidence=0.85,
                reasoning="Natural language question routed to Document RAG retrieval.",
            )

        # 6. Ambiguous query
        return RouteDecision(
            intent=QueryIntent.CLARIFICATION,
            confidence=0.5,
            clarification_prompt=(
                "I couldn't clearly determine whether you want to query document contents "
                "or perform a spreadsheet calculation. Could you please specify?"
            ),
            reasoning="Uncertain intent; ambiguous query keywords.",
        )

    def _extract_mentioned_workbooks(self, text: str) -> list[str]:
        """Extract workbook filenames or stem names from query."""
        found: list[str] = []
        registered = self.excel_registry.list_workbooks()

        # Check for registered file names
        for wb in registered:
            if wb.lower() in text or Path(wb).stem.lower() in text:
                found.append(wb)

        # Check for generic .xlsx or .xls names in text
        matches = re.findall(r"[\w-]+\.xlsx?", text)
        for m in matches:
            if m not in found:
                found.append(m)

        return found

    def _resolve_two_workbooks(self, mentioned_files: list[str], years: list[str]) -> tuple[str, str]:
        """Resolve the pair of workbooks for cross-file analysis."""
        registered = self.excel_registry.list_workbooks()

        if len(mentioned_files) >= 2:
            return mentioned_files[0], mentioned_files[1]

        # Match by years found in query
        if len(years) >= 2:
            y1, y2 = sorted(years)[:2]
            f1, f2 = None, None
            for wb in registered:
                if y1 in wb:
                    f1 = wb
                elif y2 in wb:
                    f2 = wb
            return f1 or f"sales_{y1}.xlsx", f2 or f"sales_{y2}.xlsx"

        # If 2 workbooks exist in registry, use them in order
        if len(registered) >= 2:
            return registered[0], registered[1]

        return "sales_2025.xlsx", "sales_2026.xlsx"
