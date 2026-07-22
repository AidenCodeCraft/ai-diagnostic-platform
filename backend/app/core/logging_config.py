"""Centralized logging configuration — file rotation + console output.

Usage:
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("something happened", extra={"user_id": 123})
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FILE = LOG_DIR / "app.log"

# Default format for file logs
FILE_FORMAT = (
    "[%(asctime)s] [%(levelname)-5s] [%(name)s] [%(filename)s:%(lineno)d] %(message)s"
)

# Console format (more compact — no file:line)
CONSOLE_FORMAT = (
    "[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s"
)

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Setup ─────────────────────────────────────────────────────

_configured = False


def setup_logging(level: int | str = logging.INFO) -> None:
    """Configure root logger with file rotation + console output.

    Called once at application startup (in main.py).
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(level)

    # Clear any previously attached handlers
    root.handlers.clear()

    # ── File handler (daily rotation, keep 30 days) ──────────
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename=str(LOG_FILE),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # File keeps everything
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(file_handler)

    # ── Console handler ─────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(console_handler)

    # Shhh noisy libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a module.

    Uses Python's standard hierarchical naming:
        get_logger(__name__) → "app.services.auth.auth_service"
    """
    return logging.getLogger(name)
