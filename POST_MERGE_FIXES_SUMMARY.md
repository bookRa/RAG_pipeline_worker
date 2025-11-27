# Post-Merge Bug Fixes - Implementation Summary

This document summarizes all fixes applied to resolve critical bugs after merging the batching and observability branches.

## Date: 2025-11-26

## Issues Fixed

### 1. ✅ AttributeError: 'Document' object has no attribute 'chunks'

**Problem**: Code was attempting to access `document.chunks` directly, but chunks are stored in `page.chunks` within each `Page` object.

**Files Changed**: `src/app/services/batch_pipeline_runner.py`

**Fixes Applied** (4 locations):
- Line 294-298: Chunking stage - Changed to `sum(len(page.chunks) for page in document.pages)`
- Line 353-358: Vectorization stage - Changed to nested iteration over pages and chunks
- Line 374: Pipeline complete trace - Changed to calculate total chunks from all pages

**Impact**: Batch processing will now complete without AttributeError for all files.

---

### 2. ✅ Langfuse Span Context Manager Errors

**Problem**: Code was calling `span.__enter__()` and `span.__exit__()` on Langfuse `StatefulSpanClient` objects, which don't support the context manager protocol.

**Files Changed**: `src/app/observability/batch_logger.py`

**Fixes Applied**:
- `start_span()` method (lines 172-194): Removed `span.__enter__()` call
- `end_span()` method (lines 196-213): Removed `span.__exit__()` call, now calls `span.end()` directly

**Impact**: No more "'StatefulSpanClient' object has no attribute '__enter__'" errors in terminal logs.

---

### 3. ✅ Missing Error Stack Traces

**Problem**: Exception handlers only logged error messages without full stack traces, making debugging extremely difficult.

**Files Changed**:
- `src/app/services/batch_pipeline_runner.py`
- `src/app/application/use_cases/batch_upload_use_case.py`
- `src/app/services/parallel_page_processor.py`

**Fixes Applied**:
- Added `import traceback` to batch_pipeline_runner
- Added `exc_info=True` to all `logger.error()` calls
- Added full `traceback.format_exc()` to Langfuse trace outputs
- Fixed duplicate exception handlers in parallel_page_processor

**Impact**: Full error stack traces now visible in both logs and Langfuse traces.

---

### 4. ✅ Langfuse Trace Inconsistencies

**Problem**: Trace naming and structure differed between batch and single-file processing.

**Files Changed**:
- `src/app/services/batch_pipeline_runner.py`
- `src/app/observability/batch_logger.py`

**Fixes Applied**:
- Changed trace name from `"document_pipeline"` to `f"document_pipeline::{document.filename}"` (consistent with single-file)
- Added batch_id to trace input_data for correlation
- Updated trace tags to include `["pipeline", file_type, "batch", batch_id]` (consistent with single-file)
- Enhanced metadata to include process_id and thread_id for debugging

**Impact**: Consistent trace naming and structure across both processing modes.

---

### 5. ✅ Missing Pixmap Previews in Batch Processing

**Problem**: Image previews only worked for non-batch uploads; batch processing lacked pixmap preview integration.

**Files Changed**: `src/app/services/batch_pipeline_runner.py`

**Fixes Applied**:
- Added imports: `mimetypes`, `os`, `Path`, `LangfuseMedia`
- Added `DEFAULT_PIXMAP_PREVIEW_LIMIT` constant
- Added `pixmap_preview_limit` to `__init__`
- Added `_collect_pixmap_previews()` helper method (copied from pipeline_runner)
- Integrated pixmap preview collection after parsing stage
- Added pixmap_previews to parsing span end call
- Added pixmap_count to parsing event logging

**Impact**: Image previews now work in both batch and single-file processing modes.

---

### 6. ✅ Large Input Truncation Investigation

**Problem**: Parsing traces showed `<truncated due to size exceeding limit>` warnings.

**Investigation Results**:
- Confirmed parsing is done page-by-page (not whole document)
- Each page is processed individually with proper pixmap handling
- Truncation is expected Langfuse behavior for large vision model inputs (pixmaps can be several MB)
- Images are already being resized with `max_pixmap_bytes` limit
- Actual LLM calls and outputs are captured correctly; only display is truncated

**Conclusion**: This is expected and acceptable behavior. No code changes needed.

---

## Testing Instructions

### Prerequisites
1. Ensure Langfuse is configured in `.env`:
   ```bash
   LANGFUSE__ENABLED=true
   LANGFUSE__PUBLIC_KEY=pk-lf-...
   LANGFUSE__SECRET_KEY=sk-lf-...
   LANGFUSE__HOST=https://cloud.langfuse.com
   ```

2. Start the application:
   ```bash
   python -m uvicorn src.app.main:app --reload
   ```

### Test Case 1: Batch Processing (3 Files)

1. **Upload Files**:
   ```bash
   curl -X POST "http://localhost:8000/batch/upload" \
     -F "files=@tests/doc_short_clean.pdf" \
     -F "files=@tests/doc_short_noisy.pdf" \
     -F "files=@tests/doc_short_welding.pdf"
   ```

2. **Expected Results**:
   - ✅ All 3 files complete without AttributeError
   - ✅ Batch dashboard shows all documents as "completed"
   - ✅ No Langfuse span context manager errors in terminal
   - ✅ Langfuse UI shows 3 traces named `document_pipeline::doc_short_*.pdf`
   - ✅ Each trace includes pixmap previews
   - ✅ All traces tagged with `["pipeline", "pdf", "batch", "<batch_id>"]`

3. **Check Terminal Logs**:
   - ✅ No "'StatefulSpanClient' object has no attribute '__enter__'" errors
   - ✅ No "'Document' object has no attribute 'chunks'" errors
   - ✅ Clean progress logging with batch_id correlation

### Test Case 2: Single File Processing

1. **Upload Single File**:
   ```bash
   curl -X POST "http://localhost:8000/upload" \
     -F "file=@tests/doc_short_clean.pdf"
   ```

2. **Expected Results**:
   - ✅ File processes successfully
   - ✅ Langfuse trace named `document_pipeline::doc_short_clean.pdf`
   - ✅ Trace includes pixmap previews
   - ✅ Same level of detail as batch processing
   - ✅ Trace tagged with `["pipeline", "pdf"]`

### Test Case 3: Error Scenario

1. **Upload Invalid File** (create a corrupt PDF or use wrong file type):
   ```bash
   echo "invalid content" > /tmp/corrupt.pdf
   curl -X POST "http://localhost:8000/batch/upload" \
     -F "files=@/tmp/corrupt.pdf"
   ```

2. **Expected Results**:
   - ✅ Error appears in batch dashboard
   - ✅ Full stack trace in terminal logs with `exc_info`
   - ✅ Error details in Langfuse trace with full traceback
   - ✅ Other files in batch continue processing (if error_strategy=continue)

### Test Case 4: Langfuse UI Validation

1. **Open Langfuse Dashboard**: Navigate to https://cloud.langfuse.com

2. **Check Trace List**:
   - ✅ All traces have consistent naming: `document_pipeline::{filename}`
   - ✅ Batch traces grouped by session_id/batch_id
   - ✅ Tags correctly applied for filtering

3. **Check Individual Trace**:
   - ✅ Spans: ingestion → parsing → cleaning → chunking → enrichment → vectorization
   - ✅ Parsing span includes pixmap previews (images visible)
   - ✅ All LLM calls properly captured
   - ✅ Token counts and costs tracked
   - ✅ No missing data in outputs

4. **Check Batch Trace Granularity**:
   - ✅ Each document in batch has own complete trace
   - ✅ Page-level operations visible in parsing/cleaning
   - ✅ Pixmap generation events logged
   - ✅ Same detail level as single-file traces
   - ✅ Additional batch metrics present

---

## Code Quality

- ✅ All linter errors resolved
- ✅ No type errors
- ✅ Consistent code style
- ✅ Proper error handling throughout
- ✅ Comprehensive logging with stack traces

---

## Migration Notes

**Breaking Changes**: None

**Backward Compatibility**: Fully maintained

**Environment Variables**: No new variables required

---

## Summary of Changes

| File | Lines Changed | Type |
|------|---------------|------|
| `src/app/services/batch_pipeline_runner.py` | ~100 | Major |
| `src/app/observability/batch_logger.py` | ~30 | Major |
| `src/app/services/parallel_page_processor.py` | ~15 | Minor |
| `src/app/application/use_cases/batch_upload_use_case.py` | ~5 | Minor |

**Total Impact**: 4 files modified, ~150 lines changed

---

## Next Steps

1. ✅ Run comprehensive tests (see Testing Instructions above)
2. ✅ Verify Langfuse traces are clean and informative
3. ✅ Monitor production logs for any remaining issues
4. ✅ Demo both single and batch processing to stakeholders

---

## Notes on Input Truncation

The `<truncated due to size exceeding limit>` messages in Langfuse are **expected behavior** when using vision models with large images. This is Langfuse's way of handling very large inputs for display purposes. The actual LLM calls are working correctly, and outputs are captured fully.

**Why this happens**:
- Vision parsing sends pixmap images (can be several MB)
- Langfuse limits display size for performance
- Truncation only affects UI display, not actual processing
- Metadata and outputs are still fully captured

**Mitigation already in place**:
- Images are resized with `max_pixmap_bytes` limit
- Page-by-page processing (not whole document)
- Proper chunking strategy
- Efficient image compression

**No action needed** - this is working as designed.

