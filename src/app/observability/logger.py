import json
import logging
from typing import Any, Optional

LOGGER_NAME = "rag_pipeline"

logger = logging.getLogger(LOGGER_NAME)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def log_event(stage: str, details: Optional[dict[str, Any]] = None) -> None:
    payload = json.dumps(details or {})
    logger.info("stage=%s details=%s", stage, payload)
