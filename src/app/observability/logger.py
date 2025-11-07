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
        payload = json.dumps(details or {})
        self._logger.info("stage=%s details=%s", stage, payload)


class NullObservabilityRecorder(ObservabilityRecorder):
    """No-op recorder used by default in tests."""

    def record_event(self, stage: str, details: Mapping[str, Any] | None = None) -> None:  # noqa: D401
        return None
