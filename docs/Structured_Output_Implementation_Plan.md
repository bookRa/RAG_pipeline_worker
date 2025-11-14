# Structured Output Implementation Plan

**Date:** November 14, 2025  
**Related Document:** [Structured_Output_Analysis.md](./Structured_Output_Analysis.md)  
**Status:** Ready for Implementation

---

## Overview

This document provides a detailed, step-by-step implementation plan for migrating the parsing adapter to use LlamaIndex's `as_structured_llm()` API instead of manual JSON schema injection.

**Goal:** Improve reliability and maintainability of structured output parsing while maintaining backward compatibility and streaming support.

---

## Prerequisites

### 1. Verify Vision + Structured Output Compatibility

**Action:** Create proof-of-concept test to verify that `as_structured_llm().chat()` works with `ImageBlock` content.

**Test Script:** (to be run manually before implementation)

```python
# tests/poc_structured_vision.py
"""Proof of concept: Test if as_structured_llm() works with vision."""
from pathlib import Path
from pydantic import BaseModel, Field
from llama_index.llms.openai import OpenAI
from llama_index.core.llms import ChatMessage
from llama_index.core.base.llms.types import ImageBlock
from llama_index.core.multi_modal_llms.generic_utils import encode_image


class SimplePageStructure(BaseModel):
    """Simple test schema."""
    description: str = Field(description="Describe what you see in the image")
    has_text: bool = Field(description="Does the image contain text?")
    element_count: int = Field(description="Approximate number of distinct elements")


def test_structured_llm_with_vision():
    """Test if structured LLM works with vision input."""
    # Create a simple test image
    from PIL import Image
    test_img_path = Path("/tmp/test_vision.png")
    img = Image.new("RGB", (200, 100), color="white")
    img.save(test_img_path)
    
    # Create LLM and structured wrapper
    llm = OpenAI(model="gpt-4o-mini")
    structured_llm = llm.as_structured_llm(SimplePageStructure)
    
    # Encode image
    image_data = encode_image(str(test_img_path))
    
    # Create messages with image
    messages = [
        ChatMessage(
            role="system",
            content="Analyze the image and respond with structured data."
        ),
        ChatMessage(
            role="user",
            content=[
                ImageBlock(image=image_data, image_mimetype="image/png"),
            ],
        ),
    ]
    
    # Try to call chat() on structured LLM
    try:
        response = structured_llm.chat(messages)
        
        # Check if response has .raw attribute with Pydantic model
        if hasattr(response, "raw") and isinstance(response.raw, SimplePageStructure):
            print("✅ SUCCESS: Structured LLM works with vision!")
            print(f"   Result: {response.raw}")
            return True
        else:
            print("❌ FAILURE: No .raw attribute or wrong type")
            print(f"   Response type: {type(response)}")
            print(f"   Response: {response}")
            return False
    except Exception as exc:
        print(f"❌ ERROR: {type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  Set OPENAI_API_KEY to run this test")
    else:
        test_structured_llm_with_vision()
```

**Expected Outcome:**
- ✅ If successful: Proceed with full implementation
- ❌ If fails: Document limitation and keep manual schema injection as primary method

**Decision Point:** DO NOT proceed to Phase 1 until this test passes.

---

## Implementation Phases

### Phase 1: Add Structured API Method (Parallel Implementation)

**Objective:** Add new method that uses `as_structured_llm()` without breaking existing code.

**Estimated Effort:** 2 hours  
**Risk Level:** Low (additive change only)

#### Step 1.1: Add New Method to Parsing Adapter

**File:** `src/app/adapters/llama_index/parsing_adapter.py`

**Location:** After line 232 (after `_parse_without_structured_llm` method)

**Code to Add:**

```python
def _parse_with_structured_api(
    self,
    document_id: str,
    page_number: int,
    pixmap_path: str,
) -> ParsedPage | None:
    """Parse using LlamaIndex as_structured_llm() API with vision.
    
    This method leverages native structured output support (e.g., OpenAI JSON mode)
    instead of manually injecting schema into prompts.
    
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
        structured_llm = self._llm.as_structured_llm(ParsedPage)
        
        # Build system prompt with context
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
```

#### Step 1.2: Update `parse_page()` to Use New Method

**File:** `src/app/adapters/llama_index/parsing_adapter.py`

**Location:** Lines 80-92 (inside `parse_page()` method)

**Current Code:**
```python
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
```

**New Code:**
```python
try:
    # Priority 1: Use structured API (non-streaming) for maximum reliability
    if self._use_structured_outputs and not self._use_streaming:
        parsed_page = self._parse_with_structured_api(document_id, page_number, pixmap_path)
        if parsed_page:
            self._log_trace(document_id, page_number, pixmap_path, parsed_page)
            return parsed_page
        # If structured API fails, fall through to streaming method
        logger.warning(
            "Structured API failed for doc=%s page=%s, trying streaming method",
            document_id,
            page_number,
        )
    
    # Priority 2: Use manual schema injection with streaming (for progress logs)
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
```

**Behavior Changes:**
- If `use_streaming=False`, tries structured API first
- If structured API fails or streaming is enabled, falls back to existing manual schema injection
- No change in final output structure (still returns `ParsedPage`)

---

### Phase 2: Add Configuration Controls

**Objective:** Make structured output behavior configurable.

**Estimated Effort:** 30 minutes  
**Risk Level:** Low

#### Step 2.1: Update LLMSettings

**File:** `src/app/config.py`

**Location:** After line 24 (inside `LLMSettings` class)

**Code to Add:**
```python
class LLMSettings(BaseModel):
    # ... existing fields ...
    use_structured_outputs: bool = True  # Use as_structured_llm() API when available
    use_streaming: bool = True  # Enable streaming (takes precedence over structured outputs)
```

**Note:** We already have these as parameters to `ImageAwareParsingAdapter.__init__()`, but they're not in config.

#### Step 2.2: Wire Configuration to Container

**File:** `src/app/container.py`

**Location:** Lines where `ImageAwareParsingAdapter` is instantiated (find this in bootstrap)

**Update:**
```python
# Pass settings from config
structured_parser = ImageAwareParsingAdapter(
    llm=llm,
    prompt_settings=self.settings.prompts,
    use_structured_outputs=self.settings.llm.use_structured_outputs,
    use_streaming=self.settings.llm.use_streaming,
    # ... other existing params
)
```

---

### Phase 3: Add Unit Tests

**Objective:** Verify structured API method works correctly.

**Estimated Effort:** 2 hours  
**Risk Level:** Low

#### Step 3.1: Update StubLLM Mock

**File:** `tests/test_parsing_adapter.py`

**Location:** Lines 35-71 (update `StubLLM` class)

**Add Tracking for Structured LLM Calls:**

```python
class StubLLM:
    """Mock LLM that supports as_structured_llm() and structured_predict()."""
    
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.complete_calls: list[tuple] = []
        self._parsed_page = ParsedPage(
            document_id="doc",
            page_number=1,
            raw_text="hello",
            components=[],
        )
        # Cache structured LLM instances so we can track calls
        self._structured_llms: dict[type, StubStructuredLLM] = {}
        # NEW: Track which Pydantic classes were wrapped
        self.structured_llm_calls: list[type] = []
    
    def as_structured_llm(self, pydantic_class: type) -> StubStructuredLLM:
        """Return a mock structured LLM, caching instances by Pydantic class."""
        # Track that this class was used for structured output
        self.structured_llm_calls.append(pydantic_class)
        
        if pydantic_class not in self._structured_llms:
            self._structured_llms[pydantic_class] = StubStructuredLLM(self._parsed_page)
        return self._structured_llms[pydantic_class]
    
    # ... rest of class unchanged
```

#### Step 3.2: Add Test for Structured API

**File:** `tests/test_parsing_adapter.py`

**Location:** End of file (after line 123)

**Code to Add:**

```python
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
    assert isinstance(user_message.content, list), "User message content should be list"
    from llama_index.core.base.llms.types import ImageBlock
    has_image = any(isinstance(item, ImageBlock) for item in user_message.content)
    assert has_image, "User message should contain ImageBlock"
    
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
        return iter([MockChunk('{"document_id": "doc", "page_number": 1, "raw_text": "test", "components": []}')])
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
    """Verify parsing adapter falls back to streaming if structured API fails."""
    pixmap_path = tmp_path / "page.png"
    _write_png(pixmap_path)
    
    llm = StubLLM()
    # Make structured API fail
    original_as_structured = llm.as_structured_llm
    def failing_as_structured(pydantic_class):
        structured = original_as_structured(pydantic_class)
        # Make chat() raise exception
        def failing_chat(messages):
            raise RuntimeError("Structured API failed")
        structured.chat = failing_chat
        return structured
    llm.as_structured_llm = failing_as_structured
    
    # Add working stream_chat
    llm.stream_chat_calls = []
    def mock_stream_chat(messages):
        llm.stream_chat_calls.append(messages)
        class MockChunk:
            def __init__(self, text):
                self.delta = text
        return iter([MockChunk('{"document_id": "doc", "page_number": 1, "raw_text": "fallback", "components": []}')])
    llm.stream_chat = mock_stream_chat
    
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
        use_streaming=False,  # Structured API should be tried first
    )
    
    result = adapter.parse_page(
        document_id="doc",
        page_number=1,
        raw_text="text",
        pixmap_path=str(pixmap_path)
    )
    
    # Verify fallback to streaming happened
    assert len(llm.stream_chat_calls) > 0, \
        "Should fall back to stream_chat() when structured API fails"
    
    # Verify result is valid (from fallback)
    assert isinstance(result, ParsedPage)
    assert result.document_id == "doc"
    assert result.page_number == 1
```

---

### Phase 4: Integration Testing

**Objective:** Verify structured API works with real LLM and real documents.

**Estimated Effort:** 1 hour  
**Risk Level:** Medium (requires API key and costs money)

#### Step 4.1: Create Integration Test

**File:** `tests/test_structured_api_integration.py` (NEW FILE)

**Content:**

```python
"""Integration tests for structured API with real LLM.

These tests require OPENAI_API_KEY and are not run by default.
Run with: pytest tests/test_structured_api_integration.py -v
"""
import os
import pytest
from pathlib import Path

from src.app.adapters.llama_index.parsing_adapter import ImageAwareParsingAdapter
from src.app.config import PromptSettings
from src.app.parsing.schemas import ParsedPage


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set, skipping integration test"
)
def test_structured_api_with_real_llm(tmp_path):
    """Test structured API with real OpenAI LLM."""
    from llama_index.llms.openai import OpenAI
    
    # Create a simple test image with text
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    # Try to use a default font
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except Exception:
        font = ImageFont.load_default()
    draw.text((20, 20), "Test Document\n\nThis is a sample page.", fill="black", font=font)
    
    pixmap_path = tmp_path / "test_page.png"
    img.save(pixmap_path)
    
    # Create adapter with real LLM
    llm = OpenAI(model="gpt-4o-mini", temperature=0.0)
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
        use_streaming=False,  # Use structured API
    )
    
    # Parse the test image
    result = adapter.parse_page(
        document_id="test-doc",
        page_number=1,
        raw_text="",
        pixmap_path=str(pixmap_path)
    )
    
    # Verify result
    assert isinstance(result, ParsedPage)
    assert result.document_id == "test-doc"
    assert result.page_number == 1
    assert result.parsing_status == "success"
    
    # Verify it actually parsed something
    assert result.raw_text != ""
    assert len(result.components) > 0
    
    # Verify text was recognized
    assert "Test Document" in result.raw_text or any(
        "Test Document" in str(c) for c in result.components
    )
    
    print(f"✅ Integration test passed!")
    print(f"   Components: {len(result.components)}")
    print(f"   Raw text length: {len(result.raw_text)}")


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set, skipping integration test"
)
def test_structured_api_vs_streaming_consistency(tmp_path):
    """Verify structured API and streaming produce equivalent results."""
    from llama_index.llms.openai import OpenAI
    from PIL import Image, ImageDraw, ImageFont
    
    # Create test image
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except Exception:
        font = ImageFont.load_default()
    draw.text((20, 20), "Consistency Test\n\nBoth methods should parse this.", fill="black", font=font)
    
    pixmap_path = tmp_path / "consistency_test.png"
    img.save(pixmap_path)
    
    llm = OpenAI(model="gpt-4o-mini", temperature=0.0)
    
    # Parse with structured API
    adapter_structured = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
        use_streaming=False,
    )
    result_structured = adapter_structured.parse_page(
        document_id="test",
        page_number=1,
        raw_text="",
        pixmap_path=str(pixmap_path)
    )
    
    # Parse with streaming (manual schema)
    adapter_streaming = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
        use_streaming=True,
    )
    result_streaming = adapter_streaming.parse_page(
        document_id="test",
        page_number=1,
        raw_text="",
        pixmap_path=str(pixmap_path)
    )
    
    # Both should succeed
    assert result_structured.parsing_status == "success"
    assert result_streaming.parsing_status == "success"
    
    # Both should have similar content
    assert len(result_structured.components) > 0
    assert len(result_streaming.components) > 0
    
    # Text should be similar (allowing for minor LLM variation)
    assert "Consistency Test" in result_structured.raw_text
    assert "Consistency Test" in result_streaming.raw_text
    
    print(f"✅ Consistency test passed!")
    print(f"   Structured components: {len(result_structured.components)}")
    print(f"   Streaming components: {len(result_streaming.components)}")
```

**Run Command:**
```bash
# Skip by default (no API key in CI)
pytest tests/test_parsing_adapter.py -v

# Run integration tests manually (requires API key)
OPENAI_API_KEY=sk-... pytest tests/test_structured_api_integration.py -v
```

---

### Phase 5: Documentation Updates

**Objective:** Document the change and configuration options.

**Estimated Effort:** 30 minutes  
**Risk Level:** Low

#### Step 5.1: Update Architecture Doc

**File:** `docs/ARCHITECTURE.md`

**Section:** "Structured Output Handling" (add new section)

**Content:**

```markdown
### Structured Output Handling

The pipeline uses LlamaIndex's structured output APIs to ensure LLMs return valid Pydantic models:

**Parsing Stage** (`ImageAwareParsingAdapter`):
- Uses `as_structured_llm(ParsedPage)` API when streaming is disabled
- Falls back to manual schema injection when streaming is enabled (for progress logs)
- Configuration: `LLMSettings.use_streaming` (default: True)

**Cleaning Stage** (`CleaningAdapter`):
- Always uses `as_structured_llm(CleanedPage)` for non-vision cleaning
- Uses manual schema injection for vision-based cleaning (multimodal limitation)

**Benefits of Structured API**:
- Native JSON mode support (OpenAI, Anthropic)
- Automatic validation against Pydantic schema
- Eliminates manual JSON extraction from markdown code fences
- More reliable than prompt-based schema injection

**Trade-offs**:
- Structured API doesn't support streaming (JSON structure incomplete during streaming)
- Vision + structured outputs may have provider-specific limitations
```

#### Step 5.2: Update README

**File:** `README.md`

**Section:** Add configuration section

**Content:**

```markdown
### Configuration

#### LLM Settings

```env
# Use native structured output APIs (recommended)
LLM__USE_STRUCTURED_OUTPUTS=true

# Enable streaming for progress logs (disables structured outputs)
LLM__USE_STREAMING=true
```

**Structured Outputs vs. Streaming:**
- Structured outputs use native JSON mode (more reliable)
- Streaming provides real-time progress logs (useful for debugging)
- Cannot use both simultaneously (streaming returns JSON incrementally)
- Default: Streaming is enabled for production observability
```

---

### Phase 6: Rollout Plan

**Objective:** Deploy changes safely with rollback capability.

**Estimated Effort:** 1 hour  
**Risk Level:** Medium

#### Rollout Strategy

**Stage 1: Testing Environment (Week 1)**
1. Deploy with `use_streaming=False` to test structured API
2. Run integration tests with real documents
3. Compare outputs with streaming mode
4. Verify no regressions in parsing quality

**Stage 2: Staged Production Rollout (Week 2)**
1. Deploy with `use_streaming=True` (no behavior change)
2. Monitor for any issues
3. Gradually reduce streaming usage: `use_streaming=False` for 10% of requests
4. Monitor error rates and parsing quality

**Stage 3: Full Rollout (Week 3)**
1. If Stage 2 successful, set `use_streaming=False` as default
2. Keep streaming available as fallback
3. Monitor production metrics

#### Rollback Plan

If issues occur:
1. Set `use_streaming=True` (reverts to old behavior)
2. Investigate root cause
3. Fix structured API method
4. Retry rollout

#### Success Metrics

- ✅ Parsing success rate ≥ current baseline (99%+)
- ✅ Component extraction quality equivalent or better
- ✅ No increase in error rates
- ✅ Logs show "Structured API parsing succeeded" messages

---

## Testing Checklist

Before merging changes:

### Unit Tests
- [ ] `test_parsing_adapter_uses_structured_api_when_not_streaming` passes
- [ ] `test_parsing_adapter_uses_streaming_when_enabled` passes
- [ ] `test_parsing_adapter_falls_back_if_structured_api_fails` passes
- [ ] Existing `test_image_adapter_uses_multimodal_when_pixmap` still passes

### Integration Tests (Manual)
- [ ] Run `test_structured_api_with_real_llm` with real API key
- [ ] Run `test_structured_api_vs_streaming_consistency` to verify equivalence
- [ ] Test with sample PDFs from `tests/doc_*.pdf`

### Architectural Tests
- [ ] Run `pytest tests/test_architecture.py -v`
- [ ] Verify no new architectural violations

### Regression Tests
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Verify all existing tests pass
- [ ] No new linter errors

---

## Risk Mitigation

### Risk 1: Vision + Structured API Incompatibility

**If proof-of-concept test fails:**
1. Keep manual schema injection as primary method
2. Document limitation in code comments
3. File issue with LlamaIndex project
4. Revisit when LlamaIndex adds support

### Risk 2: Performance Degradation

**Mitigation:**
1. Measure latency before/after
2. If structured API is slower, make it opt-in via config
3. Keep streaming as default for production

### Risk 3: Output Quality Regression

**Mitigation:**
1. Compare parsed outputs side-by-side (structured API vs. streaming)
2. Run visual diffs on component extraction
3. If quality degrades, investigate prompt differences
4. Adjust prompts if needed (structured API might interpret differently)

---

## Timeline

| Phase | Task | Estimated Time | Dependencies |
|-------|------|----------------|--------------|
| Pre-1 | Run proof-of-concept test | 30 min | OpenAI API key |
| 1 | Add `_parse_with_structured_api()` method | 1 hour | Proof-of-concept ✅ |
| 1 | Update `parse_page()` logic | 30 min | Phase 1 complete |
| 2 | Add configuration controls | 30 min | Phase 1 complete |
| 3 | Add unit tests | 2 hours | Phase 1 complete |
| 4 | Run integration tests | 1 hour | OpenAI API key |
| 5 | Update documentation | 30 min | Phase 1-4 complete |
| 6 | Deploy and monitor | 1 hour | All phases complete |
| **Total** | | **~6.5 hours** | |

---

## Success Criteria

- ✅ Parsing adapter uses `as_structured_llm()` when streaming is disabled
- ✅ Manual schema injection still works when streaming is enabled
- ✅ All unit tests pass (including new structured API tests)
- ✅ Integration tests pass with real LLM
- ✅ No change in parsing output quality/structure
- ✅ Architectural tests pass (no dependency violations)
- ✅ Documentation updated with configuration details
- ✅ Production rollout successful with no incidents

---

## Next Steps

1. ✅ Share analysis and plan with team
2. 🔄 Run proof-of-concept test (`tests/poc_structured_vision.py`)
3. ⏳ If POC passes, begin Phase 1 implementation
4. ⏳ If POC fails, document limitation and close ticket

---

*End of Implementation Plan*

