from __future__ import annotations

import json
import logging
from typing import Any

from llama_index.core.schema import ImageDocument

from ...application.interfaces import ParsingLLM
from ...config import PromptSettings
from ...parsing.schemas import ParsedPage, ParsedParagraph
from ...prompts.loader import load_prompt
from .utils import extract_response_text

logger = logging.getLogger("rag_pipeline.llm")


class ImageAwareParsingAdapter(ParsingLLM):
    """Calls an LLM to convert a page (text + optional pixmap) into structured content."""

    def __init__(
        self,
        llm: Any,
        prompt_settings: PromptSettings,
        vision_llm: Any | None = None,
        use_structured_outputs: bool = True,
    ) -> None:
        self._llm = llm
        self._vision_llm = vision_llm
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
            completion = self._complete(prompt, pixmap_path)
            completion_text = extract_response_text(completion)
            self._log_trace(document_id, page_number, pixmap_path, prompt, completion_text)
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

    def _complete(self, prompt: str, pixmap_path: str | None) -> Any:
        kwargs = self._structured_kwargs("parsed_page", self._schema)
        if pixmap_path and self._vision_llm:
            image_doc = ImageDocument(image_path=pixmap_path)
            return self._vision_llm.complete(
                prompt,
                image_documents=[image_doc],
                **kwargs,
            )
        if pixmap_path and not self._vision_llm:
            logger.warning(
                "Pixmap path provided but multi-modal LLM is unavailable. Falling back to text-only parsing."
            )
        return self._llm.complete(prompt, **kwargs)

    def _log_trace(
        self,
        document_id: str,
        page_number: int,
        pixmap_path: str | None,
        prompt: str,
        response: str,
    ) -> None:
        payload = {
            "document_id": document_id,
            "page_number": page_number,
            "pixmap_path": pixmap_path,
            "prompt": prompt,
            "response": response,
        }
        logger.info("parsing_llm_trace %s", json.dumps(payload, ensure_ascii=False))
