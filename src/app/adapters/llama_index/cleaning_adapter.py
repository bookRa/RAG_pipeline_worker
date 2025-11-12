from __future__ import annotations

import json
import logging
from typing import Any

from llama_index.core.prompts import PromptTemplate

from ...application.interfaces import CleaningLLM
from ...config import PromptSettings
from ...parsing.schemas import (
    CleanedPage,
    CleanedSegment,
    ParsedPage,
    ParsedTextComponent,
    ParsedImageComponent,
    ParsedTableComponent,
)
from ...prompts.loader import load_prompt

logger = logging.getLogger(__name__)


class CleaningAdapter(CleaningLLM):
    """LLM-backed cleaner that normalizes parsed page content."""

    def __init__(
        self,
        llm: Any,
        prompt_settings: PromptSettings,
        use_structured_outputs: bool = True,
    ) -> None:
        self._llm = llm
        self._use_structured_outputs = use_structured_outputs
        # Build prompt template from loaded prompts
        system_prompt = load_prompt(prompt_settings.cleaning_system_prompt_path)
        user_prompt_template = load_prompt(prompt_settings.cleaning_user_prompt_path)
        # Combine system and user prompts into a single template
        full_prompt_text = f"{system_prompt}\n\n{user_prompt_template}\n\n{{request_json}}"
        self._prompt_template = PromptTemplate(full_prompt_text)

    def clean_page(self, parsed_page: ParsedPage) -> CleanedPage:
        # Build request with components instead of separate paragraphs/tables
        request = {
            "document_id": parsed_page.document_id,
            "page_number": parsed_page.page_number,
            "components": [self._component_to_dict(c) for c in parsed_page.components],
        }
        request_json = json.dumps(request)
        
        try:
            if self._use_structured_outputs:
                cleaned_page = self._clean_with_structured_llm(request_json, parsed_page)
                if cleaned_page:
                    return cleaned_page
            else:
                # Fallback to non-structured parsing if disabled
                cleaned_page = self._clean_without_structured_llm(request_json, parsed_page)
                if cleaned_page:
                    return cleaned_page
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Cleaning adapter failed for doc=%s page=%s: %s",
                parsed_page.document_id,
                parsed_page.page_number,
                exc,
            )

        # Fallback: extract text from all components and return as cleaned segments
        segments = []
        for component in parsed_page.components:
            if isinstance(component, ParsedTextComponent):
                segments.append(CleanedSegment(segment_id=component.id, text=component.text))
            elif isinstance(component, ParsedImageComponent):
                # Include recognized text and description for cleaning
                text_parts = []
                if component.recognized_text:
                    text_parts.append(component.recognized_text)
                if component.description:
                    text_parts.append(component.description)
                if text_parts:
                    segments.append(CleanedSegment(
                        segment_id=component.id,
                        text=" ".join(text_parts)
                    ))
            elif isinstance(component, ParsedTableComponent):
                # Extract text from all table row values
                row_texts = []
                for row in component.rows:
                    row_texts.extend(str(v) for v in row.values() if v)
                if row_texts:
                    segments.append(CleanedSegment(
                        segment_id=component.id,
                        text=" | ".join(row_texts)
                    ))
        
        return CleanedPage(
            document_id=parsed_page.document_id,
            page_number=parsed_page.page_number,
            segments=segments,
        )
    
    @staticmethod
    def _component_to_dict(component: ParsedTextComponent | ParsedImageComponent | ParsedTableComponent) -> dict:
        """Convert component to dict for JSON serialization."""
        base = component.model_dump()
        # Ensure type is included for discriminated union
        if "type" not in base:
            if isinstance(component, ParsedTextComponent):
                base["type"] = "text"
            elif isinstance(component, ParsedImageComponent):
                base["type"] = "image"
            elif isinstance(component, ParsedTableComponent):
                base["type"] = "table"
        return base
    
    def _clean_with_structured_llm(
        self,
        request_json: str,
        parsed_page: ParsedPage,
    ) -> CleanedPage | None:
        """Clean using LlamaIndex structured LLM APIs."""
        try:
            # Create structured LLM wrapper
            structured_llm = self._llm.as_structured_llm(CleanedPage)
            
            # Build prompt text from template
            prompt_text = self._prompt_template.format(request_json=request_json)
            
            # Use structured LLM complete method
            response = structured_llm.complete(prompt_text)
            
            # Extract Pydantic object from response.raw
            if hasattr(response, "raw") and isinstance(response.raw, CleanedPage):
                return response.raw
            elif hasattr(response, "text"):
                # Fallback: try to parse from text
                return CleanedPage.model_validate_json(response.text)
        except Exception as exc:
            logger.warning(
                "Structured cleaning failed for doc=%s page=%s: %s",
                parsed_page.document_id,
                parsed_page.page_number,
                exc,
            )
        return None
    
    def _clean_without_structured_llm(
        self,
        request_json: str,
        parsed_page: ParsedPage,
    ) -> CleanedPage | None:
        """Fallback cleaning without structured outputs."""
        prompt_text = self._prompt_template.format(request_json=request_json)
        
        try:
            response = self._llm.complete(prompt_text)
            
            # Try to extract and parse JSON manually
            if hasattr(response, "text"):
                content = response.text
            elif hasattr(response, "message") and hasattr(response.message, "content"):
                content = response.message.content
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
                
                return CleanedPage.model_validate_json(content)
        except Exception as exc:
            logger.warning(
                "Non-structured cleaning failed for doc=%s page=%s: %s",
                parsed_page.document_id,
                parsed_page.page_number,
                exc,
            )
        return None
