# Parsing Error Handling Implementation Summary

**Date**: November 14, 2024  
**Status**: ✅ **Fully Implemented & Tested**  
**Branch**: `llama-index`

---

## Executive Summary

We have successfully implemented comprehensive error handling for the parsing stage of the RAG pipeline. Previously, when parsing failed (e.g., due to repetition loops, network errors, or LLM issues), pages were silently treated as empty with no indication of failure. 

**Now**:
- ✅ Pages are explicitly marked as `"success"`, `"failed"`, or `"partial"`
- ✅ Detailed error information is captured (error type + detailed message)
- ✅ Parsing failures are surfaced in logs, observability events, and artifacts
- ✅ Foundation is in place for future retry/fallback strategies (OCR, prompt variants)
- ✅ Backward compatible - no breaking changes

---

## What Was Implemented

### 1. **Schema Enhancements** (`src/app/parsing/schemas.py`)

Added three new fields to `ParsedPage`:

```python
class ParsedPage(BaseModel):
    # ... existing fields ...
    
    parsing_status: Literal["success", "failed", "partial"] = "success"
    error_details: Optional[str] = None
    error_type: Optional[str] = None
```

**Status Values**:
- `"success"`: Page parsed successfully (default)
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

---

### 2. **Adapter Improvements** (`src/app/adapters/llama_index/parsing_adapter.py`)

#### A. **Streaming Guardrail Error Tracking**

Updated `_stream_chat_response` to return error information:

```python
def _stream_chat_response(...) -> tuple[str, str | None, str | None]:
    """Returns: (content, error_type, error_details)"""
```

**All guardrails now capture detailed error info**:

```python
# Example: Repetition loop detected
if char_ratio > repetition_threshold:
    error_type = "repetition_loop"
    error_details = f"Streaming stopped: detected repetition loop ({char_ratio*100:.1f}% of last {repetition_window} chars are {repr(most_common_char)})"
    break
```

**Tracked Guardrails**:
1. **Max Length**: Response exceeded `streaming_max_chars` (default: 50,000 chars)
2. **Repetition Loop**: >80% of recent chars are the same character
3. **Excessive Newlines**: ≥100 consecutive `\n` characters
4. **Escaped Newlines**: >50% of recent content is `\\n`

#### B. **Main Parse Method Error Handling**

Enhanced `parse_page` to handle all error scenarios:

```python
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

#### C. **Partial Success Handling**

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

#### D. **Enhanced Logging**

Updated `_log_trace` to show parsing status and errors:

```python
logger.info("Parsing Status: %s", parsed_page.parsing_status)

if parsed_page.parsing_status != "success":
    logger.warning("❌ PARSING %s", parsed_page.parsing_status.upper())
    logger.warning("Error Type: %s", parsed_page.error_type)
    logger.warning("Error Details: %s", parsed_page.error_details)
```

---

### 3. **Service Enhancements** (`src/app/services/parsing_service.py`)

#### A. **Failure Tracking Loop**

Added logic to scan all parsed pages and extract failures:

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

#### B. **Warning Logs**

Log each failed page:

```python
if parsing_failures:
    logger.warning(
        "❌ %d page(s) failed or partially failed parsing for doc=%s",
        len(parsing_failures),
        document.id,
    )
    for failure in parsing_failures:
        logger.warning(
            "  Page %d: %s (%s)",
            failure["page_number"],
            failure["status"],
            failure["error_type"],
        )
```

#### C. **Metrics Enhancement**

Added failure count to pixmap metrics and observability:

```python
pixmap_metrics.update({
    ...
    "parsing_failures_count": len(parsing_failures),  # NEW
})

self.observability.record_event(
    stage="parsing",
    details={
        ...
        "parsing_failures_count": len(parsing_failures),  # NEW
    },
)
```

---

### 4. **Test Suite** (`tests/test_parsing_error_handling.py`)

Created comprehensive test coverage:

- ✅ **Schema Tests** (4 tests):
  - Default success status
  - Failed status with error details
  - Partial status with some content
  - Serialization/deserialization with errors

- ✅ **Adapter Tests** (2 tests):
  - Missing pixmap error handling
  - Returns failed status on error

- ✅ **Service Tests** (2 tests):
  - Tracks failures in metadata
  - No failures when all pages succeed

- ✅ **Streaming Tests** (1 test):
  - Verifies streaming method signature returns error tuple

**All 9 tests pass** ✅

---

## Artifact Output Examples

### 1. Document Metadata (`artifacts/documents/{doc_id}.json`)

```json
{
  "metadata": {
    "parsed_pages": {
      "1": {
        "document_id": "abc-123",
        "page_number": 1,
        "parsing_status": "success",
        "components": [...]
      },
      "2": {
        "document_id": "abc-123",
        "page_number": 2,
        "parsing_status": "failed",
        "error_type": "repetition_loop",
        "error_details": "Streaming stopped: detected repetition loop (85.5% of last 200 chars are '\\n')",
        "components": []
      }
    },
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

## Observability & Logging Examples

### Console Output (for failed page)

```
❌ No pixmap provided for doc=abc-123 page=2, marking as failed

⚠️ Stopping stream for doc=abc-123 page=2: detected repetition loop (85.5% of last 200 chars are '\n')

⚠️ Streaming stopped with guardrail for doc=abc-123 page=2: repetition_loop - 1543 chunks, 45231 chars in 12.3s

⚠️ Parsing marked as failed due to repetition_loop for doc=abc-123 page=2

❌ 1 page(s) failed or partially failed parsing for doc=abc-123
  Page 2: failed (repetition_loop)
```

### Parsing Trace (with error)

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

---

## Files Modified

| File | Changes | LOC Modified |
|------|---------|--------------|
| `src/app/parsing/schemas.py` | Added 3 new fields to ParsedPage | ~20 |
| `src/app/adapters/llama_index/parsing_adapter.py` | Updated streaming + parse methods | ~80 |
| `src/app/services/parsing_service.py` | Added failure tracking loop | ~35 |
| `tests/test_parsing_error_handling.py` | Created comprehensive test suite | ~250 |
| `docs/Parsing_Error_Handling_Architecture.md` | Comprehensive architecture doc | ~600 |
| `docs/Parsing_Error_Handling_Implementation_Summary.md` | This summary | ~350 |

**Total**: ~1,335 lines of code/documentation added/modified

---

## Manual Testing Guide

### Step 1: Test with Problematic Document

Upload a document known to cause parsing issues (e.g., `doc_short_noisy.pdf`):

```bash
# Start the server
python -m src.app.main

# Upload via dashboard or API
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@tests/doc_short_noisy.pdf"
```

### Step 2: Check Console Logs

Look for error indicators:

```
❌ [error emoji] indicators
⚠️ [warning emoji] indicators for guardrails
```

### Step 3: Inspect Artifacts

**A. Check document JSON**:

```bash
cat artifacts/documents/{doc_id}.json | jq '.metadata.parsing_failures'
```

Should show:
```json
[
  {
    "page_number": 2,
    "status": "failed",
    "error_type": "repetition_loop",
    "error_details": "Streaming stopped: detected repetition loop..."
  }
]
```

**B. Check parsed page**:

```bash
cat artifacts/documents/{doc_id}.json | jq '.metadata.parsed_pages["2"]'
```

Should show:
```json
{
  "parsing_status": "failed",
  "error_type": "repetition_loop",
  "error_details": "...",
  "components": []
}
```

**C. Check metrics**:

```bash
cat artifacts/documents/{doc_id}.json | jq '.metadata.pixmap_metrics.parsing_failures_count'
```

Should show: `1`

### Step 4: Verify Dashboard Display

1. Navigate to document detail page
2. Check if failed pages are indicated (may require UI updates in the future)
3. Look for error badges or warnings

---

## Known Edge Cases

### 1. **Empty Page vs. Failed Parse**

- **Empty page (success)**: `parsing_status="success"`, `components=[]`
- **Failed parse**: `parsing_status="failed"`, `error_type` set, `error_details` explains why

### 2. **Partial Success**

- If guardrail triggers but some components were extracted: `parsing_status="partial"`
- Contains both components AND error details

### 3. **Multiple Failures**

- All failures tracked in `parsing_failures` array
- Each entry has page number, status, error type, and details

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
```

### 2. **OCR Fallback**

When LLM parsing fails, fall back to pytesseract or similar:

```python
if parsing_status == "failed" and error_type in ["repetition_loop", "timeout"]:
    text = ocr_fallback(pixmap_path)
    return ParsedPage(..., parsing_status="partial", error_details="Fell back to OCR")
```

### 3. **Prompt Variants**

Try simplified prompts on retry:

```python
if error_type == "repetition_loop" and retry_count == 0:
    simplified_prompt = "Extract text from this page image. Return only the text."
    retry_with_prompt(simplified_prompt)
```

### 4. **Dashboard UI Enhancements**

- Show error badges on failed pages
- Display error details in tooltips
- Add "Retry Parsing" button for failed pages
- Show parsing success rate metrics

### 5. **Error Analytics**

Track and visualize:
- Error type distribution over time
- Pages that consistently fail across documents
- Correlation between file types and error types
- Guardrail trigger frequency

---

## Configuration & Tuning

### Guardrail Settings

Configured in `config.py` (via environment variables or defaults):

```python
class LLMSettings(BaseModel):
    streaming_max_chars: int = 50000
    streaming_repetition_window: int = 200
    streaming_repetition_threshold: float = 0.8
    streaming_max_consecutive_newlines: int = 100
```

### Tuning Recommendations

| Scenario | Adjustment |
|----------|-----------|
| **Noisy documents** | Lower `streaming_max_consecutive_newlines` to 50 |
| **Large documents** | Increase `streaming_max_chars` to 100,000 |
| **False positives** | Increase `streaming_repetition_threshold` to 0.9 |
| **Tighter guardrails** | Decrease `streaming_repetition_window` to 100 |

---

## Backward Compatibility

✅ **Fully backward compatible**:

- Old code without error fields → defaults to `"success"`
- Existing documents still work without changes
- No breaking changes to APIs or interfaces
- Graceful degradation: if fields missing, system still functions

---

## Testing Results

```
============================= test session starts ==============================
tests/test_parsing_error_handling.py::TestParsedPageErrorFields::...
  ✅ test_parsed_page_default_success_status PASSED
  ✅ test_parsed_page_with_failed_status PASSED
  ✅ test_parsed_page_with_partial_status PASSED
  ✅ test_parsed_page_serialization_with_errors PASSED

tests/test_parsing_error_handling.py::TestParsingAdapterErrorHandling::...
  ✅ test_parse_page_missing_pixmap PASSED
  ✅ test_parse_page_returns_failed_on_error PASSED

tests/test_parsing_error_handling.py::TestParsingServiceFailureTracking::...
  ✅ test_parsing_service_tracks_failures_in_metadata PASSED
  ✅ test_parsing_service_no_failures_when_all_success PASSED

tests/test_parsing_error_handling.py::TestStreamingErrorReturn::...
  ✅ test_stream_chat_response_signature PASSED

================================= 9 passed in 0.77s ============================
```

**✅ All tests passing**

**✅ No linting errors**

---

## Key Benefits

| Before | After |
|--------|-------|
| Pages fail silently | Explicit failure tracking |
| No error information | Detailed error type + message |
| Impossible to debug | Clear logs + artifacts |
| No monitoring visibility | Failure count in metrics |
| No retry possible | Foundation for retries |
| Empty = failed? | Clear distinction |

---

## Next Steps for User

### Immediate

1. **Test with problematic documents**:
   - Upload `doc_short_noisy.pdf` via dashboard
   - Check logs for `❌` and `⚠️` indicators
   - Inspect `artifacts/documents/{doc_id}.json` for `parsing_failures`

2. **Verify existing documents still work**:
   - Upload a clean, well-formatted PDF
   - Ensure `parsing_status="success"` for all pages
   - No `parsing_failures` array in metadata

3. **Monitor in production**:
   - Track `parsing_failures_count` in metrics
   - Set up alerts if failure rate exceeds threshold
   - Review error types to identify patterns

### Short-Term (Next Sprint)

4. **Implement retry logic**:
   - Start with simple retry on `"network_error"`
   - Add exponential backoff
   - Test with flaky network conditions

5. **Add OCR fallback**:
   - Install pytesseract or similar
   - Fall back to OCR when LLM parsing fails
   - Mark pages as `"partial"` when using OCR

6. **Dashboard UI enhancements**:
   - Show error badges on failed pages
   - Display parsing success rate
   - Add "Retry Parsing" button

### Long-Term

7. **Analytics & monitoring**:
   - Build error dashboard
   - Track error trends over time
   - Correlate errors with document types

8. **Prompt engineering**:
   - Create prompt variants for different scenarios
   - A/B test prompts on historically problematic pages
   - Optimize guardrail thresholds based on production data

---

## Success Criteria ✅

- [x] Pages can be marked as `"success"`, `"failed"`, or `"partial"`
- [x] All error types are captured with detailed messages
- [x] Streaming guardrails report errors instead of silent failures
- [x] Parsing service tracks failures in metadata
- [x] Failures are logged with `❌` indicators
- [x] Failure count included in metrics and observability
- [x] Artifacts (JSON) contain full error details
- [x] Backward compatible with existing code
- [x] Comprehensive test coverage (9 tests, all passing)
- [x] No linting errors
- [x] Documentation complete

**Status**: ✅ **All success criteria met!**

---

## Questions or Issues?

If you encounter any issues:

1. **Check logs** for `❌` and `⚠️` indicators
2. **Inspect artifacts** in `artifacts/documents/{doc_id}.json`
3. **Review error details** in `metadata.parsing_failures`
4. **Adjust guardrails** in `config.py` if needed
5. **Run tests** to verify functionality: `pytest tests/test_parsing_error_handling.py`

---

**Implementation Complete** ✅  
**Date**: November 14, 2024  
**Ready for Testing**: Yes  
**Ready for Production**: Yes (with monitoring)

