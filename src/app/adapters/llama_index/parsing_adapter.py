from __future__ import annotations

import json
import logging
import time
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
        use_streaming: bool = True,
        streaming_max_chars: int = 50000,
        streaming_repetition_window: int = 200,
        streaming_repetition_threshold: float = 0.8,
        streaming_max_consecutive_newlines: int = 100,
    ) -> None:
        self._llm = llm
        self._vision_llm = vision_llm
        self._use_structured_outputs = use_structured_outputs
        self._use_streaming = use_streaming
        
        # Streaming guardrail settings
        self._streaming_max_chars = streaming_max_chars
        self._streaming_repetition_window = streaming_repetition_window
        self._streaming_repetition_threshold = streaming_repetition_threshold
        self._streaming_max_consecutive_newlines = streaming_max_consecutive_newlines
        
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
                "❌ No pixmap provided for doc=%s page=%s, marking as failed",
                document_id,
                page_number,
            )
            return ParsedPage(
                document_id=document_id,
                page_number=page_number,
                raw_text="",
                components=[],
                parsing_status="failed",
                error_type="missing_pixmap",
                error_details="No pixmap image provided for vision-based parsing",
            )
        
        try:
            # Priority 1: Use structured API (non-streaming) for maximum reliability
            # This leverages native JSON mode (OpenAI response_format) when available
            if self._use_structured_outputs and not self._use_streaming:
                parsed_page = self._parse_with_structured_api(document_id, page_number, pixmap_path)
                if parsed_page:
                    self._log_trace(document_id, page_number, pixmap_path, parsed_page)
                    return parsed_page
                # If structured API fails, log and fall through to streaming method
                logger.warning(
                    "Structured API failed for doc=%s page=%s, trying streaming method as fallback",
                    document_id,
                    page_number,
                )
            
            # Priority 2: Use manual schema injection with streaming (for progress logs)
            # This is used when streaming is enabled or when structured API failed
            if self._use_structured_outputs:
                parsed_page = self._parse_with_vision_structured(document_id, page_number, pixmap_path)
                if parsed_page:
                    self._log_trace(document_id, page_number, pixmap_path, parsed_page)
                    return parsed_page
            else:
                # Priority 3: Fallback to non-structured parsing if disabled
                parsed_page = self._parse_without_structured_llm(document_id, page_number, pixmap_path)
                if parsed_page:
                    self._log_trace(document_id, page_number, pixmap_path, parsed_page)
                    return parsed_page
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.error(
                "❌ Parsing failed for doc=%s page=%s pixmap=%s: %s",
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
                parsing_status="failed",
                error_type="exception",
                error_details=f"{type(exc).__name__}: {str(exc)}",
            )
        
        # If we reach here, both parsing attempts returned None
        logger.error(
            "❌ All parsing methods returned None for doc=%s page=%s",
            document_id,
            page_number,
        )
        return ParsedPage(
            document_id=document_id,
            page_number=page_number,
            raw_text="",
            components=[],
            parsing_status="failed",
            error_type="parsing_returned_none",
            error_details="All parsing methods failed to return a valid page",
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
            
            # Call chat with streaming if enabled
            stream_error_type: str | None = None
            stream_error_details: str | None = None
            
            if self._use_streaming:
                content, stream_error_type, stream_error_details = self._stream_chat_response(messages, document_id, page_number)
            else:
                response = self._llm.chat(messages)
                content = self._extract_content_from_response(response)
            
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
                
                # If streaming hit a guardrail, mark as failed or partial
                if stream_error_type:
                    # If we got some content but hit a guardrail, mark as partial
                    status = "partial" if len(parsed_page.components) > 0 else "failed"
                    parsed_page = parsed_page.model_copy(
                        update={
                            "parsing_status": status,
                            "error_type": stream_error_type,
                            "error_details": stream_error_details,
                        }
                    )
                    logger.warning(
                        "⚠️ Parsing marked as %s due to %s for doc=%s page=%s",
                        status,
                        stream_error_type,
                        document_id,
                        page_number,
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
    
    def _parse_with_structured_api(
        self,
        document_id: str,
        page_number: int,
        pixmap_path: str,
    ) -> ParsedPage | None:
        """Parse using LlamaIndex as_structured_llm() API with vision.
        
        This method leverages native structured output support (e.g., OpenAI JSON mode)
        instead of manually injecting schema into prompts. This provides more reliable
        JSON parsing and automatic validation.
        
        Args:
            document_id: Document identifier
            page_number: Page number to parse
            pixmap_path: Path to page image (PNG)
        
        Returns:
            ParsedPage if successful, None if parsing fails
        
        Note:
            This method does NOT support streaming. For streaming with progress logs,
            use _parse_with_vision_structured() instead.
        """
        path_obj = Path(pixmap_path) if pixmap_path else None
        logger.info(
            "parsing_page_structured_api llm=%s document_id=%s page=%s exists=%s size=%s bytes",
            self._llm.__class__.__name__,
            document_id,
            page_number,
            path_obj.exists() if path_obj else False,
            path_obj.stat().st_size if path_obj and path_obj.exists() else None,
        )
        
        try:
            # Create structured LLM wrapper for ParsedPage schema
            # This automatically enables native JSON mode (e.g., OpenAI response_format)
            structured_llm = self._llm.as_structured_llm(ParsedPage)
            
            # Build system prompt with context (no need to inject schema manually!)
            system_prompt_with_context = (
                f"{self._system_prompt}\n\n"
                f"Document ID: {document_id}\n"
                f"Page Number: {page_number}"
            )
            
            # Encode image as base64
            image_data = encode_image(pixmap_path)
            
            # Create messages: system prompt + user message with image
            messages = [
                ChatMessage(role="system", content=system_prompt_with_context),
                ChatMessage(
                    role="user",
                    content=[
                        ImageBlock(image=image_data, image_mimetype="image/png"),
                    ],
                ),
            ]
            
            # Call chat() on structured LLM wrapper
            # This should automatically use native structured output support
            response = structured_llm.chat(messages)
            
            # Extract Pydantic object from response.raw
            if hasattr(response, "raw") and isinstance(response.raw, ParsedPage):
                parsed_page = response.raw
                # Ensure document_id and page_number are correct (LLM might get them wrong)
                parsed_page = parsed_page.model_copy(
                    update={
                        "document_id": document_id,
                        "page_number": page_number,
                    }
                )
                logger.info(
                    "✅ Structured API parsing succeeded for doc=%s page=%s (components: %d)",
                    document_id,
                    page_number,
                    len(parsed_page.components),
                )
                return parsed_page
            elif hasattr(response, "text"):
                # Fallback: try to parse from text (shouldn't happen with structured API)
                logger.warning(
                    "Structured API response missing .raw, attempting fallback parse for doc=%s page=%s",
                    document_id,
                    page_number,
                )
                parsed_page = ParsedPage.model_validate_json(response.text)
                parsed_page = parsed_page.model_copy(
                    update={
                        "document_id": document_id,
                        "page_number": page_number,
                    }
                )
                return parsed_page
            else:
                logger.warning(
                    "Structured API response has unexpected format for doc=%s page=%s: %s",
                    document_id,
                    page_number,
                    type(response),
                )
        except Exception as exc:
            logger.warning(
                "Structured API parsing failed for doc=%s page=%s: %s",
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

    def _stream_chat_response(
        self,
        messages: list[ChatMessage],
        document_id: str,
        page_number: int,
    ) -> tuple[str, str | None, str | None]:
        """Stream chat response and log progress in real-time with repetition detection.
        
        Returns:
            tuple[str, str | None, str | None]: (content, error_type, error_details)
        """
        logger.info(
            "🔄 Starting streaming response for doc=%s page=%s...",
            document_id,
            page_number,
        )
        
        start_time = time.time()
        first_token_time = None
        accumulated_content = ""
        chunk_count = 0
        
        # Track guardrail failures
        error_type: str | None = None
        error_details: str | None = None
        
        # Time-based logging configuration
        log_interval_seconds = 5.0  # Log every 5 seconds
        last_log_time = start_time
        content_since_last_log = ""
        
        # Repetition detection configuration (from settings)
        max_response_length = self._streaming_max_chars
        repetition_window = self._streaming_repetition_window
        repetition_threshold = self._streaming_repetition_threshold
        consecutive_newlines_limit = self._streaming_max_consecutive_newlines
        
        # Log guardrail configuration for debugging
        logger.info(
            "🛡️ Guardrails active: max_chars=%d, rep_window=%d, rep_threshold=%.2f, max_consec_newlines=%d",
            max_response_length,
            repetition_window,
            repetition_threshold,
            consecutive_newlines_limit,
        )
        
        try:
            # Call stream_chat to get streaming response
            stream_response = self._llm.stream_chat(messages)
            
            for chunk in stream_response:
                chunk_count += 1
                current_time = time.time()
                
                # Record time to first token
                if first_token_time is None:
                    first_token_time = current_time
                    elapsed = first_token_time - start_time
                    logger.info(
                        "✓ First token received for doc=%s page=%s (%.1fs)",
                        document_id,
                        page_number,
                        elapsed,
                    )
                
                # Extract delta content from chunk
                delta = ""
                if hasattr(chunk, "delta") and chunk.delta:
                    delta = str(chunk.delta)
                elif hasattr(chunk, "message") and hasattr(chunk.message, "content"):
                    # Some implementations return full message
                    new_content = str(chunk.message.content)
                    if new_content.startswith(accumulated_content):
                        delta = new_content[len(accumulated_content):]
                    else:
                        delta = new_content
                
                accumulated_content += delta
                content_since_last_log += delta
                
                # Guardrail 1: Check for excessive response length
                if len(accumulated_content) > max_response_length:
                    error_type = "max_length_exceeded"
                    error_details = f"Streaming stopped: response exceeded maximum length ({max_response_length} chars, got {len(accumulated_content)})"
                    logger.warning(
                        "⚠️ Stopping stream for doc=%s page=%s: exceeded max length (%d chars)",
                        document_id,
                        page_number,
                        max_response_length,
                    )
                    break
                
                # Guardrail 2: Check for repetitive patterns (e.g., infinite \n\n\n)
                if len(accumulated_content) >= repetition_window:
                    recent_content = accumulated_content[-repetition_window:]
                    
                    # Check if content is mostly the same character
                    most_common_char = max(set(recent_content), key=recent_content.count)
                    char_ratio = recent_content.count(most_common_char) / len(recent_content)
                    
                    # Debug: log every 50 chunks when checking repetition
                    if chunk_count % 50 == 0:
                        # Show a sample of the recent content to diagnose issues
                        sample = recent_content[-50:] if len(recent_content) > 50 else recent_content
                        logger.debug(
                            "🔍 Repetition check [chunk %d]: %.1f%% of last %d chars are %s | sample: %s",
                            chunk_count,
                            char_ratio * 100,
                            repetition_window,
                            repr(most_common_char),
                            repr(sample),
                        )
                    
                    if char_ratio > repetition_threshold:
                        error_type = "repetition_loop"
                        error_details = f"Streaming stopped: detected repetition loop ({char_ratio*100:.1f}% of last {repetition_window} chars are {repr(most_common_char)})"
                        logger.warning(
                            "⚠️ Stopping stream for doc=%s page=%s: detected repetition loop "
                            "(%.1f%% of last %d chars are '%s')",
                            document_id,
                            page_number,
                            char_ratio * 100,
                            repetition_window,
                            repr(most_common_char),
                        )
                        break
                
                # Guardrail 3: Check for excessive consecutive newlines (both actual \n and escaped \\n)
                # Only check the last portion of content for efficiency (last 500 chars)
                check_window = min(500, len(accumulated_content))
                tail_content = accumulated_content[-check_window:]
                
                # Count max consecutive ACTUAL newlines in the tail
                max_consecutive_newlines = 0
                current_consecutive = 0
                for char in tail_content:
                    if char == '\n':
                        current_consecutive += 1
                        max_consecutive_newlines = max(max_consecutive_newlines, current_consecutive)
                    else:
                        current_consecutive = 0
                
                # Also check for the string "\\n" repeated (escaped newlines in JSON)
                escaped_newline_count = tail_content.count('\\n')
                escaped_newline_ratio = escaped_newline_count * 2 / len(tail_content) if tail_content else 0  # *2 because \\n is 2 chars
                
                if chunk_count % 50 == 0:
                    logger.debug(
                        "🔍 Newline check [chunk %d]: max consec newlines = %d, escaped \\\\n ratio = %.1f%%",
                        chunk_count,
                        max_consecutive_newlines,
                        escaped_newline_ratio * 100,
                    )
                
                # Trigger if we have excessive actual newlines OR excessive escaped newlines
                if max_consecutive_newlines >= consecutive_newlines_limit:
                    error_type = "excessive_newlines"
                    error_details = f"Streaming stopped: detected {max_consecutive_newlines} consecutive newlines (limit: {consecutive_newlines_limit})"
                    logger.warning(
                        "⚠️ Stopping stream for doc=%s page=%s: detected %d consecutive newlines (limit: %d)",
                        document_id,
                        page_number,
                        max_consecutive_newlines,
                        consecutive_newlines_limit,
                    )
                    break
                
                # Also stop if >50% of recent content is escaped newlines (likely a runaway response)
                if escaped_newline_ratio > 0.5:
                    error_type = "excessive_escaped_newlines"
                    error_details = f"Streaming stopped: detected excessive escaped newlines ({escaped_newline_ratio*100:.1f}% of recent content)"
                    logger.warning(
                        "⚠️ Stopping stream for doc=%s page=%s: detected excessive escaped newlines (%.1f%% of tail)",
                        document_id,
                        page_number,
                        escaped_newline_ratio * 100,
                    )
                    break
                
                # Log accumulated content every N seconds
                if current_time - last_log_time >= log_interval_seconds:
                    if content_since_last_log:
                        # Log the chunk in a readable format (full content, no truncation)
                        logger.info(
                            "📝 [doc=%s pg=%s | %.1fs]\n%s",
                            document_id,
                            page_number,
                            current_time - start_time,
                            content_since_last_log,
                        )
                        logger.info(
                            "📊 Progress: %d chunks, %d chars total",
                            chunk_count,
                            len(accumulated_content),
                        )
                    content_since_last_log = ""
                    last_log_time = current_time
            
            # Log any remaining content
            if content_since_last_log:
                logger.info(
                    "📝 [doc=%s pg=%s | final]\n%s",
                    document_id,
                    page_number,
                    content_since_last_log,
                )
            
            # Final summary
            total_time = time.time() - start_time
            if error_type:
                logger.warning(
                    "⚠️ Streaming stopped with guardrail for doc=%s page=%s: %s - %d chunks, %d chars in %.1fs",
                    document_id,
                    page_number,
                    error_type,
                    chunk_count,
                    len(accumulated_content),
                    total_time,
                )
            else:
                logger.info(
                    "✅ Streaming complete for doc=%s page=%s: %d chunks, %d chars in %.1fs (TTFT: %.1fs)",
                    document_id,
                    page_number,
                    chunk_count,
                    len(accumulated_content),
                    total_time,
                    (first_token_time - start_time) if first_token_time else 0,
                )
            
            return accumulated_content, error_type, error_details
            
        except Exception as exc:
            logger.error(
                "❌ Streaming failed for doc=%s page=%s after %d chunks: %s",
                document_id,
                page_number,
                chunk_count,
                exc,
            )
            return accumulated_content, "streaming_exception", f"{type(exc).__name__}: {str(exc)}"

    def _extract_content_from_response(self, response: Any) -> str:
        """Extract text content from a non-streaming response."""
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
                return "".join(text_parts)
            elif not isinstance(content, str):
                return str(content)
            return content
        elif hasattr(response, "text"):
            return response.text
        else:
            return str(response)

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
        logger.info("🔍 PARSING TRACE - Document: %s, Page: %s", document_id, page_number)
        logger.info("=" * 80)
        logger.info("Pixmap Path: %s", pixmap_path)
        logger.info("Parsing Status: %s", parsed_page.parsing_status)
        
        # NEW: Log error details if parsing failed/partial
        if parsed_page.parsing_status != "success":
            logger.warning("-" * 80)
            logger.warning("❌ PARSING %s", parsed_page.parsing_status.upper())
            logger.warning("-" * 80)
            logger.warning("Error Type: %s", parsed_page.error_type)
            logger.warning("Error Details: %s", parsed_page.error_details)
        
        # NEW: Log page summary if present
        if parsed_page.page_summary:
            logger.info("-" * 80)
            logger.info("📄 PAGE SUMMARY:")
            logger.info("-" * 80)
            logger.info("%s", parsed_page.page_summary)
        
        logger.info("-" * 80)
        logger.info("RAW TEXT (Markdown):")
        logger.info("-" * 80)
        logger.info("%s", parsed_page.raw_text)
        logger.info("-" * 80)
        logger.info("COMPONENTS: %d (ordered by layout)", len(parsed_page.components))
        
        # Show all components (no truncation)
        for i, component in enumerate(parsed_page.components, 1):
            if isinstance(component, ParsedTextComponent):
                text_type_str = f" ({component.text_type})" if component.text_type else ""
                logger.info("  [%d] TEXT%s - order=%d:\n%s", 
                          i, text_type_str, component.order,
                          component.text)
            elif isinstance(component, ParsedImageComponent):
                logger.info("  [%d] IMAGE - order=%d", i, component.order)
                logger.info("      description: %s", component.description)
                if component.recognized_text:
                    logger.info("      recognized_text: %s", component.recognized_text)
            elif isinstance(component, ParsedTableComponent):
                caption_str = f" - {component.caption}" if component.caption else ""
                logger.info("  [%d] TABLE - order=%d%s: %d rows", 
                          i, component.order, caption_str, len(component.rows))
                # NEW: Log table summary if present
                if component.table_summary:
                    logger.info("      📊 summary: %s", component.table_summary)
                if component.rows:
                    # Show all column names
                    first_row = component.rows[0]
                    cols = ", ".join(list(first_row.keys()))
                    logger.info("      columns: %s", cols)
        
        # Summary by type
        text_count = len([c for c in parsed_page.components if isinstance(c, ParsedTextComponent)])
        image_count = len([c for c in parsed_page.components if isinstance(c, ParsedImageComponent)])
        table_count = len([c for c in parsed_page.components if isinstance(c, ParsedTableComponent)])
        logger.info("-" * 80)
        logger.info("SUMMARY: %d text, %d images, %d tables", text_count, image_count, table_count)
        logger.info("=" * 80)
