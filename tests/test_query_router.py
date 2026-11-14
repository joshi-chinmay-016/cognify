"""Unit tests for QueryRouter classification and routing."""

import pytest

from app.ingestion.document_loader import ExcelRegistry
from app.query_router import QueryIntent, QueryRouter


def test_query_router_required_examples():
    """Test all prompt specification routing examples."""
    router = QueryRouter(ExcelRegistry())

    # 1. Document RAG: Leave policy
    d1 = router.route("What is the company's leave policy?")
    assert d1.intent == QueryIntent.RAG

    # 2. Document RAG: Employee benefits
    d2 = router.route("Who is eligible for employee benefits?")
    assert d2.intent == QueryIntent.RAG

    # 3. Excel Analytics: Total revenue in 2025
    d3 = router.route("What is the total revenue in 2025?")
    assert d3.intent == QueryIntent.EXCEL_ANALYTICS
    assert d3.parameters.get("operation") == "sum"

    # 4. Cross-file Excel Analytics: Compare sales_2025.xlsx and sales_2026.xlsx
    d4 = router.route("Compare the total sales in sales_2025.xlsx and sales_2026.xlsx.")
    assert d4.intent == QueryIntent.CROSS_FILE_ANALYTICS

    # 5. Excel Analytics: Highest revenue by region
    d5 = router.route("Which region had the highest revenue?")
    assert d5.intent == QueryIntent.EXCEL_ANALYTICS
    assert d5.parameters.get("group_by") == "region"

    # 6. Chart Generation: Monthly sales comparison chart
    d6 = router.route("Generate a monthly sales comparison chart.")
    assert d6.intent == QueryIntent.CHART

    # 7. Document RAG: Revenue policy (even though it contains 'revenue', it asks for 'policy')
    d7 = router.route("Explain the company's revenue policy.")
    assert d7.intent == QueryIntent.RAG

    # 8. Clarification on empty / ambiguous query
    d8 = router.route("xyz123")
    assert d8.intent == QueryIntent.CLARIFICATION


def test_query_router_with_registered_workbooks():
    """Test routing when registry contains loaded workbooks (exercises Path extraction)."""
    from app.ingestion.excel_parser import ParsedExcelWorkbook

    reg = ExcelRegistry()
    reg.register_workbook(ParsedExcelWorkbook(filename="sales_2025.xlsx", file_id="f1"))
    reg.register_workbook(ParsedExcelWorkbook(filename="sales_2026.xlsx", file_id="f2"))

    router = QueryRouter(reg)

    # 1. Total revenue in 2025 (matches registered workbook)
    d1 = router.route("What is the total revenue in 2025?")
    assert d1.intent == QueryIntent.EXCEL_ANALYTICS

    # 2. Compare 2025 and 2026
    d2 = router.route("Compare total revenue in 2025 and 2026.")
    assert d2.intent == QueryIntent.CROSS_FILE_ANALYTICS
    assert "sales_2025.xlsx" in d2.parameters["file1"] or "sales_2025.xlsx" in d2.parameters["file2"]

    # 3. Chart with registered workbooks
    d3 = router.route("Generate a bar chart comparing total revenue by region.")
    assert d3.intent == QueryIntent.CHART

    # 4. Chart explicitly naming a registered workbook
    d4 = router.route("Generate a bar chart for sales_2025.xlsx by region.")
    assert d4.intent == QueryIntent.CHART
    assert "sales_2025.xlsx" in d4.parameters["workbooks"]

