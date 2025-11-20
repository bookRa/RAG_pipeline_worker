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
from pathlib import Path
from typing import Any, Sequence

import requests

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
        
        for msg in messages:
            role = str(msg.role) if hasattr(msg, "role") else "user"
            
            # Handle multi-modal content (text + images)
            if hasattr(msg, "blocks") and msg.blocks:
                content = []
                for block in msg.blocks:
                    if hasattr(block, "block_type"):
                        if block.block_type == "text":
                            content.append({
                                "type": "text",
                                "text": str(block.text) if hasattr(block, "text") else str(block)
                            })
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
                api_messages.append({"role": role, "content": content})
            else:
                # Simple text content
                content = str(msg.content) if hasattr(msg, "content") else str(msg)
                api_messages.append({"role": role, "content": content})
        
        return api_messages

    def _resolve_image_url(self, image_block: Any) -> str | None:
        """Resolve an image block to a data URL for BCAI.
        
        Supports:
        - Direct base64 data URLs
        - File paths to images
        - ImageDocument objects
        """
        # Check if already a data URL
        if hasattr(image_block, "url") and image_block.url:
            if image_block.url.startswith("data:"):
                return image_block.url
            # Try to load from file path
            return self._encode_image_file(image_block.url)
        
        # Check for path attribute
        if hasattr(image_block, "path") and image_block.path:
            return self._encode_image_file(image_block.path)
        
        # Check for image data
        if hasattr(image_block, "image") and image_block.image:
            mimetype = getattr(image_block, "image_mimetype", "image/png")
            return f"data:{mimetype};base64,{image_block.image}"
        
        return None

    def _encode_image_file(self, path: str) -> str:
        """Encode an image file to a base64 data URL."""
        try:
            file_path = Path(path)
            if not file_path.exists():
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
            encoded = base64.b64encode(data).decode("utf-8")
            return f"data:{mimetype};base64,{encoded}"
        except Exception:
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
            "skip_db_save": self._skip_db_save,
            "stream": False,  # Disable streaming for now
        }
        
        # Add response format if provided
        if response_format:
            payload["response_format"] = response_format
        
        # Merge any additional kwargs
        payload.update(kwargs)
        
        url = f"{self._api_base}/bcai-public-api/conversation"
        
        # Retry logic
        last_exception = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.post(
                    url,
                    json=payload,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                
                data = response.json()
                return self._extract_text_from_response(data)
                
            except requests.exceptions.RequestException as exc:
                last_exception = exc
                if attempt == self._max_retries:
                    break
                # Wait a bit before retrying (exponential backoff)
                import time
                time.sleep(2 ** attempt)
        
        raise RuntimeError(
            f"BCAI API error after {self._max_retries + 1} attempts: {last_exception}"
        ) from last_exception

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

