"""Boeing Conversational AI (BCAI) LLM adapter for LlamaIndex.

This adapter wraps the BCAI API to work with LlamaIndex's LLM interface.
BCAI is OpenAI-compatible but uses basic authentication and has some additional parameters.

Key Features:
- Text completion and chat
- Multi-modal support (vision/images)
- Structured outputs (JSON schema)
- Streaming support
- BCAI-specific parameters (conversation_mode, conversation_source, etc.)
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path
from typing import Any, Sequence

import logging
import requests

# Module-level logger for consistent logging
logger = logging.getLogger(__name__)

try:
    from llama_index.core.base.llms.base import (
        ChatMessage,
        ChatResponse,
        ChatResponseGen,
        CompletionResponse,
        CompletionResponseGen,
        ChatResponseAsyncGen,
        CompletionResponseAsyncGen,
    )
    from llama_index.core.base.llms.types import LLMMetadata, MessageRole
    from llama_index.core.llms.llm import LLM as LlamaIndexLLM
    from llama_index.core.schema import ImageDocument
except ImportError:  # pragma: no cover - optional dependency
    raise ImportError(
        "llama-index-core is required for BCAI adapter. "
        "Install with: pip install llama-index-core"
    )


class BCAILLM(LlamaIndexLLM):
    """Boeing Conversational AI (BCAI) LLM adapter.
    
    This adapter provides a LlamaIndex-compatible interface to the BCAI API,
    which is OpenAI-compatible but uses basic authentication.
    
    Args:
        api_base: Base URL for BCAI API (e.g., "https://bcai-test.web.boeing.com")
        api_key: BCAI API key (UDAL PAT)
        model: Model name (e.g., "gpt-4o-mini", "gpt-4.1-mini")
        temperature: Sampling temperature (0-2)
        max_tokens: Maximum tokens to generate
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries on failure
        conversation_mode: BCAI conversation mode (default: "non-rag")
        conversation_source: Identifier for the API caller's use case
        skip_db_save: Whether to skip saving conversation to BCAI database
    """

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        max_tokens: int = 256,
        timeout: float = 120.0,
        max_retries: int = 2,
        conversation_mode: str = "non-rag",
        conversation_source: str = "rag-pipeline-worker",
        skip_db_save: bool = True,
    ) -> None:
        super().__init__()
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._max_retries = max_retries
        self._conversation_mode = conversation_mode
        self._conversation_source = conversation_source
        self._skip_db_save = skip_db_save
        
        # Setup session with authentication
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"basic {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    @property
    def metadata(self) -> LLMMetadata:
        """Return metadata about this LLM."""
        return LLMMetadata(
            model_name=self._model,
            context_window=128000,  # Most modern models support this
            is_chat_model=True,
            is_function_calling_model=True,
        )

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        """Complete a prompt using the BCAI API.
        
        Args:
            prompt: Text prompt to complete
            formatted: Whether prompt is already formatted (unused)
            **kwargs: Additional parameters to pass to BCAI
            
        Returns:
            CompletionResponse with generated text
        """
        # Convert completion to chat format (BCAI expects chat format)
        messages = [{"role": "user", "content": prompt}]
        response_text = self._call_api(messages, **kwargs)
        return CompletionResponse(text=response_text)

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseGen:
        """Stream completion (currently returns non-streaming response).
        
        Note: Streaming is not yet implemented, returns single response.
        """
        yield self.complete(prompt, formatted, **kwargs)

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        """Chat with the model using conversation history.
        
        Args:
            messages: List of ChatMessage objects representing conversation history
            **kwargs: Additional parameters (can include structured_output_schema for JSON mode)
            
        Returns:
            ChatResponse with model's reply
        """
        # Convert LlamaIndex ChatMessage to BCAI format
        api_messages = self._convert_messages(messages)
        
        # Handle structured outputs if schema provided
        response_format = kwargs.pop("response_format", None)
        structured_schema = kwargs.pop("structured_output_schema", None)
        
        if structured_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "Response",
                    "strict": True,
                    "schema": structured_schema,
                }
            }
        
        response_text = self._call_api(
            api_messages,
            response_format=response_format,
            **kwargs
        )
        
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=response_text),
            raw={"content": response_text}
        )

    def stream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseGen:
        """Stream chat (currently returns non-streaming response).
        
        Note: Streaming is not yet implemented, returns single response.
        """
        yield self.chat(messages, **kwargs)

    async def acomplete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        """Async complete (uses sync implementation)."""
        return self.complete(prompt, formatted, **kwargs)

    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponse:
        """Async chat (uses sync implementation)."""
        return self.chat(messages, **kwargs)

    async def astream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseAsyncGen:
        """Async stream complete."""
        async def generator():
            yield self.complete(prompt, formatted, **kwargs)
        return generator()

    async def astream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseAsyncGen:
        """Async stream chat."""
        async def generator():
            yield self.chat(messages, **kwargs)
        return generator()

    def _convert_messages(self, messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
        """Convert LlamaIndex ChatMessage objects to BCAI API format.
        
        Handles both text and multi-modal (image) content.
        """
        api_messages = []
        
        logger.debug(f"Converting {len(messages)} ChatMessage(s) to BCAI format")
        
        for msg_idx, msg in enumerate(messages):
            # Handle MessageRole enum: use .value if it's an enum, otherwise convert to string
            if hasattr(msg, "role"):
                role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            else:
                role = "user"
            
            logger.debug(f"  Message {msg_idx}: role={role}, has_blocks={hasattr(msg, 'blocks') and bool(msg.blocks)}")
            
            # Handle multi-modal content (text + images)
            if hasattr(msg, "blocks") and msg.blocks:
                content = []
                logger.debug(f"    Processing {len(msg.blocks)} block(s)")
                for block_idx, block in enumerate(msg.blocks):
                    block_type = getattr(block, "block_type", "unknown")
                    logger.debug(f"    Block {block_idx}: type={block_type}, attrs={list(vars(block).keys()) if hasattr(block, '__dict__') else 'N/A'}")
                    
                    if hasattr(block, "block_type"):
                        if block.block_type == "text":
                            text_content = str(block.text) if hasattr(block, "text") else str(block)
                            content.append({
                                "type": "text",
                                "text": text_content
                            })
                            logger.debug(f"      Text block: {len(text_content)} chars")
                        elif block.block_type == "image":
                            # Handle image blocks
                            image_url = self._resolve_image_url(block)
                            if image_url:
                                content.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": image_url,
                                        "detail": "high"
                                    }
                                })
                                # Log image details
                                self._log_image_debug_info(image_url, block_idx)
                            else:
                                logger.warning(f"      Image block {block_idx}: Failed to resolve image URL")
                api_messages.append({"role": role, "content": content})
            else:
                # Simple text content
                content = str(msg.content) if hasattr(msg, "content") else str(msg)
                api_messages.append({"role": role, "content": content})
                logger.debug(f"    Simple text content: {len(content)} chars")
        
        return api_messages
    
    def _log_image_debug_info(self, image_url: str, block_idx: int) -> None:
        """Log detailed debug information about an image."""
        try:
            if image_url.startswith("data:"):
                # Parse data URL
                # Format: data:image/png;base64,<base64_data>
                header_end = image_url.find(",")
                if header_end > 0:
                    header = image_url[:header_end]
                    base64_data = image_url[header_end + 1:]
                    
                    # Extract mimetype
                    mimetype = "unknown"
                    if ":" in header and ";" in header:
                        mimetype = header.split(":")[1].split(";")[0]
                    
                    # Calculate sizes
                    base64_len = len(base64_data)
                    # Base64 encodes 3 bytes as 4 chars, so decoded size is ~75% of base64 length
                    estimated_bytes = int(base64_len * 0.75)
                    estimated_kb = estimated_bytes / 1024
                    estimated_mb = estimated_kb / 1024
                    
                    # Estimate tokens (rough: ~85 tokens per 512x512 tile for high detail)
                    # This is a very rough estimate based on OpenAI's documentation
                    estimated_tokens = max(85, int(estimated_kb / 10) * 85)
                    
                    # Check if base64 looks valid (should only contain valid base64 chars)
                    valid_base64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
                    sample = base64_data[:100]
                    invalid_chars = [c for c in sample if c not in valid_base64_chars]
                    
                    logger.debug(
                        f"      Image block {block_idx}: mimetype={mimetype}, "
                        f"base64_len={base64_len:,} chars, "
                        f"estimated_size={estimated_kb:.1f}KB ({estimated_mb:.2f}MB), "
                        f"estimated_tokens=~{estimated_tokens:,}"
                    )
                    logger.debug(f"      Image base64 prefix (first 80 chars): {base64_data[:80]}...")
                    logger.debug(f"      Image base64 suffix (last 40 chars): ...{base64_data[-40:]}")
                    
                    if invalid_chars:
                        logger.warning(f"      WARNING: Found invalid base64 chars in sample: {invalid_chars[:10]}")
                    
                    # Try to validate base64 by decoding a small sample
                    try:
                        # Just try to decode to verify it's valid base64
                        # Add padding if needed
                        padded = base64_data + "=" * (4 - len(base64_data) % 4) if len(base64_data) % 4 else base64_data
                        test_decode = base64.b64decode(padded[:100] + "==")
                        logger.debug(f"      Base64 validation: OK (sample decoded successfully)")
                    except Exception as e:
                        logger.warning(f"      Base64 validation: FAILED - {e}")
                else:
                    logger.warning(f"      Image block {block_idx}: Invalid data URL format (no comma separator)")
            else:
                logger.debug(f"      Image block {block_idx}: External URL = {image_url[:100]}...")
        except Exception as e:
            logger.warning(f"      Image debug logging failed: {e}")

    def _resolve_image_url(self, image_block: Any) -> str | None:
        """Resolve an image block to a data URL for BCAI.
        
        Supports:
        - Direct base64 data URLs
        - File paths to images
        - ImageDocument objects
        """
        logger.debug(f"      Resolving image URL from block: {type(image_block).__name__}")
        
        # Log available attributes for debugging
        if hasattr(image_block, "__dict__"):
            attrs = {k: type(v).__name__ for k, v in vars(image_block).items()}
            logger.debug(f"      Image block attributes: {attrs}")
        
        # Check if already a data URL
        if hasattr(image_block, "url") and image_block.url:
            logger.debug(f"      Found 'url' attribute, value starts with: {str(image_block.url)[:50]}...")
            if image_block.url.startswith("data:"):
                logger.debug("      Using existing data URL from 'url' attribute")
                return image_block.url
            # Try to load from file path
            logger.debug(f"      Treating 'url' as file path, encoding from: {image_block.url}")
            return self._encode_image_file(image_block.url)
        
        # Check for path attribute
        if hasattr(image_block, "path") and image_block.path:
            logger.debug(f"      Found 'path' attribute, encoding from: {image_block.path}")
            return self._encode_image_file(image_block.path)
        
        # Check for image data (raw base64 string)
        if hasattr(image_block, "image") and image_block.image:
            mimetype = getattr(image_block, "image_mimetype", "image/png")
            image_data = image_block.image
            
            # Normalize image data to clean base64 string (cross-platform fix)
            image_data = self._normalize_base64_data(image_data)
            
            logger.debug(
                f"      Found 'image' attribute with raw base64 data, "
                f"mimetype={mimetype}, data_len={len(image_data) if image_data else 0}, "
                f"data_type={type(image_block.image).__name__}"
            )
            if image_data:
                logger.debug(f"      Raw image data prefix: {image_data[:80]}...")
                logger.debug(f"      Raw image data suffix: ...{image_data[-40:]}")
            return f"data:{mimetype};base64,{image_data}"
        
        logger.warning("      Could not resolve image URL: no url, path, or image attribute found")
        return None

    def _normalize_base64_data(self, data: Any) -> str:
        """Normalize base64 data to a clean string.
        
        Handles cross-platform differences in how image data might be represented:
        - bytes vs str
        - repr() strings (e.g., "b'...'")
        - Extra whitespace or newlines
        
        Args:
            data: Raw image data (could be bytes, str, or other)
            
        Returns:
            Clean base64 string containing only valid base64 characters
        """
        if data is None:
            return ""
        
        # Log the original type for debugging
        original_type = type(data).__name__
        
        # Handle bytes
        if isinstance(data, bytes):
            logger.debug(f"      Normalizing base64: converting from bytes ({len(data)} bytes)")
            data = data.decode("utf-8", errors="replace")
        
        # Convert to string if not already
        if not isinstance(data, str):
            logger.debug(f"      Normalizing base64: converting from {original_type} to str")
            data = str(data)
        
        # Check for repr'd bytes string (e.g., "b'iVBORw0...'")
        # This can happen if someone accidentally str(bytes_object) instead of decode
        if data.startswith("b'") and data.endswith("'"):
            logger.warning(f"      Normalizing base64: detected repr'd bytes string, stripping b'...'")
            data = data[2:-1]
            # Handle escape sequences that might be in repr'd strings
            try:
                data = data.encode("utf-8").decode("unicode_escape")
            except Exception as e:
                logger.warning(f"      Failed to decode escape sequences: {e}")
        
        # Also check for b"..." format
        if data.startswith('b"') and data.endswith('"'):
            logger.warning(f"      Normalizing base64: detected repr'd bytes string (double quotes), stripping b\"...\"")
            data = data[2:-1]
            try:
                data = data.encode("utf-8").decode("unicode_escape")
            except Exception as e:
                logger.warning(f"      Failed to decode escape sequences: {e}")
        
        # Strip whitespace and newlines (sometimes added by encoders)
        data = data.strip()
        data = data.replace("\n", "").replace("\r", "").replace(" ", "")
        
        # Validate that we have valid base64 characters
        valid_base64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        invalid_chars = [c for c in data[:200] if c not in valid_base64_chars]
        
        if invalid_chars:
            logger.warning(
                f"      Normalizing base64: found {len(invalid_chars)} invalid chars in first 200: {invalid_chars[:10]}"
            )
            # Remove invalid characters
            original_len = len(data)
            data = "".join(c for c in data if c in valid_base64_chars)
            logger.warning(f"      Normalizing base64: removed invalid chars, length {original_len} -> {len(data)}")
        
        # Log final state
        if original_type != "str" or invalid_chars:
            logger.debug(f"      Normalizing base64: complete, final length={len(data)}")
        
        return data

    def _encode_image_file(self, path: str) -> str:
        """Encode an image file to a base64 data URL."""
        try:
            file_path = Path(path)
            logger.debug(f"      Encoding image file: {file_path}")
            
            if not file_path.exists():
                logger.warning(f"      Image file does not exist: {file_path}")
                return None
            
            # Determine mimetype from extension
            ext = file_path.suffix.lower()
            mimetype_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mimetype = mimetype_map.get(ext, "image/png")
            
            data = file_path.read_bytes()
            file_size_kb = len(data) / 1024
            logger.debug(f"      Read {len(data):,} bytes ({file_size_kb:.1f}KB) from file, mimetype={mimetype}")
            
            encoded = base64.b64encode(data).decode("utf-8")
            logger.debug(f"      Base64 encoded: {len(encoded):,} chars")
            logger.debug(f"      Encoded prefix: {encoded[:80]}...")
            
            return f"data:{mimetype};base64,{encoded}"
        except Exception as e:
            logger.error(f"      Failed to encode image file {path}: {e}")
            return None

    def _call_api(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        **kwargs: Any
    ) -> str:
        """Make the actual API call to BCAI.
        
        Args:
            messages: List of message dictionaries
            response_format: Optional structured output format
            **kwargs: Additional BCAI parameters
            
        Returns:
            Generated text from the model
            
        Raises:
            RuntimeError: If API call fails after retries
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "response_max_tokens": self._max_tokens,
            "conversation_mode": [self._conversation_mode],
            "conversation_source": self._conversation_source,
            "conversation_guid": str(uuid.uuid4()),  # Required by BCAI
            "skip_db_save": self._skip_db_save,
            "stream": False,  # Disable streaming for now
        }
        
        # Add response format if provided
        if response_format:
            payload["response_format"] = response_format
        
        # Merge any additional kwargs
        payload.update(kwargs)
        
        url = f"{self._api_base}/bcai-public-api/conversation"
        
        # Comprehensive debug logging for the API call
        logger.debug("=" * 60)
        logger.debug("BCAI API CALL DEBUG INFO")
        logger.debug("=" * 60)
        logger.debug(f"URL: {url}")
        logger.debug(f"Model: {payload.get('model')}")
        logger.debug(f"Temperature: {payload.get('temperature')}")
        logger.debug(f"Max tokens: {payload.get('response_max_tokens')}")
        logger.debug(f"Conversation mode: {payload.get('conversation_mode')}")
        logger.debug(f"Response format: {payload.get('response_format', {}).get('type', 'none')}")
        
        # Log message details
        msgs = payload.get("messages", [])
        logger.debug(f"Number of messages: {len(msgs)}")
        
        total_text_chars = 0
        total_images = 0
        
        for i, msg in enumerate(msgs):
            role = msg.get("role", "unknown")
            content = msg.get("content")
            
            if isinstance(content, str):
                text_len = len(content)
                total_text_chars += text_len
                logger.debug(f"  Message {i} (role={role}): text with {text_len:,} chars")
                # Show preview of text content
                preview = content[:200].replace('\n', '\\n')
                logger.debug(f"    Preview: {preview}...")
            elif isinstance(content, list):
                logger.debug(f"  Message {i} (role={role}): multimodal with {len(content)} parts")
                for j, part in enumerate(content):
                    part_type = part.get("type", "unknown")
                    if part_type == "text":
                        text_len = len(part.get("text", ""))
                        total_text_chars += text_len
                        logger.debug(f"    Part {j}: text with {text_len:,} chars")
                    elif part_type == "image_url":
                        total_images += 1
                        img_url = part.get("image_url", {}).get("url", "")
                        img_detail = part.get("image_url", {}).get("detail", "auto")
                        if img_url.startswith("data:"):
                            # Data URL
                            comma_idx = img_url.find(",")
                            if comma_idx > 0:
                                header = img_url[:comma_idx]
                                base64_data = img_url[comma_idx + 1:]
                                estimated_kb = len(base64_data) * 0.75 / 1024
                                logger.debug(
                                    f"    Part {j}: image_url (data URL), "
                                    f"header={header}, base64_len={len(base64_data):,}, "
                                    f"~{estimated_kb:.1f}KB, detail={img_detail}"
                                )
                                # Show base64 snippet
                                logger.debug(f"      Base64 start: {base64_data[:60]}...")
                                logger.debug(f"      Base64 end: ...{base64_data[-30:]}")
                        else:
                            logger.debug(f"    Part {j}: image_url (external), url={img_url[:80]}...")
        
        # Estimate total tokens (very rough)
        # ~4 chars per token for English text, ~85 tokens per image tile
        estimated_text_tokens = total_text_chars // 4
        estimated_image_tokens = total_images * 1000  # Rough estimate for high-detail images
        total_estimated_tokens = estimated_text_tokens + estimated_image_tokens
        
        logger.debug("-" * 40)
        logger.debug(f"TOTALS: {total_text_chars:,} text chars, {total_images} images")
        logger.debug(f"ESTIMATED TOKENS: ~{estimated_text_tokens:,} (text) + ~{estimated_image_tokens:,} (images) = ~{total_estimated_tokens:,} total")
        logger.debug("=" * 60)
        
        # Retry logic
        last_exception = None
        last_response_body = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.post(
                    url,
                    json=payload,
                    timeout=self._timeout,
                )
                
                # For debugging, capture response body before raising
                if hasattr(response, 'status_code') and response.status_code >= 400:
                    try:
                        last_response_body = response.text
                    except Exception:
                        last_response_body = None
                
                response.raise_for_status()
                
                data = response.json()
                return self._extract_text_from_response(data)
                
            except requests.exceptions.RequestException as exc:
                last_exception = exc
                if attempt == self._max_retries:
                    break
                # Don't retry on 4xx errors (client errors) - only 5xx and network issues
                if hasattr(exc, 'response') and exc.response is not None:
                    if 400 <= exc.response.status_code < 500:
                        break  # Don't retry client errors
                # Wait a bit before retrying (exponential backoff)
                import time
                time.sleep(2 ** attempt)
        
        # Include response body in error message if available
        error_msg = f"BCAI API error after {self._max_retries + 1} attempts: {last_exception}"
        if last_response_body:
            error_msg += f"\nResponse body: {last_response_body[:500]}"
        
        raise RuntimeError(error_msg) from last_exception

    def _extract_text_from_response(self, data: dict[str, Any]) -> str:
        """Extract generated text from BCAI response.
        
        BCAI response format:
        {
            "choices": [
                {
                    "messages": [{"role": "assistant", "content": "text"}]
                }
            ]
        }
        """
        try:
            choices = data.get("choices", [])
            if not choices:
                return str(data)
            
            # BCAI uses 'messages' array in choices
            messages = choices[0].get("messages", [])
            if messages:
                return messages[0].get("content", "")
            
            # Fallback to standard OpenAI format
            message = choices[0].get("message", {})
            return message.get("content", str(data))
        except (KeyError, IndexError, AttributeError):
            # Fallback to returning raw data as string
            return str(data)

