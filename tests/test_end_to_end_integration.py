"""End-to-End integration tests for Cognify.

Tests the complete flow: document ingestion -> FAISS indexing ->
Ollama LLM RAG answering -> Pandas calculations -> Cross-file analysis ->
Chart generation.
"""

from pathlib import Path
import pytest

from app.analytics.chart_generator import ChartGenerator
from app.analytics.cross_file_analysis import CrossFileAnalyzer
from app.analytics.pandas_engine import PandasAnalyticsEngine
from app.config import AppConfig
from app.ingestion.document_loader import DocumentLoader, ExcelRegistry
from app.llm.generator import OllamaLLM
from app.query_router import QueryIntent, QueryRouter
from app.rag.pipeline import RAGPipeline
from scripts.generate_sample_data import generate_company_policy_docx, generate_sales_spreadsheets


@pytest.fixture(scope="module")
def setup_cognify_env(tmp_path_factory):
    """Set up temporary working directories and test documents."""
    base_dir = tmp_path_factory.mktemp("cognify_e2e")
    downloads_dir = base_dir / "downloads"
    downloads_dir.mkdir(parents=True)
    vector_dir = base_dir / "vector_store"
    charts_dir = base_dir / "charts"

    # Generate documents
    generate_company_policy_docx(downloads_dir / "company_policy.docx")
    generate_sales_spreadsheets(downloads_dir)

    cfg = AppConfig(
        root_dir=base_dir,
        downloads_dir=downloads_dir,
        vector_store_dir=vector_dir,
        charts_dir=charts_dir,
        ollama_model="qwen2.5:3b",
    )

    registry = ExcelRegistry()
    loader = DocumentLoader(excel_registry=registry)
    ingestion = loader.load_directory(downloads_dir)

    rag = RAGPipeline(config=cfg)
    rag.index_documents(ingestion.rag_documents)

    analytics = PandasAnalyticsEngine(registry)
    cross_analyzer = CrossFileAnalyzer(registry)
    chart_gen = ChartGenerator(config=cfg, registry=registry)
    router = QueryRouter(excel_registry=registry)

    return {
        "cfg": cfg,
        "registry": registry,
        "rag": rag,
        "analytics": analytics,
        "cross_analyzer": cross_analyzer,
        "chart_gen": chart_gen,
        "router": router,
    }


def test_e2e_rag_leave_policy(setup_cognify_env):
    """Test full RAG question answering on company_policy.docx."""
    rag: RAGPipeline = setup_cognify_env["rag"]

    # Check if Ollama is available
    online, _ = rag.llm.check_connection()
    if not online:
        pytest.skip("Ollama is not running locally.")

    resp = rag.query("What is the company's leave policy?")
    assert resp.has_context
    assert "company_policy.docx" in resp.sources
    assert len(resp.answer) > 20
    # Must mention leave/days
    assert any(term in resp.answer.lower() for term in ["25", "leave", "vacation", "days", "annual"])


def test_e2e_pandas_total_revenue(setup_cognify_env):
    """Test actual Pandas calculation of total revenue."""
    analytics: PandasAnalyticsEngine = setup_cognify_env["analytics"]

    res = analytics.calculate_summary_metric(
        metric_col="Revenue",
        operation="sum",
        workbook_name="sales_2025.xlsx",
    )
    assert res.error is None
    # 2025 total from generate_sales_spreadsheets:
    # 120k + 85k + 95k + 110k + 130k + 75k + 140k + 115k + 90k + 150k + 105k + 80k + 98k + 145k + 88k + 124k = 1,750,000.0
    assert res.result_value == 1750000.0
    assert "sales_2025.xlsx" in res.sources


def test_e2e_cross_file_comparison(setup_cognify_env):
    """Test mandatory cross-workbook requirement: 2025 vs 2026 sales comparison and % growth."""
    cross: CrossFileAnalyzer = setup_cognify_env["cross_analyzer"]

    res = cross.compare_workbooks(
        file1_name="sales_2025.xlsx",
        file2_name="sales_2026.xlsx",
        metric_col="Revenue",
        group_by_col="Region",
    )
    assert res.error is None
    assert res.file1_total == 1750000.0
    # 2026 total: 155+110+125+140+165+95+180+150+115+190+135+105+125+185+112+160 = 2,247,000.0
    assert res.file2_total == 2247000.0
    assert res.difference == 497000.0
    # Percentage growth: (497,000 / 1,750,000) * 100 = ~28.4%
    assert round(res.percentage_growth, 1) == 28.4

    # Verify both source filenames
    assert "sales_2025.xlsx" in res.sources
    assert "sales_2026.xlsx" in res.sources


def test_e2e_chart_generation(setup_cognify_env):
    """Test on-demand chart generation saves PNG."""
    chart_gen: ChartGenerator = setup_cognify_env["chart_gen"]
    registry: ExcelRegistry = setup_cognify_env["registry"]

    sheet = registry.get_sheet("sales_2025.xlsx")
    assert sheet is not None

    chart_path = chart_gen.create_bar_chart(
        df=sheet.df,
        category_col="Region",
        value_col="Revenue",
        title="2025 Regional Revenue",
    )

    assert chart_path.exists()
    assert chart_path.suffix == ".png"
    assert chart_path.stat().st_size > 1000
