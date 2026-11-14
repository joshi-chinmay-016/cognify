"""Interactive Rich Terminal Interface for Cognify.

Provides branding, status inspection, continuous multi-turn chat,
source attribution, and command handling (/help, /status, /files, /reindex, /exit).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.analytics.chart_generator import ChartGenerator
from app.analytics.cross_file_analysis import CrossFileAnalyzer
from app.analytics.pandas_engine import PandasAnalyticsEngine
from app.config import AppConfig
from app.drive.drive_client import GoogleDriveClient
from app.ingestion.document_loader import DocumentLoader, ExcelRegistry
from app.llm.generator import OllamaLLM
from app.query_router import QueryIntent, QueryRouter
from app.rag.pipeline import RAGPipeline
from app.utils.metadata import MetadataRegistry

logger = logging.getLogger(__name__)


class CognifyCLI:
    """Rich terminal user interface and interactive chat controller."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.console = Console()

        # Core subsystems
        self.metadata_registry = MetadataRegistry(config.processed_dir / "sync_metadata.json")
        self.excel_registry = ExcelRegistry()
        self.loader = DocumentLoader(
            excel_registry=self.excel_registry,
            metadata_registry=self.metadata_registry,
        )
        self.drive_client = GoogleDriveClient(config)
        self.llm = OllamaLLM.from_config(config)
        self.rag = RAGPipeline(config=config, llm=self.llm)
        self.analytics = PandasAnalyticsEngine(self.excel_registry)
        self.cross_analyzer = CrossFileAnalyzer(self.excel_registry)
        self.chart_generator = ChartGenerator(config=config, registry=self.excel_registry)
        self.router = QueryRouter(self.excel_registry)

        # State tracking
        self.word_count = 0
        self.excel_count = 0
        self.ollama_online = False
        self.ollama_status_msg = ""
        self.drive_connected = False

    def display_banner(self) -> None:
        """Display Cognify branding header."""
        banner_text = Text()
        banner_text.append("COGNIFY", style="bold cyan")
        banner_text.append(" — Your Documents. Your Data. One Intelligence.\n", style="bold white")
        banner_text.append("Local AI Document & Spreadsheet Assistant | v1.0.0", style="dim")

        panel = Panel(
            banner_text,
            border_style="cyan",
            expand=False,
            padding=(1, 2),
        )
        self.console.print(panel)

    def startup(self) -> None:
        """Execute application startup sequence with visual status feedback."""
        self.display_banner()
        self.config.ensure_directories()

        with self.console.status("[bold green]Initializing Cognify systems...", spinner="dots"):
            # 1. Check Ollama
            self.ollama_online, self.ollama_status_msg = self.llm.check_connection()

            # 2. Check Google Drive
            self.drive_connected = self.drive_client.authenticate(interactive=False)
            if self.drive_connected and self.config.google_drive_folder_id:
                try:
                    sync_report = self.drive_client.sync()
                    logger.info("Drive sync on startup: %s", sync_report)
                except Exception as e:
                    logger.warning("Drive sync failed: %s", e)

            # 3. Ingest documents from downloads directory
            ingestion = self.loader.load_directory(self.config.downloads_dir)
            self.word_count = len(ingestion.word_documents)
            self.excel_count = len(ingestion.excel_workbooks)

            # 4. Load or build FAISS index
            index_loaded = self.rag.load_or_initialize_index()
            if not index_loaded and ingestion.rag_documents:
                self.rag.index_documents(ingestion.rag_documents)

        # Print system status summary table
        self.print_status_table()
        self.console.print("\n[bold green]Cognify is ready.[/bold green] Type [cyan]/help[/cyan] for commands or ask any question.\n")

    def print_status_table(self) -> None:
        """Display structured system status."""
        table = Table(title="System & Data Status", border_style="blue", title_style="bold magenta")
        table.add_column("Subsystem", style="cyan", width=24)
        table.add_column("Status / Details", style="white")

        # LLM Status
        llm_color = "green" if self.ollama_online else "yellow"
        table.add_row("Ollama LLM", f"[{llm_color}]{self.ollama_status_msg}[/{llm_color}]")
        table.add_row("Model Configured", f"[cyan]{self.config.ollama_model}[/cyan]")

        # Drive Status
        drive_str = "[green]Connected[/green]" if self.drive_connected else "[yellow]Offline (Local storage active)[/yellow]"
        table.add_row("Google Drive", drive_str)

        # Document counts
        table.add_row("Word Documents", f"[green]{self.word_count}[/green] files loaded")
        table.add_row("Excel Workbooks", f"[green]{self.excel_count}[/green] workbooks loaded")
        table.add_row("Indexed Vector Chunks", f"[green]{len(self.rag.vector_store)}[/green] chunks in FAISS")

        self.console.print(table)

    def print_help(self) -> None:
        """Display available slash commands and example prompts."""
        help_table = Table(title="Available Commands & Prompt Examples", border_style="cyan")
        help_table.add_column("Command / Query Type", style="cyan", width=30)
        help_table.add_column("Description / Example", style="white")

        help_table.add_row("/help", "Show this guidance menu")
        help_table.add_row("/status", "Display current system, LLM, Drive, and index status")
        help_table.add_row("/files", "List all ingested Word and Excel documents")
        help_table.add_row("/sources", "List unique source documents registered in RAG index")
        help_table.add_row("/reindex", "Re-parse documents and rebuild FAISS index from scratch")
        help_table.add_row("/exit or /quit", "Exit the Cognify assistant")
        help_table.add_row("", "")
        help_table.add_row("Document RAG Query", "'What is the company leave policy?'")
        help_table.add_row("Spreadsheet Analytics", "'What is the total revenue in 2025?'")
        help_table.add_row("Cross-File Analysis", "'Compare total revenue from 2025 and 2026. Calculate percentage growth.'")
        help_table.add_row("Chart Generation", "'Generate a bar chart comparing total revenue by region.'")

        self.console.print(help_table)

    def list_files(self) -> None:
        """Display all currently registered files and sheets."""
        table = Table(title="Ingested Files & Spreadsheets", border_style="magenta")
        table.add_column("Filename", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Details", style="white")

        # Excel workbooks
        for item in self.excel_registry.list_all_sheets():
            cols = ", ".join(item["columns"][:4])
            if len(item["columns"]) > 4:
                cols += "..."
            table.add_row(
                item["workbook"],
                "Excel Worksheet",
                f"Sheet: {item['sheet']} | {item['rows']} rows | Cols: {cols}",
            )

        # Word docs
        for f in self.config.downloads_dir.glob("*.docx"):
            table.add_row(f.name, "Word Document", f"Local file ({f.stat().st_size} bytes)")

        self.console.print(table)

    def list_sources(self) -> None:
        """Display unique source documents present in FAISS vector store."""
        sources = {c.source for c in self.rag.vector_store.chunks}
        if not sources:
            self.console.print("[yellow]No documents currently indexed in vector store.[/yellow]")
            return

        self.console.print("[bold cyan]Indexed Sources in RAG Store:[/bold cyan]")
        for src in sorted(sources):
            self.console.print(f"  • [green]{src}[/green]")

    def reindex(self) -> None:
        """Re-parse and rebuild the FAISS vector index."""
        with self.console.status("[bold yellow]Re-indexing documents...", spinner="dots"):
            self.excel_registry.clear()
            ingestion = self.loader.load_directory(self.config.downloads_dir)
            self.rag.vector_store.clear()
            if ingestion.rag_documents:
                count = self.rag.index_documents(ingestion.rag_documents)
                self.console.print(f"[bold green]Re-indexing complete![/bold green] Indexed {count} chunks.")
            else:
                self.console.print("[yellow]No documents found in downloads directory to index.[/yellow]")

    def process_query(self, query: str) -> None:
        """Process user query through routing, execution, and formatted output."""
        decision = self.router.route(query)
        logger.info("Routing decision: %s (confidence: %.2f)", decision.intent, decision.confidence)

        if decision.intent == QueryIntent.CLARIFICATION:
            prompt = decision.clarification_prompt or "Could you please clarify your question?"
            self.console.print(f"\n[bold yellow]Cognify:[/bold yellow] {prompt}\n")
            return

        if decision.intent == QueryIntent.CHART:
            self._handle_chart_query(query, decision.parameters)
            return

        if decision.intent == QueryIntent.CROSS_FILE_ANALYTICS:
            self._handle_cross_file_query(decision.parameters)
            return

        if decision.intent == QueryIntent.EXCEL_ANALYTICS:
            self._handle_excel_analytics_query(decision.parameters)
            return

        # Default: Document RAG
        self._handle_rag_query(query)

    def _handle_rag_query(self, query: str) -> None:
        """Execute Document RAG retrieval and answer generation."""
        with self.console.status("[bold cyan]Searching documents & generating grounded response...", spinner="dots"):
            response = self.rag.query(query)

        self.console.print("\n[bold cyan]Cognify:[/bold cyan]")
        self.console.print(response.answer)

        if response.sources:
            self.console.print("\n[bold white]Sources:[/bold white]")
            for src in response.sources:
                self.console.print(f"  • [green]{src}[/green]")
        self.console.print()

    def _handle_excel_analytics_query(self, params: dict[str, Any]) -> None:
        """Execute single-file Pandas numerical computation."""
        op = params.get("operation", "sum")
        metric = params.get("metric", "revenue")
        group_by = params.get("group_by")
        wb_name = params.get("workbook")

        with self.console.status("[bold cyan]Executing Pandas calculation...", spinner="dots"):
            if group_by:
                if op == "max":
                    result = self.analytics.find_highest_or_lowest(
                        group_by_col=group_by,
                        metric_col=metric,
                        find_highest=True,
                        workbook_name=wb_name,
                    )
                elif op == "min":
                    result = self.analytics.find_highest_or_lowest(
                        group_by_col=group_by,
                        metric_col=metric,
                        find_highest=False,
                        workbook_name=wb_name,
                    )
                else:
                    result = self.analytics.group_by_aggregate(
                        group_by_col=group_by,
                        metric_col=metric,
                        operation=op,
                        workbook_name=wb_name,
                    )
            else:
                result = self.analytics.calculate_summary_metric(
                    metric_col=metric,
                    operation=op,
                    workbook_name=wb_name,
                )

        self.console.print("\n[bold cyan]Cognify:[/bold cyan]")
        if result.error:
            self.console.print(f"[bold red]Error:[/bold red] {result.error}")
        else:
            self.console.print(result.summary_text)
            if result.table is not None and not result.table.empty:
                table = Table(border_style="cyan")
                for col in result.table.columns:
                    table.add_column(str(col), style="white")
                for _, row in result.table.iterrows():
                    table.add_row(*[str(val) for val in row])
                self.console.print(table)

            if result.sources:
                self.console.print("\n[bold white]Sources:[/bold white]")
                for src in result.sources:
                    self.console.print(f"  • [green]{src}[/green]")
        self.console.print()

    def _handle_cross_file_query(self, params: dict[str, Any]) -> None:
        """Execute cross-workbook comparative calculation."""
        file1 = params.get("file1", "sales_2025.xlsx")
        file2 = params.get("file2", "sales_2026.xlsx")
        metric = params.get("metric", "revenue")
        group_by = params.get("group_by")

        with self.console.status("[bold cyan]Comparing workbooks with Pandas...", spinner="dots"):
            result = self.cross_analyzer.compare_workbooks(
                file1_name=file1,
                file2_name=file2,
                metric_col=metric,
                group_by_col=group_by,
            )

        self.console.print("\n[bold cyan]Cognify:[/bold cyan]")
        if result.error:
            self.console.print(f"[bold red]Error:[/bold red] {result.error}")
        else:
            self.console.print(result.summary_text)

            if result.comparison_table is not None and not result.comparison_table.empty:
                table = Table(title="Comparative Summary", border_style="cyan")
                for col in result.comparison_table.columns:
                    table.add_column(str(col), style="white")
                for _, row in result.comparison_table.iterrows():
                    table.add_row(*[str(val) for val in row])
                self.console.print(table)

            if result.category_breakdown is not None and not result.category_breakdown.empty:
                table_break = Table(title=f"Breakdown by {group_by.title() if group_by else 'Category'}", border_style="blue")
                for col in result.category_breakdown.columns:
                    table_break.add_column(str(col), style="white")
                for _, row in result.category_breakdown.iterrows():
                    table_break.add_row(*[str(val) for val in row])
                self.console.print(table_break)

            self.console.print("\n[bold white]Sources:[/bold white]")
            for src in result.sources:
                self.console.print(f"  • [green]{src}[/green]")
        self.console.print()

    def _handle_chart_query(self, query: str, params: dict[str, Any]) -> None:
        """Generate requested chart and display saved file path."""
        chart_type = params.get("chart_type", "bar")
        cat_col = params.get("category_col", "region")
        val_col = params.get("metric_col", "revenue")

        # Pick appropriate workbook from registry
        workbooks = self.excel_registry.list_workbooks()
        if not workbooks:
            self.console.print("\n[bold yellow]Cognify:[/bold yellow] No spreadsheet data available to generate charts.\n")
            return

        # Use first workbook or one mentioned
        target_wb = workbooks[0]
        sheet_data = self.excel_registry.get_sheet(target_wb)
        if not sheet_data:
            self.console.print("\n[bold yellow]Cognify:[/bold yellow] Could not access worksheet data for chart.\n")
            return

        df = sheet_data.df

        # Resolve columns with fuzzy match
        matched_cat = self.analytics._find_column(df, cat_col)
        matched_val = self.analytics._find_column(df, val_col)

        if not matched_cat or not matched_val:
            avail = ", ".join(df.columns)
            self.console.print(
                f"\n[bold yellow]Cognify:[/bold yellow] Could not match chart columns '{cat_col}' or '{val_col}'. "
                f"Available in {target_wb}: {avail}\n"
            )
            return

        try:
            with self.console.status("[bold cyan]Rendering visualization with Matplotlib...", spinner="dots"):
                if chart_type == "line":
                    chart_path = self.chart_generator.create_line_chart(
                        df, x_col=matched_cat, y_col=matched_val, title=f"{matched_val} Trend ({target_wb})"
                    )
                elif chart_type == "pie":
                    chart_path = self.chart_generator.create_pie_chart(
                        df, category_col=matched_cat, value_col=matched_val, title=f"{matched_val} Share ({target_wb})"
                    )
                else:
                    chart_path = self.chart_generator.create_bar_chart(
                        df, category_col=matched_cat, value_col=matched_val, title=f"{matched_val} by {matched_cat} ({target_wb})"
                    )

            self.console.print("\n[bold cyan]Cognify:[/bold cyan]")
            self.console.print(f"[bold green]Chart successfully saved:[/bold green]")
            self.console.print(f"  [cyan]{chart_path}[/cyan]")
            self.console.print("\n[bold white]Sources:[/bold white]")
            self.console.print(f"  • [green]{target_wb}[/green]\n")

        except Exception as e:
            self.console.print(f"\n[bold red]Chart Generation Error:[/bold red] {e}\n")

    def run(self) -> None:
        """Start interactive continuous chat loop."""
        self.startup()

        while True:
            try:
                user_input = self.console.input("[bold green]You:[/bold green] ").strip()
                if not user_input:
                    continue

                cmd = user_input.lower()
                if cmd in ["/exit", "/quit", "exit", "quit"]:
                    self.console.print("[cyan]Goodbye! Thank you for using Cognify.[/cyan]")
                    break
                elif cmd == "/help":
                    self.print_help()
                elif cmd == "/status":
                    self.print_status_table()
                elif cmd == "/files":
                    self.list_files()
                elif cmd == "/sources":
                    self.list_sources()
                elif cmd == "/reindex":
                    self.reindex()
                else:
                    self.process_query(user_input)

            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[cyan]Session terminated. Goodbye![/cyan]")
                break
            except Exception as e:
                logger.exception("Unexpected error in main loop: %s", e)
                self.console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")
