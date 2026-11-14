"""Cognify Application Entry Point.

Run Cognify:
    python -m app.main
"""

from __future__ import annotations

import logging
import sys

from app.cli import CognifyCLI
from app.config import config


def setup_logging() -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(config.root_dir / "cognify.log", encoding="utf-8"),
        ],
    )


def main() -> None:
    """Launch Cognify interactive assistant."""
    setup_logging()
    app = CognifyCLI(config)
    app.run()


if __name__ == "__main__":
    main()

