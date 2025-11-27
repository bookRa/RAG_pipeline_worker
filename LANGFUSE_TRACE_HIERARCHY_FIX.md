# Langfuse Trace Hierarchy Fix

## Problem Summary

After the initial post-merge fixes, Langfuse traces were cluttered and difficult to navigate:

1. **Separate top-level traces**: LlamaIndex LLM calls (Cleaning LLM, Document Summary LLM, etc.) appeared as separate top-level traces instead of being nested under document pipeline traces
2. **Poor hierarchy**: Had to click into document traces to see LLM sub-traces
3. **Cluttered trace list**: Dozens of separate traces instead of organized hierarchy
4. **Duplicate/confusing traces**: Some traces appeared multiple times or had unclear purposes
5. **Empty exceptions**: Some traces showed `{"exception":{}}` without useful information
6. **Missing image previews**: Pixmap images not displaying in batch traces

## Root Cause

The batch processing code created manual traces via `batch_logger.start_trace()`, but **did not call `set_root()` on the Langfuse handler**. This meant:

- LlamaIndex LLM operations didn't know about the parent document trace
- Each LLM call created a new top-level trace instead of nesting
- The trace hierarchy was flat instead of properly nested

## Solution Implemented

### 1. Set Root Trace for Proper Nesting

**File**: `src/app/observability/batch_logger.py`

**Changes in `start_trace()`**:

```python
# BEFORE: Only created trace
self._trace = self.langfuse_handler.langfuse.trace(...)

# AFTER: Create trace AND set as root for nested operations
self._trace = self.langfuse_handler.langfuse.trace(...)

# CRITICAL FIX: Set as root trace
if hasattr(self.langfuse_handler, "set_root"):
    self.langfuse_handler.set_root(self._trace, update_root=False)
```

This tells the LlamaIndex Langfuse handler: "All subsequent LLM calls should nest under this trace."

**Changes in `end_trace()`**:

```python
# Clear the root trace when done so next document doesn't accidentally nest
if hasattr(self.langfuse_handler, "set_root"):
    self.langfuse_handler.set_root(None, update_root=False)
```

### 2. Set Trace Parameters

Added `set_trace_params()` call before creating trace to configure the LlamaIndex handler with proper metadata:

```python
if hasattr(self.langfuse_handler, "set_trace_params"):
    self.langfuse_handler.set_trace_params(
        name=name,
        session_id=self.batch_id or document_id,
        metadata=metadata,
        tags=tags,
    )
```

### 3. Session ID for Grouping

Ensured all traces use the batch_id as session_id for proper grouping in Langfuse UI.

## Expected Trace Hierarchy After Fix

### Batch Processing (3 files)

```
Langfuse Trace List (1 session):
├─ batch_document_processing (top-level batch trace)
├─ document_pipeline::doc_short_clean.pdf
│  ├─ ingestion (span)
│  ├─ parsing (span)
│  │  └─ LlamaIndex_completion (nested LLM call)
│  ├─ cleaning (span)
│  │  └─ Cleaning LLM (nested LLM call)
│  ├─ chunking (span)
│  ├─ enrichment (span)
│  │  ├─ Document Summary LLM (nested LLM call)
│  │  └─ Chunk Summary LLM (nested LLM calls)
│  └─ vectorization (span)
├─ document_pipeline::doc_short_noisy.pdf
│  └─ (same structure)
└─ document_pipeline::doc_short_welding.pdf
   └─ (same structure)
```

### Key Improvements

1. **Clean trace list**: Only 4 top-level traces (1 batch + 3 documents) instead of dozens
2. **Proper nesting**: All LLM calls nested under their respective document traces
3. **Easy navigation**: Click document trace → see all operations including LLM calls
4. **Clear hierarchy**: Batch → Documents → Pipeline Stages → LLM Operations

## What You Should See Now

### ✅ In Langfuse Trace List

- **4 traces total** for a 3-document batch:
  - 1× `batch_document_processing`
  - 3× `document_pipeline::{filename}.pdf`
- **No separate LlamaIndex_completion or LlamaIndex_chat traces** at top level
- All traces grouped by session (batch_id)

### ✅ Inside a Document Trace

When you click `document_pipeline::doc_name.pdf`:

1. **Spans tab** shows:
   - ingestion
   - parsing (with nested LLM call)
   - cleaning (with Cleaning LLM nested)
   - chunking
   - enrichment (with Document Summary LLM + multiple Chunk Summary LLM nested)
   - vectorization

2. **Observations tab** shows all nested LLM generations

3. **Metadata tab** shows:
   - batch_id
   - document_job_id
   - process_id
   - thread_id
   - file_type
   - size_bytes

### ✅ LLM Operations

- **Cleaning LLM**: Shows raw text input → cleaned text output
- **Document Summary LLM**: Shows page summaries → document summary
- **Chunk Summary LLM**: Shows chunk text + context → chunk summary
- **Parsing LLM**: Shows pixmap image → structured ParsedPage output

### ✅ Image Previews

- Pixmap previews should display in the parsing span
- LangfuseMedia objects properly attached
- Images visible without clicking through multiple layers

## Testing Instructions

### 1. Clear Previous Test Data

To avoid confusion with old traces, either:
- Wait for traces to naturally organize (Langfuse processes async)
- Filter by timestamp to see only new traces
- Use a new batch upload

### 2. Run Batch Upload

```bash
curl -X POST "http://localhost:8000/batch/upload" \
  -F "files=@tests/doc_short_clean.pdf" \
  -F "files=@tests/doc_short_noisy.pdf" \
  -F "files=@tests/doc_short_welding.pdf"
```

### 3. Check Langfuse UI

**A. Trace List View**:
- ✅ Should see exactly 4 traces (1 batch + 3 documents)
- ✅ All tagged with batch ID
- ✅ All have timestamp from same batch run
- ✅ Consistent naming: `document_pipeline::{filename}`
- ❌ Should NOT see separate LlamaIndex_completion traces

**B. Click into Document Trace**:
- ✅ See 6 spans: ingestion, parsing, cleaning, chunking, enrichment, vectorization
- ✅ Click parsing span → see nested LLM completion
- ✅ Click cleaning span → see Cleaning LLM nested
- ✅ Click enrichment span → see Document Summary LLM + multiple Chunk Summary LLMs
- ✅ All LLM calls show proper inputs/outputs
- ✅ Images display in parsing operations

**C. Timeline View**:
- ✅ Shows proper sequence and nesting
- ✅ Parallel page processing visible
- ✅ LLM calls properly indented under pipeline stages

**D. Batch Trace**:
- ✅ Click `batch_document_processing` trace
- ✅ Shows summary: 3 documents, processing time, success/failure counts
- ✅ Links to individual document traces

### 4. Compare with Single-File Upload

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@tests/doc_short_clean.pdf"
```

- ✅ Single trace: `document_pipeline::doc_short_clean.pdf`
- ✅ Same structure as batch document traces
- ✅ Same LLM nesting behavior
- ✅ Consistent metadata and tags

## Troubleshooting

### Issue: Still seeing separate LlamaIndex traces

**Possible Causes**:
1. Old traces from before the fix (check timestamp)
2. Langfuse handler not properly initialized
3. Multiple handler instances interfering

**Solutions**:
- Filter Langfuse by timestamp > current time
- Restart application to ensure clean handler state
- Check logs for "Failed to set root trace" warnings

### Issue: Empty exception traces

**Possible Causes**:
1. LlamaIndex internal error handling
2. Retry logic creating extra traces

**Solutions**:
- Check if these are old traces (before fix)
- Look for actual errors in application logs
- These should disappear with proper nesting

### Issue: Image previews not showing

**Possible Causes**:
1. Pixmap generation disabled
2. Image size exceeded limits
3. LangfuseMedia not imported

**Solutions**:
- Check `LANGFUSE_PIXMAP_PREVIEW_LIMIT` env var (default: 2)
- Check pixmap generation logs
- Verify LangfuseMedia is properly imported

### Issue: Truncated inputs

**This is expected and OK**:
- Vision model inputs (pixmaps) can be several MB
- Langfuse truncates display for performance
- Actual processing and outputs are unaffected
- Full data is still captured, just not displayed

## Technical Details

### Why set_root() Works

The LlamaIndex Langfuse handler maintains a "root trace" context. When LLM operations are triggered:

1. Handler checks: "Is there a root trace set?"
2. If YES: Create LLM generation nested under root trace
3. If NO: Create new top-level trace

By calling `set_root(self._trace)` in `start_trace()`, we tell the handler: "This document trace is the root for all subsequent operations."

By calling `set_root(None)` in `end_trace()`, we clean up so the next document starts fresh.

### Why set_trace_params() Helps

`set_trace_params()` configures the handler with metadata, tags, and session_id. This ensures:
- All nested operations inherit these parameters
- Consistent tagging across the trace tree
- Proper session grouping in Langfuse UI

### Session ID Strategy

- **Single file**: session_id = run_id or document_id
- **Batch**: session_id = batch_id for all documents in batch
- This groups all batch operations together in Langfuse sessions view

## Migration from Old Traces

**Note**: Old traces (before this fix) will remain in Langfuse with the flat structure. They won't be retroactively reorganized.

**Recommendation**:
- Add a tag or metadata field to distinguish new vs old traces
- Filter Langfuse views by timestamp or tag
- Archive old traces once new structure is validated

## Summary

This fix transforms Langfuse observability from a cluttered mess of disconnected traces into a clean, hierarchical structure that mirrors the actual pipeline execution. You should now be able to:

1. **Find documents easily**: 1 trace per document (not dozens)
2. **See complete context**: All LLM calls nested under their pipeline stage
3. **Debug efficiently**: Full trace tree shows execution flow
4. **Compare runs**: Consistent structure across batch and single-file

The trace hierarchy now correctly reflects the code structure:
- Batch contains documents
- Documents contain pipeline stages
- Pipeline stages contain LLM operations
- All properly nested and linked

