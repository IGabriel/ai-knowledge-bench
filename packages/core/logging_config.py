"""Logging configuration."""
import logging
import sys
from typing import Optional

from packages.core.config import get_settings


def setup_logging(name: Optional[str] = None, level: Optional[str] = None) -> logging.Logger:
    """Setup logging with consistent format."""
    settings = get_settings()
    log_level = level or settings.app_log_level

    # Create logger
    logger = logging.getLogger(name or "ai-knowledge-bench")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level.upper()))

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    return logger
