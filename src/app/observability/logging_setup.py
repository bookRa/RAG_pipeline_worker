"""Centralized logging configuration for the RAG pipeline.

This module provides a single point of configuration for all logging in the application.
The log level is controlled via the LOG_LEVEL environment variable or .env file.

Usage:
    from src.app.observability.logging_setup import setup_logging
    
    # Call once at application startup (e.g., in main.py)
    setup_logging()

Configuration:
    Set LOG_LEVEL in your .env file:
    
    LOG_LEVEL=INFO    # Clean progress logs (default, recommended for production)
    LOG_LEVEL=DEBUG   # Verbose diagnostic logs (recommended for development/debugging)
    LOG_LEVEL=WARNING # Only warnings and errors
    LOG_LEVEL=ERROR   # Only errors
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

# Valid log levels
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Logger names used throughout the application
KNOWN_LOGGERS = [
    "rag_pipeline",                                    # Main pipeline logger
    "batch_pipeline",                                  # Batch processing logger
    "src.app.adapters.llama_index.bcai_llm",          # BCAI LLM adapter
    "src.app.adapters.llama_index.parsing_adapter",   # Parsing adapter
    "src.app.adapters.llama_index.cleaning_adapter",  # Cleaning adapter
    "src.app.services",                               # Services
    "src.app.api",                                    # API routes
]


def get_log_level_from_settings() -> int:
    """Get the log level from application settings.
    
    Returns:
        The logging level constant (e.g., logging.DEBUG, logging.INFO)
    """
    # Import here to avoid circular imports
    from ..config import settings
    
    level_str = settings.log_level.upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    
    return level_map.get(level_str, logging.INFO)


def setup_logging() -> None:
    """Configure logging for the entire application.
    
    This function should be called once at application startup.
    It configures:
    - Root logger level from settings.log_level
    - Consistent formatting across all loggers
    - Reduces noise from third-party libraries
    
    The log level is read from the LOG_LEVEL environment variable (via .env file).
    """
    from ..config import settings
    
    log_level = get_log_level_from_settings()
    level_name = logging.getLevelName(log_level)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler with formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Use detailed format for DEBUG, cleaner format for INFO+
    if log_level == logging.DEBUG:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S"
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Configure known application loggers
    for logger_name in KNOWN_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.setLevel(log_level)
        # Don't propagate to root to avoid duplicate logs
        # (these loggers add their own handlers in _build_logger() and BatchObservabilityRecorder)
        logger.propagate = False
    
    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("langfuse").setLevel(logging.WARNING)
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)
    
    # Log the configuration (visible at INFO+ levels)
    startup_logger = logging.getLogger("rag_pipeline.startup")
    startup_logger.info(f"Logging configured: level={level_name} (from LOG_LEVEL={settings.log_level})")
    
    if log_level == logging.DEBUG:
        startup_logger.debug(
            f"DEBUG logging enabled - verbose output will be shown for: {', '.join(KNOWN_LOGGERS)}"
        )


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the application's configured level.
    
    This is a convenience function that ensures the logger respects
    the application's log level setting.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    # Level is already set by setup_logging(), but set it explicitly
    # in case this is called before setup_logging()
    logger.setLevel(get_log_level_from_settings())
    return logger

