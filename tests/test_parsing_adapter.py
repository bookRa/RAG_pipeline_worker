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
    
    def as_structured_llm(self, pydantic_class: type) -> StubStructuredLLM:
        """Return a mock structured LLM, caching instances by Pydantic class."""
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
    assert len(vision_llm.complete_calls) == 0, "Vision LLM should not be used (same LLM handles vision)"
    
    # Verify result is a ParsedPage
    assert isinstance(result, ParsedPage)
    assert result.document_id == "doc"
    assert result.page_number == 1
