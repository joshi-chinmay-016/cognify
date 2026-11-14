"""Application configuration module for Cognify.

Loads settings from environment variables and provides structured,
type-safe access to application configuration and paths.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root if present
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class AppConfig:
    """Cognify configuration parameters."""

    # Project Paths
    root_dir: Path = field(default_factory=lambda: PROJECT_ROOT)
    downloads_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "downloads")
    processed_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "processed")
    vector_store_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "vector_store")
    charts_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "charts")

    # Google Drive Integration
    google_drive_folder_id: str = field(
        default_factory=lambda: os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    )
    google_credentials_file: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    )
    google_token_file: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    )
    google_scopes: list[str] = field(
        default_factory=lambda: ["https://www.googleapis.com/auth/drive.readonly"]
    )

    # Local LLM Integration (Ollama)
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip()
    )
    llm_temperature: float = 0.1
    llm_timeout: int = 60

    # Embeddings & Vector Storage
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2").strip()
    )
    chunk_size: int = field(
        default_factory=lambda: int(os.getenv("CHUNK_SIZE", "800"))
    )
    chunk_overlap: int = field(
        default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "150"))
    )
    top_k: int = field(
        default_factory=lambda: int(os.getenv("TOP_K", "5"))
    )

    # Retrieval similarity threshold (L2 distance or cosine threshold)
    similarity_threshold: float = 1.5

    def ensure_directories(self) -> None:
        """Create necessary data, vector store, and chart directories if not existing."""
        for d in [self.downloads_dir, self.processed_dir, self.vector_store_dir, self.charts_dir]:
            d.mkdir(parents=True, exist_ok=True)


# Global singleton instance
config = AppConfig()
