# Log Level Guide

This document explains the logging strategy used in the RAG pipeline and how to control log verbosity.

---

## Log Level Philosophy

The pipeline uses a structured approach to logging with two primary levels:

### INFO Level (Default)
- **Purpose**: High-level progress tracking and batch observability
- **Audience**: Developers monitoring real-time pipeline behavior
- **Content**: Clean, minimal progress updates without cognitive overload

### DEBUG Level
- **Purpose**: Detailed diagnostic information for troubleshooting
- **Audience**: Developers debugging specific issues
- **Content**: Verbose streaming logs, full parsing traces, detailed progress

### WARNING/ERROR Levels
- **Purpose**: Issues that require attention
- **Always visible regardless of log level configuration**

---

## What You'll See at Each Level

### INFO Level (Default)

Clean, minimal batch progress logs:

```
10:46:24.352 | [BATCH_STARTED] batch=5df85573
10:46:24.355 | [INGESTION_STARTED] batch=5df85573 job=f7f940e2 doc=doc_short_clean.pdf
10:46:24.502 | [INGESTION] batch=5df85573 job=1055ddc2 doc=doc_short_noisy.pdf
10:46:24.979 | [PIXMAP_PAGE_COMPLETE] batch=5df85573 job=f7f940e2 doc=doc_short_clean.pdf page=1/2
10:46:28.123 | [PARSING] batch=5df85573 job=f7f940e2 doc=doc_short_clean.pdf 2 pages
10:46:32.456 | [CLEANING] batch=5df85573 job=f7f940e2 doc=doc_short_clean.pdf 2 pages
10:46:35.789 | [CHUNKING] batch=5df85573 job=f7f940e2 doc=doc_short_clean.pdf 15 chunks
10:46:40.123 | [ENRICHMENT] batch=5df85573 job=f7f940e2 doc=doc_short_clean.pdf ✓ summary
10:46:45.456 | [VECTORIZATION] batch=5df85573 job=f7f940e2 doc=doc_short_clean.pdf 15 vectors
10:46:45.789 | [PIPELINE_COMPLETE] batch=5df85573 job=f7f940e2 doc=doc_short_clean.pdf ⏱ 21437ms
```

**Characteristics:**
- One line per significant event
- Batch ID and document job correlation
- Clean timestamp format (HH:MM:SS.mmm)
- Emojis for visual scanning
- No JSON dumps or verbose details

### DEBUG Level

Includes everything from INFO plus detailed diagnostic information:

```
2025-11-25 10:46:28,320 - INFO - ✓ First token received for doc=361a253d page=1 (2.7s)
2025-11-25 10:46:30,666 - INFO - 📝 [doc=361a253d pg=1 | 5.0s]
{
  "document_id": "361a253d",
  "page_number": 1,
  "raw_text": "3 Installation and start-up...",
  "page_summary": "This page provides installation instructions...",
  "components": [...]
}
2025-11-25 10:46:30,666 - INFO - 📊 Progress: 95 chunks, 306 chars total
2025-11-25 10:46:35,668 - INFO - 📝 [doc=361a253d pg=1 | 10.0s] ...more content...
2025-11-25 10:46:59,515 - INFO - ✅ Streaming complete for doc=361a253d page=1: 1442 chunks, 5302 chars in 33.9s
```

**Characteristics:**
- Streaming progress updates (every 5 seconds)
- Full JSON content from LLM responses
- Token counts and character counts
- Time-to-first-token (TTFT) metrics
- Detailed parsing trace with all components
- Guardrail activation logs

---

## Configuring Log Levels

### Option 1: Environment Variable (Recommended)

Set the Python logging level before starting the application:

```bash
# INFO level (default) - clean batch logs only
export PYTHONLOGLEVEL=INFO
uvicorn src.app.main:app --reload

# DEBUG level - verbose diagnostic logs
export PYTHONLOGLEVEL=DEBUG
uvicorn src.app.main:app --reload
```

### Option 2: Python Logging Configuration

In `src/app/main.py` or a logging configuration file:

```python
import logging

# INFO level (default)
logging.basicConfig(level=logging.INFO)

# DEBUG level for troubleshooting
logging.basicConfig(level=logging.DEBUG)
```

### Option 3: Per-Module Control

For fine-grained control, configure specific loggers:

```python
import logging

# Set root logger to INFO
logging.basicConfig(level=logging.INFO)

# Enable DEBUG only for parsing adapter
logging.getLogger("src.app.adapters.llama_index.parsing_adapter").setLevel(logging.DEBUG)

# Enable DEBUG only for batch processing
logging.getLogger("src.app.services.batch_pipeline_runner").setLevel(logging.DEBUG)
```

---

## When to Use Each Level

### Use INFO Level When:
- ✅ Monitoring batch processing in production
- ✅ Tracking pipeline progress across multiple documents
- ✅ Identifying slow stages or bottlenecks
- ✅ Debugging high-level workflow issues
- ✅ Demonstrating the pipeline to stakeholders

### Use DEBUG Level When:
- ✅ Debugging LLM parsing issues
- ✅ Investigating why specific content is being parsed incorrectly
- ✅ Analyzing streaming response patterns
- ✅ Troubleshooting guardrail activations
- ✅ Understanding token usage and timing
- ✅ Developing or testing new features

---

## Log Locations by Component

### Batch Observability (INFO Level)
- **File**: `src/app/observability/batch_logger.py`
- **Logs**: Clean progress events with batch_id correlation
- **Format**: `HH:MM:SS.mmm | [EVENT] batch=... doc=... details`

### LLM Parsing (DEBUG Level)
- **File**: `src/app/adapters/llama_index/parsing_adapter.py`
- **Logs**: Streaming progress, full parsing traces, component details
- **Methods**:
  - `_stream_with_guardrails()` - Streaming progress logs
  - `_log_trace()` - Detailed parsing trace with all components
  - `_parse_with_vision_structured()` - LLM call logs
  - `_parse_with_structured_api()` - Structured API logs

### Single Document Pipeline (INFO Level)
- **File**: `src/app/observability/logger.py`
- **Logs**: Standard observability events for single-document processing

---

## Best Practices

### For Development
1. **Start with INFO level** to see high-level progress
2. **Switch to DEBUG** when you encounter unexpected behavior
3. **Use per-module control** to focus on specific components
4. **Keep DEBUG logs on** when developing new features

### For Production
1. **Use INFO level** as default to reduce log volume
2. **Enable DEBUG temporarily** when investigating issues
3. **Monitor for WARNING/ERROR** logs regardless of level
4. **Consider log aggregation** (e.g., Cloudwatch, Datadog) for DEBUG logs

### For Testing
1. **Use INFO level** for integration tests (validates progress tracking)
2. **Use DEBUG level** for diagnostic tests (validates detailed behavior)
3. **Capture logs in CI** to diagnose test failures

---

## Migration Notes

### What Changed

Previously, all logs were at INFO level, causing cognitive overload during batch processing. Now:

- **Batch progress logs** remain at INFO (clean, minimal)
- **Streaming progress logs** moved to DEBUG (verbose details)
- **Parsing trace logs** moved to DEBUG (full component dumps)
- **LLM call logs** moved to DEBUG (request/response details)
- **Warning/Error logs** unchanged (always visible)

### Backward Compatibility

The default log level is INFO, so existing deployments will see:
- ✅ Clean batch progress logs (improved)
- ❌ No verbose streaming logs (moved to DEBUG)

To restore previous behavior, set `PYTHONLOGLEVEL=DEBUG`.

---

## Examples

### Example 1: Monitoring Batch Processing

**Goal**: Track progress of multiple documents without clutter

**Configuration**:
```bash
export PYTHONLOGLEVEL=INFO
uvicorn src.app.main:app --reload
```

**Result**: See clean batch progress logs only

### Example 2: Debugging Parsing Issues

**Goal**: Investigate why a specific table isn't being extracted

**Configuration**:
```bash
export PYTHONLOGLEVEL=DEBUG
uvicorn src.app.main:app --reload
```

**Result**: See full parsing trace with streaming progress and component details

### Example 3: Production Monitoring

**Goal**: Monitor production pipeline with minimal log volume

**Configuration**:
```bash
export PYTHONLOGLEVEL=INFO
# Configure log aggregation to capture WARNING/ERROR
```

**Result**: Clean progress tracking + alerts on issues

---

## Related Documentation

- **Batch Observability Quick Start**: `docs/Batch_Observability_Quick_Start.md`
- **Batch Processing Guide**: `docs/Batch_Processing_Implementation_Summary.md`
- **Langfuse Integration**: `docs/Batch_Observability_Implementation_Summary.md`

---

## Summary

The pipeline now uses a two-level logging strategy:

- **INFO (default)**: Clean, minimal progress tracking for batch operations
- **DEBUG**: Verbose diagnostic logs for troubleshooting

This reduces cognitive overload while maintaining full diagnostic capabilities when needed.

Change log level via `PYTHONLOGLEVEL` environment variable:
- `INFO` - Clean batch progress (recommended for production)
- `DEBUG` - Full diagnostic logs (recommended for development/debugging)




