# Structured Output Analysis & Remediation Plan

**Date:** November 14, 2025  
**Author:** AI Coding Agent (Review Agent Role)  
**Status:** Analysis Complete, Implementation Pending

---

## Executive Summary

This document analyzes how our RAG pipeline solicits structured responses from LLMs across all pipeline stages, compares our implementation against LlamaIndex best practices, and provides a comprehensive remediation plan for non-compliant implementations.

**Key Findings:**
- ✅ **Cleaning stage** correctly uses `as_structured_llm()` API
- ❌ **Parsing stage** manually injects JSON schema (not fool-proof)
- ⚠️ **Summarization stage** has no structured output (plain text only)

**Impact:** The parsing stage is vulnerable to:
- LLM returning markdown-wrapped JSON requiring manual extraction
- Schema validation failures that could be handled by LlamaIndex
- Missing out on native structured output support (e.g., OpenAI's JSON mode)

---

## Pipeline Stages & LLM Integration Analysis

### Stage 1: Parsing (ImageAwareParsingAdapter)

**Location:** `src/app/adapters/llama_index/parsing_adapter.py`

**Current Implementation:**
```python
# Lines 152-158: Manual schema injection
schema = ParsedPage.model_json_schema()
schema_instruction = (
    "\n\nRespond ONLY with valid JSON that matches this schema:\n"
    f"{json.dumps(schema, indent=2)}\n"
    "Do not include any markdown formatting, code fences, or explanations."
)
full_system_prompt = system_prompt_with_context + schema_instruction

# Lines 165-173: Manual chat() call
messages = [
    ChatMessage(role="system", content=full_system_prompt),
    ChatMessage(role="user", content=[ImageBlock(image=image_data, ...)]),
]

# Lines 182-196: Manual response parsing with code fence extraction
response = self._llm.chat(messages)
content = self._extract_content_from_response(response)
# Manual JSON extraction from markdown fences...
parsed_page = ParsedPage.model_validate_json(content)
```

**Compliance Status:** ❌ **NON-COMPLIANT**

**Issues:**
1. **No native structured output support**: Manually injecting schema doesn't leverage OpenAI's JSON mode or other providers' structured output features
2. **Brittle parsing**: Requires manual extraction from markdown code fences (lines 187-194)
3. **Error-prone**: If LLM returns malformed JSON or includes extra text, parsing fails
4. **Inconsistent with cleaning stage**: Different approaches for same problem
5. **Vision + streaming complication**: Uses `chat()` with streaming, which may complicate structured output integration

**Why not using `as_structured_llm()`?**
- Vision models traditionally didn't support structured outputs in LlamaIndex
- Streaming support was a concern
- However, modern LLMs (GPT-4o-mini) support both vision AND structured outputs

---

### Stage 2: Cleaning (CleaningAdapter)

**Location:** `src/app/adapters/llama_index/cleaning_adapter.py`

**Current Implementation:**
```python
# Lines 144-151: CORRECT usage of as_structured_llm()
def _clean_with_structured_llm(self, request_json: str, parsed_page: ParsedPage) -> CleanedPage | None:
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
```

**Compliance Status:** ✅ **COMPLIANT**

**Strengths:**
1. Uses `as_structured_llm(CleanedPage)` to wrap the LLM
2. Response automatically validates against Pydantic schema
3. Native structured output support when available
4. Clean extraction via `response.raw`
5. Has fallback methods for non-structured mode

**Note:** Vision-based cleaning (lines 208-281) still uses manual schema injection because it uses `chat()` with images. This is a similar limitation to parsing.

---

### Stage 3: Enrichment/Summarization (LlamaIndexSummaryAdapter)

**Location:** `src/app/adapters/llama_index/summary_adapter.py`

**Current Implementation:**
```python
# Lines 20-26: Simple complete() with no structure
def summarize(self, text: str) -> str:
    if not text.strip():
        return ""
    try:
        completion = self._llm.complete(f"{self._prompt}\n\n{text.strip()}")
        completion_text = extract_response_text(completion)
        return completion_text.strip()
    except Exception as exc:
        logger.warning("LLM summary failed, falling back to truncate: %s", exc)
        return text[:280].strip()
```

**Compliance Status:** ⚠️ **ACCEPTABLE (Plain Text Output)**

**Analysis:**
- Summarization is inherently unstructured (just returns text)
- No need for Pydantic schema unless we want structured summaries (e.g., title + summary + keywords)
- Current implementation is fine for simple text summaries
- **Opportunity:** Could be enhanced to return structured metadata (see recommendations)

---

## LlamaIndex Best Practices (from Documentation)

Based on [LlamaIndex Structured Outputs Guide](https://developers.llamaindex.ai/python/examples/structured_outputs/structured_outputs):

### Method 1: `as_structured_llm()` (Wrapper Approach)

```python
from pydantic import BaseModel

class OutputSchema(BaseModel):
    response: str
    confidence: float

# Wrap LLM with schema
structured_llm = llm.as_structured_llm(output_cls=OutputSchema)

# Use complete() or chat()
response = structured_llm.complete("Your prompt here")

# Access structured output
result: OutputSchema = response.raw
```

**Pros:**
- Explicit and clear
- Works with both `complete()` and `chat()`
- Response object has `.raw` attribute with parsed Pydantic model
- Automatic validation

**Cons:**
- Need to wrap LLM explicitly
- May not work seamlessly with streaming (implementation-dependent)

---

### Method 2: `structured_predict()` (One-Line Approach)

```python
from llama_index.core.prompts import ChatPromptTemplate

# Define prompt template
prompt_template = ChatPromptTemplate(...)

# One-line structured prediction
result = llm.structured_predict(
    OutputSchema, 
    prompt_template, 
    movie_name="Lord of the Rings"
)

# result is already the Pydantic model
assert isinstance(result, OutputSchema)
```

**Pros:**
- Most concise API
- Handles template formatting and structure in one call
- Returns Pydantic model directly (not wrapped in response)
- Ideal for simple prompts

**Cons:**
- Less control over the LLM call
- May not support advanced features (streaming, vision, etc.)

---

### When Native Structured Outputs Are Used

According to LlamaIndex documentation, when using OpenAI models with `as_structured_llm()` or `structured_predict()`:

1. **JSON Mode is automatically enabled** if the model supports it (GPT-4o, GPT-4o-mini, etc.)
2. **Response format parameter** is set to enforce JSON output
3. **Automatic retry logic** if parsing fails
4. **Validation happens automatically** using Pydantic

This means models will be constrained to return valid JSON matching the schema, reducing hallucinations and parsing errors.

---

## Root Cause Analysis: Why Parsing Stage Doesn't Use Structured APIs

### Historical Context

The parsing stage was implemented with these constraints:
1. **Vision input required**: Needs to pass images via `ChatMessage` with `ImageBlock`
2. **Streaming support**: Implements custom streaming with guardrails (lines 310-550)
3. **Complex prompt structure**: System prompt + user message with image
4. **Early implementation**: May predate robust structured output support for multimodal models

### Technical Barriers

**Barrier 1: Vision + Structured Outputs**
- `as_structured_llm()` traditionally worked with `complete()` (text-only)
- Vision requires `chat()` with messages containing image blocks
- Unclear if `as_structured_llm().chat()` supports image content

**Barrier 2: Streaming + Structured Outputs**
- Parsing uses `stream_chat()` for real-time progress logging (lines 310-550)
- Structured outputs may not work with streaming (model returns JSON incrementally)
- Custom guardrails check for runaway responses

**Barrier 3: Complex Message Structure**
- System prompt + user message with image requires `chat(messages=[...])`
- Structured LLM might expect simpler prompt strings via `complete()`

---

## Recommended Solution Strategy

### Option A: Use `as_structured_llm()` with Non-Streaming Chat (RECOMMENDED)

**Approach:**
1. Create structured LLM wrapper: `structured_llm = self._llm.as_structured_llm(ParsedPage)`
2. Use `structured_llm.chat(messages)` with vision-enabled messages
3. Disable streaming for parsing (or keep as fallback)
4. Let LlamaIndex handle JSON extraction and validation

**Pros:**
- Consistent with cleaning adapter
- Native structured output support
- Automatic validation
- Cleaner code (no manual JSON extraction)

**Cons:**
- Lose real-time streaming progress logs
- Need to verify vision + structured outputs work together

**Fallback Plan:**
- Keep streaming as a separate code path
- Use structured outputs when streaming is disabled
- Document the trade-off (streaming vs. structured guarantees)

---

### Option B: Hybrid Approach - Structured for Non-Streaming, Manual for Streaming

**Approach:**
1. Use `as_structured_llm()` when streaming is disabled
2. Keep manual schema injection when streaming is enabled
3. Add configuration flag: `use_streaming_for_parsing`

**Pros:**
- Best of both worlds
- Maintains streaming diagnostics for debugging
- Gradual migration path

**Cons:**
- Code duplication (two paths)
- More complex testing

---

### Option C: Upgrade to `structured_predict()` (FUTURE)

**Approach:**
1. Wait for LlamaIndex to support vision + structured_predict()
2. Use one-line API when available

**Pros:**
- Simplest API
- Future-proof

**Cons:**
- Not available yet (vision + structured_predict unclear)
- Blocks immediate improvements

---

## Implementation Plan

### Phase 1: Research & Validation (CURRENT)

**Tasks:**
- ✅ Analyze current structured output usage across pipeline
- ✅ Document compliance vs. best practices
- 🔄 Test if `as_structured_llm().chat()` supports vision (ImageBlock content)
- 🔄 Test if structured outputs work with streaming

**Deliverable:** This analysis document

---

### Phase 2: Parsing Adapter Refactor (PRIORITY)

**Goal:** Update `ImageAwareParsingAdapter` to use `as_structured_llm()` for non-streaming mode

**Changes:**

1. **Add structured parsing method:**
```python
def _parse_with_vision_structured_api(
    self,
    document_id: str,
    page_number: int,
    pixmap_path: str,
) -> ParsedPage | None:
    """Parse using as_structured_llm() API with vision."""
    try:
        # Create structured LLM wrapper
        structured_llm = self._llm.as_structured_llm(ParsedPage)
        
        # Build messages with image
        system_prompt_with_context = (
            f"{self._system_prompt}\n\n"
            f"Document ID: {document_id}\n"
            f"Page Number: {page_number}"
        )
        
        image_data = encode_image(pixmap_path)
        messages = [
            ChatMessage(role="system", content=system_prompt_with_context),
            ChatMessage(
                role="user",
                content=[ImageBlock(image=image_data, image_mimetype="image/png")],
            ),
        ]
        
        # Call chat() on structured LLM wrapper
        response = structured_llm.chat(messages)
        
        # Extract Pydantic object from response.raw
        if hasattr(response, "raw") and isinstance(response.raw, ParsedPage):
            parsed_page = response.raw
            # Ensure IDs are correct (LLM might get them wrong)
            parsed_page = parsed_page.model_copy(
                update={
                    "document_id": document_id,
                    "page_number": page_number,
                }
            )
            return parsed_page
        elif hasattr(response, "text"):
            # Fallback: try to parse from text
            return ParsedPage.model_validate_json(response.text)
    except Exception as exc:
        logger.warning(
            "Structured API parsing failed for doc=%s page=%s: %s",
            document_id,
            page_number,
            exc,
        )
    return None
```

2. **Update `parse_page()` method to try structured API first:**
```python
def parse_page(self, *, document_id: str, page_number: int, raw_text: str = "", pixmap_path: str | None = None) -> ParsedPage:
    if not pixmap_path:
        # ... existing error handling
        
    try:
        # Try structured API first (if not streaming)
        if self._use_structured_outputs and not self._use_streaming:
            parsed_page = self._parse_with_vision_structured_api(document_id, page_number, pixmap_path)
            if parsed_page:
                self._log_trace(document_id, page_number, pixmap_path, parsed_page)
                return parsed_page
        
        # Fallback to manual schema injection (for streaming mode)
        if self._use_streaming or not self._use_structured_outputs:
            parsed_page = self._parse_with_vision_structured(document_id, page_number, pixmap_path)
            if parsed_page:
                self._log_trace(document_id, page_number, pixmap_path, parsed_page)
                return parsed_page
    except Exception as exc:
        # ... existing error handling
```

3. **Update configuration:**
```python
# src/app/config.py
class LLMSettings(BaseModel):
    # ... existing fields
    use_structured_outputs: bool = True  # Enable as_structured_llm() API
    use_streaming: bool = True  # Enable streaming (incompatible with structured outputs)
```

**Testing Requirements:**
- Verify `as_structured_llm().chat()` works with vision
- Test that `response.raw` contains valid `ParsedPage` model
- Test fallback to manual parsing if structured API fails
- Verify document_id and page_number are correctly overridden

---

### Phase 3: Cleaning Adapter Enhancement (OPTIONAL)

**Goal:** Make vision-based cleaning use structured API if possible

**Current Issue:** Vision cleaning (line 208-281) uses manual schema injection

**Solution:** Apply same pattern as parsing - try `as_structured_llm().chat()` with vision

**Priority:** Low (cleaning already uses structured API for non-vision mode)

---

### Phase 4: Summarization Enhancement (OPTIONAL)

**Goal:** Add structured summary output with metadata

**Current:** Plain text summaries

**Enhancement:** Return structured summaries with metadata
```python
from pydantic import BaseModel, Field

class StructuredSummary(BaseModel):
    """Structured summary with metadata."""
    summary: str = Field(description="2-3 sentence summary")
    key_topics: list[str] = Field(description="Main topics (3-5 items)")
    document_type: str = Field(description="Type: technical manual, research paper, etc.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in summary quality")
```

**Benefits:**
- Richer metadata for RAG retrieval
- Structured topics for filtering
- Document classification

**Priority:** Low (not required for correctness)

---

### Phase 5: Test Suite Updates (REQUIRED)

**Goal:** Ensure tests verify structured output usage

**New Tests:**

1. **Test structured API with vision:**
```python
def test_parsing_adapter_uses_structured_api_with_vision(tmp_path):
    """Verify parsing adapter uses as_structured_llm() when streaming is disabled."""
    pixmap_path = tmp_path / "page.png"
    _write_png(pixmap_path)
    
    llm = StubLLM()
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
        use_streaming=False,  # Disable streaming to use structured API
    )
    
    result = adapter.parse_page(
        document_id="doc",
        page_number=1,
        raw_text="text",
        pixmap_path=str(pixmap_path)
    )
    
    # Verify structured LLM was used
    assert ParsedPage in llm._structured_llms, "Should create structured LLM wrapper"
    structured_llm = llm._structured_llms[ParsedPage]
    assert len(structured_llm.chat_calls) > 0, "Should call chat() on structured LLM"
    
    # Verify result is valid
    assert isinstance(result, ParsedPage)
    assert result.document_id == "doc"
    assert result.page_number == 1
```

2. **Test streaming mode still works:**
```python
def test_parsing_adapter_streaming_mode_still_works(tmp_path):
    """Verify streaming mode still works with manual schema injection."""
    pixmap_path = tmp_path / "page.png"
    _write_png(pixmap_path)
    
    llm = StubStreamingLLM()  # Mock that supports stream_chat()
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
        use_streaming=True,  # Enable streaming
    )
    
    result = adapter.parse_page(
        document_id="doc",
        page_number=1,
        raw_text="text",
        pixmap_path=str(pixmap_path)
    )
    
    # Verify streaming was used
    assert len(llm.stream_chat_calls) > 0, "Should call stream_chat()"
    
    # Verify result is still valid
    assert isinstance(result, ParsedPage)
```

3. **Test cleaning adapter structured output:**
```python
def test_cleaning_adapter_uses_structured_llm():
    """Verify cleaning adapter correctly uses as_structured_llm()."""
    llm = StubLLM()
    adapter = CleaningAdapter(
        llm=llm,
        prompt_settings=PromptSettings(),
        use_structured_outputs=True,
    )
    
    parsed_page = ParsedPage(
        document_id="doc",
        page_number=1,
        raw_text="hello",
        components=[],
    )
    
    result = adapter.clean_page(parsed_page)
    
    # Verify structured LLM was used
    assert CleanedPage in llm._structured_llms, "Should create structured LLM wrapper"
    structured_llm = llm._structured_llms[CleanedPage]
    assert len(structured_llm.complete_calls) > 0, "Should call complete() on structured LLM"
    
    # Verify result
    assert isinstance(result, CleanedPage)
```

**Priority:** High (required before merging changes)

---

## Risk Assessment

### Risk 1: Vision + Structured Outputs Incompatibility

**Description:** `as_structured_llm().chat()` might not support image content in messages

**Likelihood:** Medium  
**Impact:** High (blocks implementation)

**Mitigation:**
1. Create proof-of-concept test with actual OpenAI API
2. Check LlamaIndex GitHub issues/docs for vision + structured output support
3. If unsupported, keep manual schema injection as primary method
4. Document limitation and revisit when LlamaIndex adds support

---

### Risk 2: Streaming + Structured Outputs Conflict

**Description:** Structured outputs might not work with streaming (JSON returned incrementally)

**Likelihood:** High  
**Impact:** Medium (lose streaming diagnostics)

**Mitigation:**
1. Make streaming and structured outputs mutually exclusive
2. Add config flag to choose: `use_streaming=True` → manual schema, `use_streaming=False` → structured API
3. Keep streaming as default for production (diagnostics are valuable)
4. Use structured API for testing/validation

---

### Risk 3: Breaking Changes to Parsing Output

**Description:** Structured API might return slightly different ParsedPage structure

**Likelihood:** Low  
**Impact:** High (breaks downstream stages)

**Mitigation:**
1. Comprehensive integration tests before/after
2. Compare outputs from both methods on same documents
3. Schema validation ensures compatibility
4. Keep fallback to manual parsing

---

## Success Criteria

### Phase 2 Success (Parsing Adapter):
- ✅ Parsing adapter uses `as_structured_llm()` when streaming is disabled
- ✅ Manual schema injection still works when streaming is enabled
- ✅ All existing parsing tests pass
- ✅ New tests verify structured API usage
- ✅ No change in parsed output quality/structure

### Phase 5 Success (Test Suite):
- ✅ Tests explicitly verify `as_structured_llm()` is called
- ✅ Tests verify `response.raw` contains correct Pydantic model
- ✅ Tests cover both streaming and non-streaming modes
- ✅ Integration tests pass with real documents

### Overall Success:
- ✅ All LLM-backed stages use LlamaIndex structured output APIs (when applicable)
- ✅ Manual schema injection only used where necessary (streaming mode)
- ✅ Code is cleaner and more maintainable
- ✅ Native structured output support leveraged (OpenAI JSON mode, etc.)

---

## Open Questions

1. **Does `as_structured_llm().chat()` support vision (ImageBlock) content?**
   - Need to test with actual LlamaIndex + OpenAI
   - Check LlamaIndex documentation/examples

2. **Can structured outputs work with streaming?**
   - Likely no (JSON structure incomplete during streaming)
   - Need to confirm and document trade-off

3. **Should summarization stage use structured outputs?**
   - Current plain text is fine
   - Structured summaries (with metadata) would be valuable enhancement
   - Not urgent

4. **Should we update vision-based cleaning to use structured API?**
   - Low priority (non-vision cleaning already uses it)
   - Same limitations as parsing (vision + structured API)

---

## References

- [LlamaIndex Structured Outputs Guide](https://developers.llamaindex.ai/python/examples/structured_outputs/structured_outputs)
- [OpenAI Structured Outputs Documentation](https://platform.openai.com/docs/guides/structured-outputs)
- Current implementation:
  - `src/app/adapters/llama_index/parsing_adapter.py` (lines 126-232)
  - `src/app/adapters/llama_index/cleaning_adapter.py` (lines 137-166)
  - `src/app/adapters/llama_index/summary_adapter.py` (lines 20-29)

---

## Next Steps

1. **Immediate:** Share this analysis with team for review
2. **Short-term:** Test vision + structured outputs compatibility (proof-of-concept)
3. **Medium-term:** Implement Phase 2 (parsing adapter refactor) if compatible
4. **Long-term:** Consider Phase 4 (structured summaries) for enhanced RAG metadata

---

## Appendix: Code Comparison

### Current Parsing (Manual Schema Injection)

```python
# Build schema instruction
schema = ParsedPage.model_json_schema()
schema_instruction = "\n\nRespond ONLY with valid JSON that matches this schema:\n" + json.dumps(schema)
full_system_prompt = system_prompt + schema_instruction

# Call chat
messages = [ChatMessage(role="system", content=full_system_prompt), ...]
response = self._llm.chat(messages)

# Manual extraction
content = self._extract_content_from_response(response)
if "```json" in content:
    start = content.find("```json") + 7
    end = content.find("```", start)
    content = content[start:end].strip()
parsed_page = ParsedPage.model_validate_json(content)
```

### Proposed Parsing (Structured API)

```python
# Create structured LLM
structured_llm = self._llm.as_structured_llm(ParsedPage)

# Call chat (same messages)
messages = [ChatMessage(role="system", content=system_prompt), ...]
response = structured_llm.chat(messages)

# Extract from response.raw
if hasattr(response, "raw") and isinstance(response.raw, ParsedPage):
    parsed_page = response.raw
```

**Lines Saved:** ~15 lines of manual extraction logic  
**Reliability:** Higher (native JSON mode, automatic validation)  
**Maintainability:** Better (consistent with cleaning adapter)

---

*End of Analysis Document*

