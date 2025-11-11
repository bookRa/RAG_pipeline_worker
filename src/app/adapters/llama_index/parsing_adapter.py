from __future__ import annotations

import json
import logging
from typing import Any

from ...application.interfaces import ParsingLLM
from ...config import PromptSettings
from ...parsing.schemas import ParsedPage, ParsedParagraph
from ...prompts.loader import load_prompt
from .utils import extract_response_text

logger = logging.getLogger(__name__)


class ImageAwareParsingAdapter(ParsingLLM):
    """Calls an LLM to convert a page (text + optional pixmap) into structured content."""

    def __init__(self, llm: Any, prompt_settings: PromptSettings) -> None:
        self._llm = llm
        self._system_prompt = load_prompt(prompt_settings.parsing_system_prompt_path)
        self._user_prompt_template = load_prompt(prompt_settings.parsing_user_prompt_path)

    def parse_page(
        self,
        *,
        document_id: str,
        page_number: int,
        raw_text: str,
        pixmap_path: str | None = None,
    ) -> ParsedPage:
        payload = {
            "document_id": document_id,
            "page_number": page_number,
            "raw_text": raw_text,
            "pixmap_path": pixmap_path,
        }
        prompt = f"{self._system_prompt}\n\n{self._user_prompt_template}\n\n{json.dumps(payload)}"
        try:
            completion = self._llm.complete(prompt)
            completion_text = extract_response_text(completion)
            data = json.loads(completion_text)
            return ParsedPage.model_validate(data)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Falling back to raw parsing for doc=%s page=%s: %s", document_id, page_number, exc)
            return ParsedPage(
                document_id=document_id,
                page_number=page_number,
                raw_text=raw_text,
                paragraphs=[
                    ParsedParagraph(order=0, text=raw_text.strip() or "(empty page)"),
                ],
            )
