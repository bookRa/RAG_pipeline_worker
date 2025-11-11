from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from ...application.interfaces import CleaningLLM
from ...config import PromptSettings
from ...parsing.schemas import CleanedPage, CleanedSegment, ParsedPage
from ...prompts.loader import load_prompt

logger = logging.getLogger(__name__)


class CleaningAdapter(CleaningLLM):
    """LLM-backed cleaner that normalizes parsed page content."""

    def __init__(self, llm: Any, prompt_settings: PromptSettings) -> None:
        self._llm = llm
        self._system_prompt = load_prompt(prompt_settings.cleaning_system_prompt_path)
        self._user_prompt_template = load_prompt(prompt_settings.cleaning_user_prompt_path)

    def clean_page(self, parsed_page: ParsedPage) -> CleanedPage:
        request = {
            "document_id": parsed_page.document_id,
            "page_number": parsed_page.page_number,
            "paragraphs": [para.model_dump() for para in parsed_page.paragraphs],
            "tables": [table.model_dump() for table in parsed_page.tables],
        }
        prompt = f"{self._system_prompt}\n\n{self._user_prompt_template}\n\n{json.dumps(request)}"
        try:
            completion = self._llm.complete(prompt)
            data = json.loads(completion)
            return CleanedPage.model_validate(data)
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.warning(
                "Invalid cleaning response for doc=%s page=%s: %s",
                parsed_page.document_id,
                parsed_page.page_number,
                exc,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Cleaning adapter failed for doc=%s page=%s: %s",
                parsed_page.document_id,
                parsed_page.page_number,
                exc,
            )

        # Fallback: return paragraphs verbatim as cleaned segments
        return CleanedPage(
            document_id=parsed_page.document_id,
            page_number=parsed_page.page_number,
            segments=[
                CleanedSegment(segment_id=para.id, text=para.text)
                for para in parsed_page.paragraphs
            ],
        )
