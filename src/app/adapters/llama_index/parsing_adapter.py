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

    def __init__(
        self,
        llm: Any,
        prompt_settings: PromptSettings,
        use_structured_outputs: bool = True,
    ) -> None:
        self._llm = llm
        self._system_prompt = load_prompt(prompt_settings.parsing_system_prompt_path)
        self._user_prompt_template = load_prompt(prompt_settings.parsing_user_prompt_path)
        self._use_structured_outputs = use_structured_outputs
        self._schema = ParsedPage.model_json_schema()

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
        completion_text = ""
        try:
            completion = self._llm.complete(
                prompt,
                **self._structured_kwargs("parsed_page", self._schema),
            )
            completion_text = extract_response_text(completion)
            data = json.loads(completion_text)
            return ParsedPage.model_validate(data)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning(
                "Falling back to raw parsing for doc=%s page=%s: %s\nRaw response snippet: %s",
                document_id,
                page_number,
                exc,
                completion_text[:500],
            )
            return ParsedPage(
                document_id=document_id,
                page_number=page_number,
                raw_text=raw_text,
                paragraphs=[
                    ParsedParagraph(order=0, text=raw_text.strip() or "(empty page)"),
                ],
            )

    def _structured_kwargs(self, name: str, schema: dict[str, Any]) -> dict[str, Any]:
        if not self._use_structured_outputs:
            return {}
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": name,
                    "schema": schema,
                },
            }
        }
