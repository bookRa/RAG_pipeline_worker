from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from ..application.interfaces import ObservabilityRecorder

LOGGER_NAME = "rag_pipeline"


def _build_logger() -> logging.Logger:
    """Build logger that respects the centralized LOG_LEVEL configuration."""
    from .logging_setup import get_log_level_from_settings
    
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    # Use centralized log level from settings
    logger.setLevel(get_log_level_from_settings())
    return logger


class LoggingObservabilityRecorder(ObservabilityRecorder):
    """Adapter that writes structured events to Python logging."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _build_logger()

    def record_event(
        self, 
        stage: str, 
        details: Mapping[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Record event with human-readable formatted output."""
        log_parts = [f"stage={stage}"]
        if trace_id:
            log_parts.append(f"trace_id={trace_id}")
        if details:
            # Use pretty-printed JSON for readability
            payload = json.dumps(details, indent=2, ensure_ascii=False)
            log_parts.append(f"details=\n{payload}")
            self._logger.info(" ".join(log_parts))
        else:
            self._logger.info(" ".join(log_parts))
