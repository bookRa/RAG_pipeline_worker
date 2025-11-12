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
from ...parsing.schemas import ParsedPage
from ...prompts.loader import load_prompt

logger = logging.getLogger("rag_pipeline.llm")


class ImageAwareParsingAdapter(ParsingLLM):
    """Calls an LLM to convert a page image into structured content."""

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
        # Build system prompt from loaded prompts (combine system + user prompts)
        system_prompt = load_prompt(prompt_settings.parsing_system_prompt_path)
        user_prompt_template = load_prompt(prompt_settings.parsing_user_prompt_path)
        # Combine system and user prompts into a single system message
        # Include document_id and page_number placeholders for the LLM to use
        self._system_prompt = f"{system_prompt}\n\n{user_prompt_template}"

    def parse_page(
        self,
        *,
        document_id: str,
        page_number: int,
        raw_text: str = "",  # Optional, not used for image-only parsing
        pixmap_path: str | None = None,
    ) -> ParsedPage:
        # Require pixmap for vision parsing (image-only mode)
        if not pixmap_path:
            logger.warning(
                "No pixmap provided for doc=%s page=%s, returning empty page",
                document_id,
                page_number,
            )
            return ParsedPage(
                document_id=document_id,
                page_number=page_number,
                raw_text="",
                components=[],
            )
        
        try:
            if self._use_structured_outputs:
                parsed_page = self._parse_with_vision_structured(document_id, page_number, pixmap_path)
                if parsed_page:
                    self._log_trace(document_id, page_number, pixmap_path, parsed_page)
                    return parsed_page
            else:
                # Fallback to non-structured parsing if disabled
                parsed_page = self._parse_without_structured_llm(document_id, page_number, pixmap_path)
                if parsed_page:
                    self._log_trace(document_id, page_number, pixmap_path, parsed_page)
                    return parsed_page
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception(
                "Falling back to empty page for doc=%s page=%s pixmap=%s: %s",
                document_id,
                page_number,
                pixmap_path,
                exc,
            )
        
        return ParsedPage(
            document_id=document_id,
            page_number=page_number,
            raw_text="",
            components=[],
        )

    def _parse_with_vision_structured(
        self,
        document_id: str,
        page_number: int,
        pixmap_path: str,
    ) -> ParsedPage | None:
        """Parse using OpenAI LLM (GPT-4o-mini) with vision - image-only mode."""
        path_obj = Path(pixmap_path) if pixmap_path else None
        logger.info(
            "parsing_page_image llm=%s document_id=%s page=%s exists=%s size=%s bytes",
            self._llm.__class__.__name__,
            document_id,
            page_number,
            path_obj.exists() if path_obj else False,
            path_obj.stat().st_size if path_obj and path_obj.exists() else None,
        )
        
        try:
            # Add document_id and page_number to system prompt
            system_prompt_with_context = (
                f"{self._system_prompt}\n\n"
                f"Document ID: {document_id}\n"
                f"Page Number: {page_number}"
            )
            
            # Add JSON schema instruction to system prompt for structured output
            schema = ParsedPage.model_json_schema()
            schema_instruction = (
                "\n\nRespond ONLY with valid JSON that matches this schema:\n"
                f"{json.dumps(schema, indent=2)}\n"
                "Do not include any markdown formatting, code fences, or explanations."
            )
            full_system_prompt = system_prompt_with_context + schema_instruction
            
            # Encode image as base64 string (not data URL)
            image_data = encode_image(pixmap_path)
            
            # Use system message + user message with image
            # System message contains instructions, user message contains the image
            messages = [
                ChatMessage(role="system", content=full_system_prompt),
                ChatMessage(
                    role="user",
                    content=[
                        ImageBlock(image=image_data, image_mimetype="image/png"),
                    ],
                ),
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
                
                parsed_page = ParsedPage.model_validate_json(content)
                # Ensure document_id and page_number match (LLM might get them wrong)
                parsed_page = parsed_page.model_copy(
                    update={
                        "document_id": document_id,
                        "page_number": page_number,
                    }
                )
                return parsed_page
        except Exception as exc:
            logger.warning(
                "Structured vision LLM parsing failed for doc=%s page=%s: %s",
                document_id,
                page_number,
                exc,
            )
        return None
    
    def _parse_without_structured_llm(
        self,
        document_id: str,
        page_number: int,
        pixmap_path: str,
    ) -> ParsedPage | None:
        """Fallback parsing without structured outputs (for testing or when disabled)."""
        try:
            # Add document_id and page_number to system prompt
            system_prompt_with_context = (
                f"{self._system_prompt}\n\n"
                f"Document ID: {document_id}\n"
                f"Page Number: {page_number}"
            )
            
            # Encode image as base64 string
            image_data = encode_image(pixmap_path)
            
            # Use system message + user message with image
            messages = [
                ChatMessage(role="system", content=system_prompt_with_context),
                ChatMessage(
                    role="user",
                    content=[
                        ImageBlock(image=image_data, image_mimetype="image/png"),
                    ],
                ),
            ]
            
            response = self._llm.chat(messages)
            
            # Try to extract and parse JSON manually
            if hasattr(response, "message") and hasattr(response.message, "content"):
                content = response.message.content
                if isinstance(content, list):
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
                
                parsed_page = ParsedPage.model_validate_json(content)
                parsed_page = parsed_page.model_copy(
                    update={
                        "document_id": document_id,
                        "page_number": page_number,
                    }
                )
                return parsed_page
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
        parsed_page: ParsedPage,
    ) -> None:
        """Log parsing trace in human-readable format."""
        from ...parsing.schemas import ParsedTextComponent, ParsedImageComponent, ParsedTableComponent
        
        logger.info("=" * 80)
        logger.info("PARSING TRACE - Document: %s, Page: %s", document_id, page_number)
        logger.info("=" * 80)
        logger.info("Pixmap Path: %s", pixmap_path)
        logger.info("-" * 80)
        logger.info("RAW TEXT (Markdown):")
        logger.info("-" * 80)
        logger.info("%s", parsed_page.raw_text[:1000] + ("..." if len(parsed_page.raw_text) > 1000 else ""))
        logger.info("-" * 80)
        logger.info("COMPONENTS: %d (ordered by layout)", len(parsed_page.components))
        
        # Show components in order
        for i, component in enumerate(parsed_page.components[:10], 1):  # Show first 10
            if isinstance(component, ParsedTextComponent):
                text_type_str = f" ({component.text_type})" if component.text_type else ""
                logger.info("  [%d] TEXT%s - order=%d: %s", 
                          i, text_type_str, component.order,
                          component.text[:150] + ("..." if len(component.text) > 150 else ""))
            elif isinstance(component, ParsedImageComponent):
                logger.info("  [%d] IMAGE - order=%d", i, component.order)
                logger.info("      description: %s", component.description[:150] + ("..." if len(component.description) > 150 else ""))
                if component.recognized_text:
                    logger.info("      recognized_text: %s", component.recognized_text[:100] + ("..." if len(component.recognized_text) > 100 else ""))
            elif isinstance(component, ParsedTableComponent):
                caption_str = f" - {component.caption}" if component.caption else ""
                logger.info("  [%d] TABLE - order=%d%s: %d rows", 
                          i, component.order, caption_str, len(component.rows))
                if component.rows:
                    # Show first row keys as column preview
                    first_row = component.rows[0]
                    cols = ", ".join(list(first_row.keys())[:5])
                    if len(first_row) > 5:
                        cols += f" ... ({len(first_row)} total columns)"
                    logger.info("      columns: %s", cols)
        
        if len(parsed_page.components) > 10:
            logger.info("  ... (%d more components)", len(parsed_page.components) - 10)
        
        # Summary by type
        text_count = len([c for c in parsed_page.components if isinstance(c, ParsedTextComponent)])
        image_count = len([c for c in parsed_page.components if isinstance(c, ParsedImageComponent)])
        table_count = len([c for c in parsed_page.components if isinstance(c, ParsedTableComponent)])
        logger.info("-" * 80)
        logger.info("SUMMARY: %d text, %d images, %d tables", text_count, image_count, table_count)
        logger.info("=" * 80)
