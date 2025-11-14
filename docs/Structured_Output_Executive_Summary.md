# Executive Summary: Structured Output Audit & Remediation

**Date:** November 14, 2025  
**Scope:** RAG Pipeline LLM Integration Compliance Review  
**Outcome:** 1 of 3 stages non-compliant with LlamaIndex best practices

---

## Quick Answer to Your Question

You asked:
> *"According to the llama-index documentation... there is a proper way to get structured output from an llm that supports it. However, I see that we are doing things like passing the schema into the system prompt, which is not a fool-proof way of ensuring that the llm returns the requested json."*

**You are 100% correct.** 

Our **parsing stage** manually injects JSON schema into prompts and then manually extracts JSON from the response (including stripping markdown code fences). This is:
- ❌ Not fool-proof (LLM can return malformed JSON or extra text)
- ❌ Missing native structured output support (OpenAI JSON mode, etc.)
- ❌ Inconsistent with our cleaning stage (which correctly uses `as_structured_llm()`)

---

## What We Found

### ✅ COMPLIANT: Cleaning Stage

**File:** `src/app/adapters/llama_index/cleaning_adapter.py`

**What it does right:**
```python
# Lines 144-151
structured_llm = self._llm.as_structured_llm(CleanedPage)
response = structured_llm.complete(prompt_text)
return response.raw  # Already a validated Pydantic model
```

This is the **correct** LlamaIndex pattern:
- Uses `as_structured_llm()` to wrap LLM with schema
- Response automatically validates against `CleanedPage` Pydantic model
- Native JSON mode enabled when supported (e.g., OpenAI)
- No manual JSON extraction needed

---

### ❌ NON-COMPLIANT: Parsing Stage

**File:** `src/app/adapters/llama_index/parsing_adapter.py`

**What it does wrong:**
```python
# Lines 152-158: Manual schema injection
schema = ParsedPage.model_json_schema()
schema_instruction = "\n\nRespond ONLY with valid JSON..."
full_system_prompt = system_prompt + schema_instruction

# Lines 165-173: Manual chat() call (no structured wrapper)
messages = [ChatMessage(role="system", content=full_system_prompt), ...]
response = self._llm.chat(messages)

# Lines 186-196: Manual JSON extraction (brittle!)
content = self._extract_content_from_response(response)
if "```json" in content:
    start = content.find("```json") + 7
    end = content.find("```", start)
    content = content[start:end].strip()
parsed_page = ParsedPage.model_validate_json(content)
```

**Problems:**
1. No native structured output support (missing OpenAI JSON mode)
2. Brittle parsing (manual markdown code fence extraction)
3. Error-prone (if LLM adds extra text or malforms JSON, parsing fails)
4. Inconsistent with cleaning stage

**Why this happened:**
- Parsing uses **vision** (images via `ImageBlock`) + **streaming** (for progress logs)
- Both features may complicate structured output integration
- Implementation may predate robust multimodal structured output support

---

### ⚠️ ACCEPTABLE: Summarization Stage

**File:** `src/app/adapters/llama_index/summary_adapter.py`

**What it does:**
```python
# Lines 20-26: Plain text completion
completion = self._llm.complete(f"{self._prompt}\n\n{text.strip()}")
return completion_text.strip()
```

**Analysis:**
- Summarization is inherently **unstructured** (just returns text)
- No Pydantic schema needed for plain text
- Current implementation is fine for basic summaries

**Opportunity for enhancement (optional):**
Could return structured summaries with metadata:
```python
class StructuredSummary(BaseModel):
    summary: str
    key_topics: list[str]
    document_type: str
    confidence: float
```

But this is **not required for correctness**.

---

## Recommended Solution

### Use `as_structured_llm()` for Parsing (When Not Streaming)

**Proposed Implementation:**

```python
def _parse_with_structured_api(self, document_id, page_number, pixmap_path):
    """Use as_structured_llm() API for maximum reliability."""
    # Wrap LLM with schema
    structured_llm = self._llm.as_structured_llm(ParsedPage)
    
    # Build messages with image
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=[ImageBlock(image=..., ...)]),
    ]
    
    # Call chat() on structured wrapper
    response = structured_llm.chat(messages)
    
    # Extract validated Pydantic model
    return response.raw  # Already a ParsedPage instance!
```

**Benefits:**
- Native JSON mode (OpenAI, Anthropic)
- Automatic validation
- No manual JSON extraction
- Consistent with cleaning adapter

**Trade-offs:**
- May not work with streaming (JSON returned incrementally)
- Need to verify vision + structured outputs compatibility

---

## Implementation Strategy

### Phase 1: Proof of Concept (30 min)

Test if `as_structured_llm().chat()` works with vision:
```python
structured_llm = llm.as_structured_llm(ParsedPage)
messages = [ChatMessage(role="user", content=[ImageBlock(...)])]
response = structured_llm.chat(messages)
assert isinstance(response.raw, ParsedPage)  # Does this work?
```

**Decision Point:** Only proceed if this test passes.

---

### Phase 2: Hybrid Implementation (2 hours)

Add structured API path **alongside** existing streaming path:

```python
def parse_page(self, ...):
    # Priority 1: Use structured API (non-streaming)
    if self._use_structured_outputs and not self._use_streaming:
        parsed_page = self._parse_with_structured_api(...)
        if parsed_page:
            return parsed_page
    
    # Priority 2: Fall back to streaming (with manual schema)
    if self._use_streaming:
        parsed_page = self._parse_with_vision_structured(...)  # Existing method
        if parsed_page:
            return parsed_page
```

**Configuration:**
```python
# config.py
class LLMSettings:
    use_structured_outputs: bool = True  # Enable as_structured_llm()
    use_streaming: bool = True  # Enable streaming (takes precedence)
```

**Behavior:**
- Default: `use_streaming=True` → uses existing manual schema injection (no change)
- Test/prod: `use_streaming=False` → uses new structured API (more reliable)

---

### Phase 3: Testing (2 hours)

**Unit Tests:**
```python
def test_parsing_uses_structured_api_when_not_streaming():
    """Verify as_structured_llm() is called when streaming=False."""
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        use_structured_outputs=True,
        use_streaming=False,  # KEY
    )
    result = adapter.parse_page(...)
    assert ParsedPage in llm.structured_llm_calls
```

**Integration Tests:**
- Test with real OpenAI LLM + real images
- Compare outputs: structured API vs. streaming
- Verify consistency

---

### Phase 4: Rollout (1 week)

1. **Week 1:** Deploy with `use_streaming=True` (no change)
2. **Week 2:** Gradually test `use_streaming=False` on 10% of requests
3. **Week 3:** If successful, make structured API default

**Rollback:** Set `use_streaming=True` to revert to old behavior

---

## Detailed Documentation

I've created two comprehensive documents:

### 1. Analysis Document
**File:** `docs/Structured_Output_Analysis.md`

**Contents:**
- Stage-by-stage breakdown of LLM integration
- Comparison to LlamaIndex best practices
- Root cause analysis (why parsing doesn't use structured API)
- Recommended solutions with pros/cons
- Risk assessment
- Code examples showing before/after

### 2. Implementation Plan
**File:** `docs/Structured_Output_Implementation_Plan.md`

**Contents:**
- Step-by-step implementation guide (6 phases)
- Proof-of-concept test script
- Code changes with exact line numbers
- Unit test additions
- Integration test suite
- Configuration changes
- Rollout strategy with rollback plan
- Success criteria and timeline (~6.5 hours)

---

## Key Decisions Required

### Decision 1: Run Proof-of-Concept Test

**Question:** Does `as_structured_llm().chat()` work with vision (ImageBlock content)?

**Action:** Run `tests/poc_structured_vision.py` (script provided in implementation plan)

**Outcome:**
- ✅ **If passes:** Proceed with full implementation
- ❌ **If fails:** Document limitation, keep manual schema injection

---

### Decision 2: Streaming vs. Structured Outputs

**Question:** Which should be the default?

**Options:**
1. **Streaming** (current default): Real-time progress logs, manual schema
2. **Structured API**: Native JSON mode, more reliable, no streaming

**Recommendation:** Keep streaming as default for production (observability is valuable), but make structured API available for testing/validation.

---

### Decision 3: Should Summarization Use Structured Outputs?

**Question:** Should we enhance summarization to return structured metadata?

**Current:** Plain text summaries  
**Enhanced:** Structured summaries with topics, type, confidence

**Recommendation:** **Not required**. Plain text is fine for summaries. Enhanced structure is a nice-to-have for future RAG improvements, but not necessary for correctness.

---

## Risks & Mitigations

### Risk 1: Vision + Structured API Incompatibility
**Likelihood:** Medium  
**Impact:** High (blocks implementation)  
**Mitigation:** Proof-of-concept test (Phase 1) will reveal this early

### Risk 2: Streaming + Structured API Conflict
**Likelihood:** High  
**Impact:** Medium (lose streaming diagnostics)  
**Mitigation:** Make them mutually exclusive via config flag

### Risk 3: Output Quality Regression
**Likelihood:** Low  
**Impact:** High (breaks downstream)  
**Mitigation:** Comprehensive testing, side-by-side comparison

---

## Timeline

| Phase | Estimated Time |
|-------|----------------|
| Proof-of-concept | 30 min |
| Implementation | 2 hours |
| Unit tests | 2 hours |
| Integration tests | 1 hour |
| Documentation | 30 min |
| Rollout & monitoring | 1 hour |
| **Total** | **~7 hours** |

---

## Next Steps (Recommended)

1. ✅ **Review analysis** (`docs/Structured_Output_Analysis.md`)
2. ✅ **Review implementation plan** (`docs/Structured_Output_Implementation_Plan.md`)
3. 🔄 **Run proof-of-concept test** to verify vision + structured output compatibility
4. ⏳ **If POC passes:** Begin implementation (start with Phase 1)
5. ⏳ **If POC fails:** Document limitation and revisit when LlamaIndex adds support

---

## Summary

**You were right:** We're not using LlamaIndex structured output APIs properly in the parsing stage.

**Good news:** 
- Cleaning stage is already compliant
- Summarization stage doesn't need structured outputs
- We have a clear path to fix parsing stage

**Action items:**
1. Run proof-of-concept test
2. Implement hybrid approach (structured API + streaming fallback)
3. Comprehensive testing
4. Gradual rollout

**Estimated effort:** ~7 hours for full implementation and testing

---

## References

- **Analysis:** `docs/Structured_Output_Analysis.md`
- **Implementation Plan:** `docs/Structured_Output_Implementation_Plan.md`
- **LlamaIndex Guide:** https://developers.llamaindex.ai/python/examples/structured_outputs/structured_outputs
- **Current Parsing Code:** `src/app/adapters/llama_index/parsing_adapter.py` (lines 126-232)
- **Current Cleaning Code:** `src/app/adapters/llama_index/cleaning_adapter.py` (lines 137-166)

---

*End of Executive Summary*

