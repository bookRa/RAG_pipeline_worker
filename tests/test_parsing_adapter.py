from __future__ import annotations

from pathlib import Path

from src.app.adapters.llama_index.parsing_adapter import ImageAwareParsingAdapter
from src.app.config import PromptSettings
from src.app.parsing.schemas import ParsedPage


class StubStructuredResponse:
    """Mock response from structured LLM with .raw and .text attributes."""
    
    def __init__(self, parsed_page: ParsedPage) -> None:
        self.raw = parsed_page
        self.text = parsed_page.model_dump_json()


class StubStructuredLLM:
    """Mock structured LLM returned by as_structured_llm()."""
    
    def __init__(self, parsed_page: ParsedPage) -> None:
        self._parsed_page = parsed_page
        self.complete_calls: list[tuple] = []
        self.chat_calls: list[tuple] = []
    
    def complete(self, prompt: str, **kwargs) -> StubStructuredResponse:
        self.complete_calls.append((prompt, kwargs))
        return StubStructuredResponse(self._parsed_page)
    
    def chat(self, messages: list, **kwargs) -> StubStructuredResponse:
        self.chat_calls.append((messages, kwargs))
        return StubStructuredResponse(self._parsed_page)


class StubLLM:
    """Mock LLM that supports as_structured_llm() and structured_predict()."""
    
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.complete_calls: list[tuple] = []
        self._parsed_page = ParsedPage(
            document_id="doc",
            page_number=1,
            raw_text="hello",
            paragraphs=[],
        )
        # Cache structured LLM instances so we can track calls
        self._structured_llms: dict[type, StubStructuredLLM] = {}
        # Track which Pydantic classes were wrapped with as_structured_llm()
        self.structured_llm_calls: list[type] = []
    
    def as_structured_llm(self, pydantic_class: type) -> StubStructuredLLM:
        """Return a mock structured LLM, caching instances by Pydantic class."""
        # Track that this class was used for structured output
        self.structured_llm_calls.append(pydantic_class)
        
        if pydantic_class not in self._structured_llms:
            self._structured_llms[pydantic_class] = StubStructuredLLM(self._parsed_page)
        return self._structured_llms[pydantic_class]
    
    def structured_predict(self, pydantic_class: type, prompt_template, **kwargs):
        """Mock structured_predict method."""
        # Track the call
        self.complete_calls.append(("structured_predict", kwargs))
        return self._parsed_page
    
    def complete(self, prompt: str, **kwargs):
        """Complete method that tracks calls."""
        self.complete_calls.append((prompt, kwargs))
        return StubStructuredResponse(self._parsed_page)
    
    def chat(self, messages: list, **kwargs):
        """Fallback for non-structured chat calls."""
        self.calls.append({"messages": messages, **kwargs})
        return StubStructuredResponse(self._parsed_page)
    
    def stream_chat(self, messages: list, **kwargs):
        """Fallback for streaming chat calls."""
        self.calls.append({"messages": messages, "streaming": True, **kwargs})
        # Return an iterator that yields chunks with JSON content
        class MockChunk:
            def __init__(self, text):
                self.delta = text
        # Return the full parsed page as JSON in one chunk
        json_content = self._parsed_page.model_dump_json()
        return iter([MockChunk(json_content)])


def _write_png(path: Path) -> None:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - test guard
        raise RuntimeError("Pillow is required for parsing adapter tests.") from exc

    img = Image.new("RGB", (2, 2), color="white")
    img.save(path)


def test_image_adapter_uses_multimodal_when_pixmap(tmp_path):
    pixmap_path = tmp_path / "page.png"
    _write_png(pixmap_path)

    text_llm = StubLLM()
    vision_llm = StubLLM()
    adapter = ImageAwareParsingAdapter(
        llm=text_llm,
        vision_llm=vision_llm,
        prompt_settings=PromptSettings(),
    )

    result = adapter.parse_page(document_id="doc", page_number=1, raw_text="text", pixmap_path=str(pixmap_path))

    # Verify text LLM was used for vision (same LLM handles both)
    # Check that chat() was called directly on the base LLM with image content
    assert len(text_llm.calls) > 0, "Text LLM should have been called with chat() for vision"
    
    # Verify the chat call contains messages with image content
    chat_call = text_llm.calls[0]
    if "messages" in chat_call:
        messages = chat_call["messages"]
        if messages and len(messages) > 0:
            message = messages[0]
            # Check if message content is a list with ImageBlock
            if isinstance(message.content, list):
                from llama_index.core.base.llms.types import ImageBlock
                has_image = any(
                    isinstance(item, ImageBlock) or (hasattr(item, 'block_type') and getattr(item, 'block_type', None) == 'image')
                    for item in message.content
                )
                assert has_image, "Chat message should contain ImageBlock in content list"
    
    # Verify vision_llm was not used (we use same LLM now)
    assert len(vision_llm.complete_calls) == 0, "Separate vision_llm should not be used (same LLM handles vision)"
    
    # Verify result is a ParsedPage
    assert isinstance(result, ParsedPage)
    assert result.document_id == "doc"
    assert result.page_number == 1


def test_parsing_adapter_uses_structured_api_when_not_streaming(tmp_path):
    """Verify parsing adapter uses as_structured_llm() API when streaming is disabled."""
    pixmap_path = tmp_path / "page.png"
    _write_png(pixmap_path)
    
    llm = StubLLM()
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
        use_streaming=False,  # KEY: Disable streaming to use structured API
    )
    
    result = adapter.parse_page(
        document_id="doc",
        page_number=1,
        raw_text="text",
        pixmap_path=str(pixmap_path)
    )
    
    # Verify as_structured_llm() was called with ParsedPage
    assert ParsedPage in llm.structured_llm_calls, \
        "Should call as_structured_llm(ParsedPage)"
    
    # Verify the structured LLM wrapper's chat() was called
    assert ParsedPage in llm._structured_llms, "Should create structured LLM wrapper"
    structured_llm = llm._structured_llms[ParsedPage]
    assert len(structured_llm.chat_calls) > 0, \
        "Should call chat() on structured LLM wrapper"
    
    # Verify chat was called with messages containing image
    messages, kwargs = structured_llm.chat_calls[0]
    assert len(messages) >= 2, "Should have system + user messages"
    
    # Check user message contains ImageBlock
    user_message = messages[1]
    from llama_index.core.base.llms.types import ImageBlock
    # ChatMessage stores ImageBlock in either .content (list) or .blocks
    if hasattr(user_message, 'blocks') and user_message.blocks:
        has_image = any(isinstance(item, ImageBlock) for item in user_message.blocks)
        assert has_image, "User message should contain ImageBlock in blocks"
    elif isinstance(user_message.content, list):
        has_image = any(isinstance(item, ImageBlock) for item in user_message.content)
        assert has_image, "User message should contain ImageBlock in content list"
    else:
        raise AssertionError(f"Expected ImageBlock in message, got content={user_message.content}, blocks={getattr(user_message, 'blocks', None)}")
    
    # Verify result is valid ParsedPage
    assert isinstance(result, ParsedPage)
    assert result.document_id == "doc"
    assert result.page_number == 1
    assert result.parsing_status == "success"


def test_parsing_adapter_uses_streaming_when_enabled(tmp_path):
    """Verify parsing adapter uses streaming (manual schema) when streaming is enabled."""
    pixmap_path = tmp_path / "page.png"
    _write_png(pixmap_path)
    
    llm = StubLLM()
    # Add stream_chat support
    llm.stream_chat_calls = []
    def mock_stream_chat(messages):
        llm.stream_chat_calls.append(messages)
        # Return an iterator that yields chunks
        class MockChunk:
            def __init__(self, text):
                self.delta = text
        return iter([MockChunk('{"document_id": "doc", "page_number": 1, "raw_text": "test", "components": [], "parsing_status": "success"}')])
    llm.stream_chat = mock_stream_chat
    
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
        use_streaming=True,  # KEY: Enable streaming
    )
    
    result = adapter.parse_page(
        document_id="doc",
        page_number=1,
        raw_text="text",
        pixmap_path=str(pixmap_path)
    )
    
    # Verify as_structured_llm() was NOT called (streaming takes precedence)
    assert ParsedPage not in llm.structured_llm_calls, \
        "Should NOT call as_structured_llm() when streaming is enabled"
    
    # Verify stream_chat was called instead
    assert len(llm.stream_chat_calls) > 0, \
        "Should call stream_chat() when streaming is enabled"
    
    # Verify result is still valid
    assert isinstance(result, ParsedPage)
    assert result.document_id == "doc"
    assert result.page_number == 1


def test_parsing_adapter_falls_back_if_structured_api_fails(tmp_path):
    """Verify parsing adapter falls back to manual schema if structured API fails."""
    pixmap_path = tmp_path / "page.png"
    _write_png(pixmap_path)
    
    llm = StubLLM()
    # Make structured API fail
    original_as_structured = llm.as_structured_llm
    def failing_as_structured(pydantic_class):
        llm.structured_llm_calls.append(pydantic_class)  # Track the call
        structured = original_as_structured(pydantic_class)
        # Make chat() raise exception
        def failing_chat(messages, **kwargs):
            raise RuntimeError("Structured API failed")
        structured.chat = failing_chat
        return structured
    llm.as_structured_llm = failing_as_structured
    
    # Add working chat method for fallback (non-structured chat with manual schema)
    # The fallback uses _parse_with_vision_structured which calls chat() not stream_chat() when streaming=False
    llm.chat_calls_count = 0
    original_chat = llm.chat
    def working_chat(messages, **kwargs):
        llm.chat_calls_count += 1
        return original_chat(messages, **kwargs)
    llm.chat = working_chat
    
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
        use_streaming=False,  # Structured API should be tried first, then fallback to manual schema (non-streaming)
    )
    
    result = adapter.parse_page(
        document_id="doc",
        page_number=1,
        raw_text="text",
        pixmap_path=str(pixmap_path)
    )
    
    # Verify structured API was attempted
    assert ParsedPage in llm.structured_llm_calls, \
        "Should attempt as_structured_llm() first"
    
    # Verify fallback to manual schema (non-streaming chat) happened
    # The base StubLLM.chat() is called by _parse_with_vision_structured as fallback
    assert llm.chat_calls_count > 0, \
        "Should fall back to manual schema (chat) when structured API fails"
    
    # Verify result is valid (from fallback)
    assert isinstance(result, ParsedPage)
    assert result.document_id == "doc"
    assert result.page_number == 1
