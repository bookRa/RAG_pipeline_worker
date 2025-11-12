from __future__ import annotations

from pathlib import Path

from src.app.adapters.llama_index.parsing_adapter import ImageAwareParsingAdapter
from src.app.config import PromptSettings


class StubResponse:
    def __init__(self, payload: str) -> None:
        self.text = payload


class StubLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete(self, prompt: str, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        return StubResponse(
            '{"document_id": "doc", "page_number": 1, "raw_text": "hello", "paragraphs": []}'
        )


def test_image_adapter_uses_multimodal_when_pixmap(tmp_path):
    pixmap_path = tmp_path / "page.png"
    pixmap_path.write_bytes(b"fakepng")

    text_llm = StubLLM()
    vision_llm = StubLLM()
    adapter = ImageAwareParsingAdapter(
        llm=text_llm,
        vision_llm=vision_llm,
        prompt_settings=PromptSettings(),
    )

    adapter.parse_page(document_id="doc", page_number=1, raw_text="text", pixmap_path=str(pixmap_path))

    assert not text_llm.calls  # Vision path should have handled the request
    assert vision_llm.calls
    call = vision_llm.calls[0]
    assert "image_documents" in call
    assert call["image_documents"][0].image_path == str(pixmap_path)
