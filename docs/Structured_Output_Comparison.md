# Structured Output: Current vs. Proposed

This document provides a visual comparison of how we currently get structured responses vs. the LlamaIndex best practice.

---

## Current Implementation (Parsing Stage)

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Build Prompt with Manual Schema Injection               │
│                                                             │
│   schema = ParsedPage.model_json_schema()                   │
│   prompt = f"{system_prompt}\n\n{schema_instruction}"      │
│   prompt += f"\n{json.dumps(schema)}"                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Call LLM (No Structured Wrapper)                        │
│                                                             │
│   messages = [                                              │
│       ChatMessage(role="system", content=prompt),           │
│       ChatMessage(role="user", content=[ImageBlock(...)]),  │
│   ]                                                          │
│   response = llm.chat(messages)  # or llm.stream_chat()    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Manually Extract JSON from Response                     │
│                                                             │
│   content = response.message.content                        │
│   if "```json" in content:                                  │
│       start = content.find("```json") + 7                   │
│       end = content.find("```", start)                      │
│       content = content[start:end].strip()                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Manually Validate with Pydantic                         │
│                                                             │
│   parsed_page = ParsedPage.model_validate_json(content)     │
│                                                             │
│   ⚠️  Can fail if LLM returns:                              │
│      - Markdown wrapped JSON                                │
│      - Extra text before/after JSON                         │
│      - Malformed JSON                                       │
└─────────────────────────────────────────────────────────────┘
```

### Issues

❌ **No native JSON mode** (missing OpenAI `response_format` parameter)  
❌ **Brittle extraction** (manual code fence parsing)  
❌ **Error-prone** (LLM not constrained to return only JSON)  
❌ **Inconsistent** (cleaning stage uses proper API)

---

## Proposed Implementation (LlamaIndex Best Practice)

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Wrap LLM with Schema (One Line!)                        │
│                                                             │
│   structured_llm = llm.as_structured_llm(ParsedPage)        │
│                                                             │
│   ✨ This automatically:                                    │
│      - Enables native JSON mode (OpenAI, Anthropic)        │
│      - Sets response_format parameter                       │
│      - Adds Pydantic validation                            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Call LLM (Using Structured Wrapper)                     │
│                                                             │
│   messages = [                                              │
│       ChatMessage(role="system", content=prompt),           │
│       ChatMessage(role="user", content=[ImageBlock(...)]),  │
│   ]                                                          │
│   response = structured_llm.chat(messages)                  │
│                                                             │
│   ✨ LLM is constrained to return valid JSON!              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Extract Validated Model (Automatic!)                    │
│                                                             │
│   parsed_page = response.raw                                │
│   # response.raw is already a ParsedPage instance!          │
│                                                             │
│   ✅ No manual JSON extraction                              │
│   ✅ Automatic validation                                   │
│   ✅ Type-safe (IDE autocomplete works)                     │
└─────────────────────────────────────────────────────────────┘
```

### Benefits

✅ **Native JSON mode** (uses OpenAI's structured output feature)  
✅ **Clean extraction** (no manual parsing)  
✅ **Reliable** (LLM constrained to return valid JSON)  
✅ **Consistent** (matches cleaning stage implementation)  
✅ **Type-safe** (`response.raw` is strongly typed)

---

## Side-by-Side Code Comparison

### Current (Manual Schema Injection)

```python
# src/app/adapters/llama_index/parsing_adapter.py (lines 126-232)

def _parse_with_vision_structured(self, document_id, page_number, pixmap_path):
    # Step 1: Manually inject schema into prompt
    schema = ParsedPage.model_json_schema()
    schema_instruction = (
        "\n\nRespond ONLY with valid JSON that matches this schema:\n"
        f"{json.dumps(schema, indent=2)}\n"
        "Do not include any markdown formatting, code fences, or explanations."
    )
    full_system_prompt = system_prompt + schema_instruction
    
    # Step 2: Call LLM without structured wrapper
    image_data = encode_image(pixmap_path)
    messages = [
        ChatMessage(role="system", content=full_system_prompt),
        ChatMessage(role="user", content=[ImageBlock(image=image_data, ...)]),
    ]
    
    if self._use_streaming:
        content, error_type, error_details = self._stream_chat_response(messages, ...)
    else:
        response = self._llm.chat(messages)
        content = self._extract_content_from_response(response)
    
    # Step 3: Manually extract JSON from markdown code fences
    if content:
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()
        
        # Step 4: Manually validate with Pydantic
        parsed_page = ParsedPage.model_validate_json(content)
        return parsed_page
    
    return None
```

**Line Count:** ~50 lines  
**Manual Steps:** 4 (inject, call, extract, validate)

---

### Proposed (Structured API)

```python
# NEW METHOD (to be added)

def _parse_with_structured_api(self, document_id, page_number, pixmap_path):
    # Step 1: Create structured LLM wrapper
    structured_llm = self._llm.as_structured_llm(ParsedPage)
    
    # Step 2: Build messages (no schema injection needed!)
    system_prompt_with_context = f"{self._system_prompt}\n\nDocument ID: {document_id}\nPage Number: {page_number}"
    image_data = encode_image(pixmap_path)
    messages = [
        ChatMessage(role="system", content=system_prompt_with_context),
        ChatMessage(role="user", content=[ImageBlock(image=image_data, ...)]),
    ]
    
    # Step 3: Call structured LLM
    response = structured_llm.chat(messages)
    
    # Step 4: Extract validated model (automatic!)
    if hasattr(response, "raw") and isinstance(response.raw, ParsedPage):
        parsed_page = response.raw
        # Ensure IDs are correct
        parsed_page = parsed_page.model_copy(
            update={"document_id": document_id, "page_number": page_number}
        )
        return parsed_page
    
    return None
```

**Line Count:** ~25 lines  
**Manual Steps:** 0 (all automatic via LlamaIndex)

**Lines Saved:** ~25 lines (~50% reduction)  
**Reliability:** Higher (native JSON mode + automatic validation)

---

## Cleaning Stage (Already Correct!)

For comparison, here's how the cleaning stage already does it correctly:

```python
# src/app/adapters/llama_index/cleaning_adapter.py (lines 137-166)

def _clean_with_structured_llm(self, request_json, parsed_page):
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
        logger.warning(...)
    return None
```

✅ **This is the pattern we want to replicate for parsing!**

---

## Configuration Strategy

### Option 1: Make Structured API Default (Recommended)

```python
# config.py
class LLMSettings(BaseModel):
    use_structured_outputs: bool = True  # Default: use as_structured_llm()
    use_streaming: bool = False  # Default: no streaming (enables structured outputs)
```

**Pros:**
- Most reliable (native JSON mode)
- Consistent with cleaning stage
- Simpler code

**Cons:**
- Lose streaming progress logs (useful for debugging)

---

### Option 2: Keep Streaming as Default (Production)

```python
# config.py
class LLMSettings(BaseModel):
    use_structured_outputs: bool = True  # Enable structured outputs when possible
    use_streaming: bool = True  # Default: use streaming (disables structured outputs)
```

**Pros:**
- Real-time progress logs (valuable for production observability)
- Backward compatible (no behavior change)

**Cons:**
- Doesn't leverage structured API by default
- Manual schema injection still primary method

---

### Option 3: Hybrid (Best of Both Worlds)

```python
# Parsing logic
if use_structured_outputs and not use_streaming:
    # Use structured API (most reliable)
    parsed_page = self._parse_with_structured_api(...)
    if parsed_page:
        return parsed_page

# Fallback to streaming with manual schema
if use_streaming:
    parsed_page = self._parse_with_vision_structured(...)  # Existing method
    return parsed_page
```

**Pros:**
- Structured API available when streaming not needed
- Streaming available when diagnostics needed
- Flexible (can switch via config)

**Cons:**
- Two code paths to maintain

**Recommendation:** Use Option 3 (hybrid approach)

---

## Testing Strategy

### Unit Tests

```python
def test_parsing_uses_structured_api_when_not_streaming():
    """Verify as_structured_llm() is used when streaming=False."""
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        use_structured_outputs=True,
        use_streaming=False,  # KEY: Disable streaming
    )
    
    result = adapter.parse_page(...)
    
    # Verify structured LLM was created
    assert ParsedPage in llm.structured_llm_calls
    
    # Verify chat() was called on structured wrapper
    structured_llm = llm._structured_llms[ParsedPage]
    assert len(structured_llm.chat_calls) > 0


def test_parsing_uses_streaming_when_enabled():
    """Verify streaming (manual schema) is used when streaming=True."""
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        use_structured_outputs=True,
        use_streaming=True,  # KEY: Enable streaming
    )
    
    result = adapter.parse_page(...)
    
    # Verify stream_chat() was called
    assert len(llm.stream_chat_calls) > 0
    
    # Verify structured API was NOT used
    assert ParsedPage not in llm.structured_llm_calls
```

---

### Integration Tests

```python
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), ...)
def test_structured_api_with_real_llm():
    """Test structured API with real OpenAI LLM."""
    llm = OpenAI(model="gpt-4o-mini")
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        use_structured_outputs=True,
        use_streaming=False,
    )
    
    result = adapter.parse_page(...)
    
    assert isinstance(result, ParsedPage)
    assert result.parsing_status == "success"
    assert len(result.components) > 0
```

---

## Migration Path

### Phase 1: Add New Method (Non-Breaking)

- Add `_parse_with_structured_api()` method
- Don't change existing behavior
- Keep manual schema injection as primary method

**Risk:** None (additive only)

---

### Phase 2: Make Available via Config

- Add `use_streaming` config flag
- If `use_streaming=False`, use structured API
- If `use_streaming=True`, use existing method

**Risk:** Low (opt-in behavior)

---

### Phase 3: Test in Production

- Deploy with `use_streaming=True` (no change)
- Gradually test `use_streaming=False` on subset of requests
- Monitor error rates and parsing quality

**Risk:** Low (gradual rollout)

---

### Phase 4: Make Default (Optional)

- If Phase 3 successful, set `use_streaming=False` as default
- Keep streaming available as opt-in for debugging

**Risk:** Medium (behavior change for all requests)

---

## Summary Table

| Aspect | Current (Manual) | Proposed (Structured API) |
|--------|------------------|---------------------------|
| **Code Lines** | ~50 | ~25 |
| **Native JSON Mode** | ❌ No | ✅ Yes |
| **Manual Extraction** | ❌ Yes (brittle) | ✅ No (automatic) |
| **Type Safety** | ⚠️ Partial | ✅ Full |
| **Consistency** | ❌ Different from cleaning | ✅ Same as cleaning |
| **Streaming Support** | ✅ Yes | ❌ No (incompatible) |
| **Reliability** | ⚠️ Medium | ✅ High |
| **Maintainability** | ⚠️ Medium | ✅ High |

---

## Recommendation

✅ **Implement hybrid approach:**
1. Add `_parse_with_structured_api()` method
2. Use structured API when `use_streaming=False`
3. Keep existing method for `use_streaming=True`
4. Default: `use_streaming=True` (production observability)
5. Testing: `use_streaming=False` (maximum reliability)

This gives us the **best of both worlds**:
- Structured API available for testing/validation
- Streaming available for production diagnostics
- Gradual migration path with rollback capability

---

*End of Comparison Document*

