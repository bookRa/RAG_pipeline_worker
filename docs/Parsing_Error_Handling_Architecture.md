# Parsing Error Handling Architecture

**Date**: November 14, 2024  
**Status**: ✅ Implemented  
**Purpose**: Comprehensive error handling for parsing failures with detailed diagnostics

---

## Overview

Previously, when parsing failed (e.g., due to streaming guardrails, network errors, or LLM issues), pages were silently treated as empty with no indication of failure. This made debugging difficult and prevented retry strategies.

**Now**: We explicitly track parsing failures with detailed error information, surface them in logs and artifacts, and provide a foundation for future retry/fallback strategies.

---

## Architecture Components

### 1. **Page-Level Status Tracking** (Schema Layer)

#### Enhanced `ParsedPage` Schema

```python
class ParsedPage(BaseModel):
    # ... existing fields ...
    
    # NEW: Parsing status and error tracking
    parsing_status: Literal["success", "failed", "partial"] = "success"
    error_details: Optional[str] = None
    error_type: Optional[str] = None
```

**Status Values**:
- `"success"`: Page parsed successfully
- `"failed"`: Parsing completely failed, no usable content extracted
- `"partial"`: Partial content extracted before failure (e.g., guardrail triggered mid-stream)

**Error Types** (Comprehensive Taxonomy):
- `"repetition_loop"`: LLM stuck in repetition (e.g., continuous `\n` characters)
- `"excessive_newlines"`: Too many consecutive newlines detected
- `"excessive_escaped_newlines"`: Too many escaped `\\n` in JSON
- `"max_length_exceeded"`: Response exceeded maximum character limit
- `"missing_pixmap"`: No pixmap provided for vision parsing
- `"parsing_returned_none"`: All parsing methods failed to return valid page
- `"exception"`: Unexpected exception during parsing
- `"streaming_exception"`: Exception during streaming
- `"network_error"`: (Future) Network/API failure
- `"timeout"`: (Future) Request timeout
- `"validation_error"`: (Future) Schema validation failed

---

### 2. **Graceful Failure Capture** (Adapter Layer)

#### Streaming Guardrail Error Tracking

The `_stream_chat_response` method now returns a tuple:

```python
def _stream_chat_response(
    self,
    messages: list[ChatMessage],
    document_id: str,
    page_number: int,
) -> tuple[str, str | None, str | None]:
    """Returns: (content, error_type, error_details)"""
```

**Guardrail Failure Detection**:

```python
# Example: Repetition loop detected
if char_ratio > repetition_threshold:
    error_type = "repetition_loop"
    error_details = f"Streaming stopped: detected repetition loop ({char_ratio*100:.1f}% of last {repetition_window} chars are {repr(most_common_char)})"
    break
```

**All Guardrails Now Tracked**:
1. **Max Length**: Stops if response exceeds `streaming_max_chars`
2. **Repetition Loop**: Stops if >80% of recent chars are the same character
3. **Excessive Newlines**: Stops if ≥100 consecutive `\n` characters
4. **Escaped Newlines**: Stops if >50% of recent content is `\\n`

#### Main Parse Method Error Handling

```python
def parse_page(...) -> ParsedPage:
    # Missing pixmap
    if not pixmap_path:
        return ParsedPage(
            ...,
            parsing_status="failed",
            error_type="missing_pixmap",
            error_details="No pixmap image provided for vision-based parsing",
        )
    
    # Exception caught
    except Exception as exc:
        return ParsedPage(
            ...,
            parsing_status="failed",
            error_type="exception",
            error_details=f"{type(exc).__name__}: {str(exc)}",
        )
```

**Partial Success Handling**:

When streaming hits a guardrail but extracted some components:

```python
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
```

---

### 3. **Aggregate Error Reporting** (Service Layer)

#### ParsingService Failure Tracking

The `ParsingService` now tracks all failed pages and surfaces them in metadata:

```python
# Track parsing failures
parsing_failures = []
for page_num_str, page_data in parsed_pages_meta.items():
    if page_data.get("parsing_status") != "success":
        parsing_failures.append({
            "page_number": int(page_num_str),
            "status": page_data.get("parsing_status"),
            "error_type": page_data.get("error_type"),
            "error_details": page_data.get("error_details"),
        })

if parsing_failures:
    updated_metadata["parsing_failures"] = parsing_failures
```

**Metadata Structure**:

```json
{
  "parsing_failures": [
    {
      "page_number": 2,
      "status": "failed",
      "error_type": "repetition_loop",
      "error_details": "Streaming stopped: detected repetition loop (85.5% of last 200 chars are '\\n')"
    }
  ],
  "pixmap_metrics": {
    "parsing_failures_count": 1,
    ...
  }
}
```

---

## Observability & Logging

### Enhanced Logging

**1. Adapter-Level Logging**:

```
❌ No pixmap provided for doc=abc-123 page=2, marking as failed

⚠️ Streaming stopped with guardrail for doc=abc-123 page=2: repetition_loop - 1543 chunks, 45231 chars in 12.3s

❌ Parsing failed for doc=abc-123 page=3: OpenAIError: Connection timeout
```

**2. Parsing Trace Enhancement**:

```
================================================================================
🔍 PARSING TRACE - Document: abc-123, Page: 2
================================================================================
Pixmap Path: /path/to/pixmap.png
Parsing Status: failed
--------------------------------------------------------------------------------
❌ PARSING FAILED
--------------------------------------------------------------------------------
Error Type: repetition_loop
Error Details: Streaming stopped: detected repetition loop (85.5% of last 200 chars are '\n')
```

**3. Service-Level Summary**:

```
❌ 1 page(s) failed or partially failed parsing for doc=abc-123
  Page 2: failed (repetition_loop)
```

### Observability Events

```python
self.observability.record_event(
    stage="parsing",
    details={
        "document_id": "abc-123",
        "page_count": 5,
        "parsing_failures_count": 1,  # NEW
        ...
    },
)
```

---

## Artifact Output

### 1. Document JSON (`artifacts/documents/{doc_id}.json`)

```json
{
  "metadata": {
    "parsed_pages": {
      "2": {
        "document_id": "abc-123",
        "page_number": 2,
        "components": [],
        "parsing_status": "failed",
        "error_type": "repetition_loop",
        "error_details": "Streaming stopped: detected repetition loop..."
      }
    },
    "parsing_failures": [
      {
        "page_number": 2,
        "status": "failed",
        "error_type": "repetition_loop",
        "error_details": "Streaming stopped: detected repetition loop..."
      }
    ],
    "pixmap_metrics": {
      "parsing_failures_count": 1
    }
  }
}
```

### 2. Run Artifacts (`artifacts/runs/{run_id}/stages/parsing.json`)

Same structure as document metadata above.

### 3. Run Summary (`artifacts/runs/{run_id}/run.json`)

```json
{
  "stages": [
    {
      "name": "parsing",
      "title": "Parsing",
      "details": {
        "parsing_failures_count": 1,
        ...
      }
    }
  ]
}
```

---

## Benefits

### 1. **Debugging & Diagnostics**

✅ **Before**: Page 2 is empty, no idea why  
✅ **After**: Page 2 failed due to repetition loop, 85% of chars are `\n`

### 2. **Monitoring & Alerts**

Can now track:
- Parsing failure rate per document type
- Most common error types
- Pages that consistently fail

### 3. **Foundation for Retry Logic**

```python
# Future enhancement
if parsing_status == "failed" and error_type == "repetition_loop":
    # Retry with modified prompt
    retry_with_different_prompt()
elif error_type == "network_error":
    # Retry with exponential backoff
    retry_with_backoff()
elif error_type == "missing_pixmap":
    # Fall back to OCR
    fallback_to_ocr()
```

### 4. **Quality Metrics**

```python
# Calculate parsing success rate
total_pages = len(document.pages)
failed_pages = len(metadata["parsing_failures"])
success_rate = (total_pages - failed_pages) / total_pages
```

---

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────────┐
│ ParsingAdapter.parse_page()                                 │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Check pixmap exists                                      │
│     └─ NO → Return ParsedPage(status="failed",              │
│               error_type="missing_pixmap")                   │
│                                                               │
│  2. Try _parse_with_vision_structured()                      │
│     ├─ Streaming enabled:                                    │
│     │  └─ _stream_chat_response()                            │
│     │      ├─ Guardrail triggered?                           │
│     │      │   ├─ YES → Set error_type, error_details        │
│     │      │   └─ NO → error_type = None                     │
│     │      └─ Return (content, error_type, error_details)    │
│     │                                                         │
│     ├─ Parse JSON response                                   │
│     │  ├─ Success + no errors → status="success"            │
│     │  ├─ Success + guardrail → status="partial"/"failed"   │
│     │  └─ Parse failed → return None                         │
│     │                                                         │
│     └─ Exception caught → Return ParsedPage(                 │
│           status="failed", error_type="exception")           │
│                                                               │
│  3. If None returned → Return ParsedPage(                    │
│       status="failed", error_type="parsing_returned_none")   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ ParsingService.parse()                                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  For each page:                                              │
│    1. Call structured_parser.parse_page()                    │
│    2. Store ParsedPage in metadata["parsed_pages"]           │
│                                                               │
│  After all pages:                                            │
│    3. Scan metadata["parsed_pages"] for failures            │
│    4. Build parsing_failures list                            │
│    5. Add to metadata["parsing_failures"]                    │
│    6. Log warning for each failure                           │
│    7. Add count to pixmap_metrics and observability         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Future Enhancements (Not Yet Implemented)

### 1. **Retry Strategies**

```python
class ParsingRetryStrategy:
    def should_retry(self, error_type: str, attempt: int) -> bool:
        if error_type == "network_error" and attempt < 3:
            return True
        if error_type == "repetition_loop" and attempt == 0:
            return True  # Retry once with modified prompt
        return False
    
    def get_retry_config(self, error_type: str) -> dict:
        if error_type == "repetition_loop":
            return {
                "use_streaming": False,  # Disable streaming
                "prompt_variant": "simplified",
            }
        elif error_type == "network_error":
            return {
                "backoff_seconds": 2 ** attempt,
            }
```

### 2. **OCR Fallback**

```python
if parsing_status == "failed" and error_type in ["repetition_loop", "timeout"]:
    # Fall back to pytesseract or similar
    text = ocr_fallback(pixmap_path)
    return ParsedPage(
        document_id=doc_id,
        page_number=page_num,
        raw_text=text,
        components=[ParsedTextComponent(order=0, text=text)],
        parsing_status="partial",
        error_details="Fell back to OCR after LLM parsing failed",
    )
```

### 3. **Prompt Variants**

```python
# If repetition loop, try simplified prompt
if error_type == "repetition_loop" and retry_count == 0:
    simplified_prompt = "Extract text from this page image. Return only the text."
    retry_with_prompt(simplified_prompt)
```

### 4. **Error Analytics Dashboard**

Track and visualize:
- Error type distribution
- Pages with consistent failures
- Correlation between file types and error types
- Guardrail trigger frequency

---

## Configuration

### Guardrail Settings (in `config.py`)

```python
class LLMSettings(BaseModel):
    # Streaming guardrails
    streaming_max_chars: int = 50000
    streaming_repetition_window: int = 200
    streaming_repetition_threshold: float = 0.8
    streaming_max_consecutive_newlines: int = 100
```

**Tuning Recommendations**:
- **Noisy documents**: Lower `streaming_max_consecutive_newlines` to 50
- **Large documents**: Increase `streaming_max_chars` to 100000
- **Reduce false positives**: Increase `streaming_repetition_threshold` to 0.9

---

## Testing

### Manual Testing

1. **Upload `doc_short_noisy.pdf`** (known to cause repetition loops)
2. **Check logs** for `❌` indicators:
   ```
   ❌ Parsing failed for doc=xxx page=2
   ⚠️ Streaming stopped with guardrail: repetition_loop
   ❌ 1 page(s) failed parsing
   ```
3. **Inspect `artifacts/documents/{doc_id}.json`**:
   - Look for `parsing_failures` array
   - Check `parsed_pages[2].parsing_status == "failed"`
   - Verify `error_details` describes the issue

### Automated Testing

```python
def test_parsing_failure_tracked():
    # Mock LLM to throw error
    mock_llm.side_effect = TimeoutError("Connection timeout")
    
    parsed_page = adapter.parse_page(doc_id="test", page_number=1, pixmap_path="test.png")
    
    assert parsed_page.parsing_status == "failed"
    assert parsed_page.error_type == "exception"
    assert "TimeoutError" in parsed_page.error_details
```

---

## Backward Compatibility

✅ **Fully backward compatible**:
- Old code without error fields → defaults to `success`
- Existing documents still work
- No breaking changes to APIs

**Graceful Degradation**:
- If `parsing_status` missing → assume `"success"`
- If `error_details` missing → no error info shown (but page still usable)

---

## Summary

| Aspect | Before | After |
|--------|---------|-------|
| **Failed pages** | Treated as empty, no indication | Explicitly marked with status |
| **Error details** | None, silent failure | Error type + detailed message |
| **Debugging** | Impossible to diagnose | Clear logs + artifacts |
| **Monitoring** | No visibility | Failure count + metrics |
| **Retry logic** | Not possible | Foundation in place |
| **Observability** | Page just "empty" | Full failure taxonomy |

---

## Key Files Modified

1. **`src/app/parsing/schemas.py`**
   - Added `parsing_status`, `error_type`, `error_details` to `ParsedPage`

2. **`src/app/adapters/llama_index/parsing_adapter.py`**
   - Updated `_stream_chat_response` to return error info
   - Enhanced `parse_page` to set failure status
   - Updated `_parse_with_vision_structured` to handle guardrail errors
   - Enhanced `_log_trace` to show error details

3. **`src/app/services/parsing_service.py`**
   - Added failure tracking loop
   - Created `parsing_failures` metadata array
   - Enhanced logging for failed pages
   - Added failure count to metrics

---

## Next Steps for User

1. **Test with problematic documents**:
   - Upload `doc_short_noisy.pdf`
   - Check logs for error indicators
   - Inspect artifacts for failure details

2. **Monitor failure patterns**:
   - Which error types are most common?
   - Which documents consistently fail?
   - Are guardrail thresholds appropriate?

3. **Plan retry strategies** (future):
   - For `repetition_loop` → Try without streaming
   - For `network_error` → Exponential backoff
   - For `timeout` → OCR fallback

4. **Tune guardrails if needed**:
   - Adjust thresholds in `config.py`
   - Monitor false positive rate
   - Balance between catching loops vs. allowing long responses

---

**Status**: ✅ Fully Implemented and Ready for Testing

The parsing pipeline now has comprehensive error handling that makes failures visible, debuggable, and actionable!

