from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from ..application.interfaces import ObservabilityRecorder

LOGGER_NAME = "rag_pipeline"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class LoggingObservabilityRecorder(ObservabilityRecorder):
    """Adapter that writes structured events to Python logging."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _build_logger()

    def record_event(self, stage: str, details: Mapping[str, Any] | None = None) -> None:
        """Record event with human-readable formatted output."""
        if details:
            # Use pretty-printed JSON for readability
            payload = json.dumps(details, indent=2, ensure_ascii=False)
            self._logger.info("stage=%s details=\n%s", stage, payload)
        else:
            self._logger.info("stage=%s (no details)", stage)
