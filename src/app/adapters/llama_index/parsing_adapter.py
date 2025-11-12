from __future__ import annotations

import json
import logging
from typing import Any
from pathlib import Path

from llama_index.core.llms import ChatMessage
from llama_index.core.base.llms.types import TextBlock, ImageBlock
from llama_index.core.prompts import PromptTemplate
from llama_index.core.multi_modal_llms.generic_utils import encode_image

from ...application.interfaces import ParsingLLM
from ...config import PromptSettings
from ...parsing.schemas import ParsedPage, ParsedParagraph
from ...prompts.loader import load_prompt

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
        self._use_structured_outputs = use_structured_outputs
        # Build prompt template from loaded prompts
        system_prompt = load_prompt(prompt_settings.parsing_system_prompt_path)
        user_prompt_template = load_prompt(prompt_settings.parsing_user_prompt_path)
        # Combine system and user prompts into a single template
        full_prompt_text = f"{system_prompt}\n\n{user_prompt_template}\n\n{{payload_json}}"
        self._prompt_template = PromptTemplate(full_prompt_text)

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
        payload_json = json.dumps(payload)
        
        try:
            if self._use_structured_outputs:
                parsed_page = self._parse_with_structured_llm(document_id, page_number, payload_json, pixmap_path)
                if parsed_page:
                    response_text = parsed_page.model_dump_json()
                    self._log_trace(document_id, page_number, pixmap_path, payload_json, response_text)
                    return parsed_page
            else:
                # Fallback to non-structured parsing if disabled
                parsed_page = self._parse_without_structured_llm(document_id, page_number, payload_json, pixmap_path)
                if parsed_page:
                    response_text = parsed_page.model_dump_json()
                    self._log_trace(document_id, page_number, pixmap_path, payload_json, response_text)
                    return parsed_page
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception(
                "Falling back to raw parsing for doc=%s page=%s pixmap=%s: %s",
                document_id,
                page_number,
                pixmap_path,
                exc,
            )
        
        return ParsedPage(
            document_id=document_id,
            page_number=page_number,
            raw_text=raw_text,
            paragraphs=[
                ParsedParagraph(order=0, text=raw_text.strip() or "(empty page)"),
            ],
        )

    def _parse_with_structured_llm(
        self,
        document_id: str,
        page_number: int,
        payload_json: str,
        pixmap_path: str | None = None,
    ) -> ParsedPage | None:
        """Parse using LlamaIndex structured LLM APIs."""
        # Use vision if pixmap is provided (same LLM handles both text and vision)
        if pixmap_path:
            return self._parse_with_vision_structured(document_id, page_number, payload_json, pixmap_path)
        else:
            return self._parse_with_text_structured(document_id, page_number, payload_json)
    
    def _parse_with_vision_structured(
        self,
        document_id: str,
        page_number: int,
        payload_json: str,
        pixmap_path: str,
    ) -> ParsedPage | None:
        """Parse using OpenAI LLM (GPT-4o-mini) with vision via structured_predict."""
        path_obj = Path(pixmap_path) if pixmap_path else None
        logger.info(
            "routing_pixmap_to_vision_llm llm=%s document_id=%s page=%s exists=%s size=%s bytes",
            self._llm.__class__.__name__,
            document_id,
            page_number,
            path_obj.exists() if path_obj else False,
            path_obj.stat().st_size if path_obj and path_obj.exists() else None,
        )
        
        try:
            # Build prompt text from template
            prompt_text = self._prompt_template.format(payload_json=payload_json)
            
            # Add JSON schema instruction to prompt for structured output
            schema = ParsedPage.model_json_schema()
            schema_instruction = (
                "\n\nRespond ONLY with valid JSON that matches this schema:\n"
                f"{json.dumps(schema, indent=2)}\n"
                "Do not include any markdown formatting, code fences, or explanations."
            )
            enhanced_prompt = prompt_text + schema_instruction
            
            # Encode image as base64 string (not data URL)
            image_data = encode_image(pixmap_path)
            
            # Call OpenAI LLM chat() directly (not through structured_llm wrapper)
            # Use TextBlock and ImageBlock for proper LlamaIndex format
            # ImageBlock.image expects base64 string directly, not a data URL
            messages = [
                ChatMessage(
                    role="user",
                    content=[
                        TextBlock(text=enhanced_prompt),
                        ImageBlock(image=image_data, image_mimetype="image/png"),
                    ],
                )
            ]
            
            # Call chat() directly on the base LLM
            response = self._llm.chat(messages)
            
            # Extract JSON from response and parse
            if hasattr(response, "message") and hasattr(response.message, "content"):
                content = response.message.content
                # Handle both string and list content
                if isinstance(content, list):
                    # Extract text from content list
                    text_parts = [
                        item.get("text", "") 
                        for item in content 
                        if isinstance(item, dict) and item.get("type") == "text"
                    ]
                    content = "".join(text_parts)
                elif not isinstance(content, str):
                    content = str(content)
            elif hasattr(response, "text"):
                content = response.text
            else:
                content = str(response)
            
            if content:
                # Try to extract JSON from markdown code fences if present
                if "```json" in content:
                    start = content.find("```json") + 7
                    end = content.find("```", start)
                    content = content[start:end].strip()
                elif "```" in content:
                    start = content.find("```") + 3
                    end = content.find("```", start)
                    content = content[start:end].strip()
                
                return ParsedPage.model_validate_json(content)
        except Exception as exc:
            logger.warning(
                "Structured vision LLM parsing failed for doc=%s page=%s: %s",
                document_id,
                page_number,
                exc,
            )
        return None
    
    def _parse_with_text_structured(
        self,
        document_id: str,
        page_number: int,
        payload_json: str,
    ) -> ParsedPage | None:
        """Parse using text-only structured LLM."""
        logger.info(
            "routing_text_llm llm=%s document_id=%s page=%s structured=True",
            self._llm.__class__.__name__,
            document_id,
            page_number,
        )
        
        try:
            # Create structured LLM wrapper
            structured_llm = self._llm.as_structured_llm(ParsedPage)
            
            # Build prompt text from template
            prompt_text = self._prompt_template.format(payload_json=payload_json)
            
            # Use structured_predict for more control, or complete() for simpler usage
            # structured_predict allows us to pass the prompt template directly
            response = structured_llm.complete(prompt_text)
            
            # Extract Pydantic object from response.raw
            if hasattr(response, "raw") and isinstance(response.raw, ParsedPage):
                return response.raw
            elif hasattr(response, "text"):
                # Fallback: try to parse from text
                return ParsedPage.model_validate_json(response.text)
        except Exception as exc:
            logger.warning(
                "Structured text LLM parsing failed for doc=%s page=%s: %s",
                document_id,
                page_number,
                exc,
            )
        return None
    
    def _parse_without_structured_llm(
        self,
        document_id: str,
        page_number: int,
        payload_json: str,
        pixmap_path: str | None = None,
    ) -> ParsedPage | None:
        """Fallback parsing without structured outputs (for testing or when disabled)."""
        prompt_text = self._prompt_template.format(payload_json=payload_json)
        
        try:
            if pixmap_path:
                # Vision without structured outputs - use chat() with ImageBlock
                image_data = encode_image(pixmap_path)
                messages = [
                    ChatMessage(
                        role="user",
                        content=[
                            TextBlock(text=prompt_text),
                            ImageBlock(image=image_data, image_mimetype="image/png"),
                        ],
                    )
                ]
                response = self._llm.chat(messages)
            else:
                # Text-only without structured outputs
                response = self._llm.complete(prompt_text)
            
            # Try to extract and parse JSON manually
            if hasattr(response, "message") and hasattr(response.message, "content"):
                content = response.message.content
            elif hasattr(response, "text"):
                content = response.text
            else:
                content = str(response)
            
            if content:
                # Try to extract JSON from markdown code fences if present
                if "```json" in content:
                    start = content.find("```json") + 7
                    end = content.find("```", start)
                    content = content[start:end].strip()
                elif "```" in content:
                    start = content.find("```") + 3
                    end = content.find("```", start)
                    content = content[start:end].strip()
                
                return ParsedPage.model_validate_json(content)
        except Exception as exc:
            logger.warning(
                "Non-structured parsing failed for doc=%s page=%s: %s",
                document_id,
                page_number,
                exc,
            )
        return None

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
