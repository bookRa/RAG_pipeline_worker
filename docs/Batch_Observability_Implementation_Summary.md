# Batch Observability Implementation Summary

## Overview

This document describes the implementation of clean, minimal batch observability logging with Langfuse integration for the RAG pipeline. The new system provides:

1. **Clean, minimal progress logging** during batch operations (no verbose JSON dumps)
2. **Granular timestamps** for each step (millisecond precision)
3. **Multi-process/thread tracking** information
4. **Langfuse integration** with batch_id and document_job_id for expert tracing

## Key Features

### 1. Clean Progress Logging

Instead of verbose JSON logs, batch processing now emits concise, human-readable progress messages:

```
12:34:56.789 | [PIXMAP_PAGE_COMPLETE] batch=8fbc27f6 job=12804c0e doc=test.pdf page=1/10
12:34:57.123 | [PIXMAP_PAGE_COMPLETE] batch=8fbc27f6 job=12804c0e doc=test.pdf page=2/10
12:34:57.456 | [PIXMAP_GENERATION] batch=8fbc27f6 job=12804c0e doc=test.pdf ✓ 10 pages
12:35:00.234 | [PARSING] batch=8fbc27f6 job=12804c0e doc=test.pdf 10 pages
12:35:05.678 | [CLEANING] batch=8fbc27f6 job=12804c0e doc=test.pdf 10 pages
12:35:07.890 | [CHUNKING] batch=8fbc27f6 job=12804c0e doc=test.pdf 45 chunks
12:35:10.123 | [ENRICHMENT] batch=8fbc27f6 job=12804c0e doc=test.pdf ✓ summary
12:35:15.456 | [VECTORIZATION] batch=8fbc27f6 job=12804c0e doc=test.pdf 45 vectors
12:35:15.789 | [PIPELINE_COMPLETE] batch=8fbc27f6 job=12804c0e doc=test.pdf ⏱ 18789ms
```

### 2. Granular Timestamps

All log messages include millisecond-precision timestamps in a clean `HH:MM:SS.mmm` format, allowing precise tracking of stage durations and identifying bottlenecks.

### 3. Multi-Process/Thread Tracking

When pages are processed in parallel using multiple threads or processes, the logger automatically includes thread identifiers:

```
12:34:56.789 | [PIXMAP_PAGE_COMPLETE] batch=8fbc27f6 doc=test.pdf page=1/10 thread=Worker-1
12:34:56.790 | [PIXMAP_PAGE_COMPLETE] batch=8fbc27f6 doc=test.pdf page=2/10 thread=Worker-2
```

### 4. Langfuse Integration

All observability events are sent to Langfuse with proper tracing hierarchy:

- **Batch-level trace**: Groups all documents in a batch
- **Document-level traces**: Each document gets its own trace
- **Stage-level spans**: Each pipeline stage (ingestion, parsing, cleaning, etc.) is tracked as a span
- **Page-level events**: Individual page operations are logged as generation events

**Metadata included in Langfuse traces:**
- `batch_id`: Unique batch identifier
- `document_job_id`: Document job identifier within the batch
- `process_id`: OS process ID (useful for debugging multi-process operations)
- `thread_id`: Thread identifier
- Tags: `["batch", "batch_id"]` for easy filtering

## Architecture

### Core Components

#### 1. `BatchObservabilityRecorder` (src/app/observability/batch_logger.py)

A specialized observability recorder that provides:
- Clean, minimal logging format
- Langfuse trace and span management
- Multi-process/thread identification
- Verbose mode (disabled by default for batch operations)

**Key Methods:**
- `record_event(stage, details)` - Log a stage event
- `start_trace(name, input_data)` - Start a Langfuse trace
- `start_span(name, input_data)` - Start a span within a trace
- `end_span(name, output_data)` - End a span
- `end_trace(output_data)` - End the trace

#### 2. Langfuse Configuration (src/app/config.py)

New `LangfuseSettings` configuration:

```python
class LangfuseSettings(BaseModel):
    enabled: bool = False
    public_key: str = ""
    secret_key: str = ""
    host: str = "https://cloud.langfuse.com"
```

**Environment Variables:**
```bash
LANGFUSE__ENABLED=true
LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=https://cloud.langfuse.com
```

#### 3. Updated Pipeline Components

**BatchPipelineRunner** (src/app/services/batch_pipeline_runner.py):
- Creates batch-level logger and trace
- Creates document-specific loggers for each document
- Emits stage events with clean format
- Manages Langfuse spans for each stage

**ParallelPageProcessor** (src/app/services/parallel_page_processor.py):
- Accepts `doc_logger` parameter
- Logs per-page progress during parsing and cleaning
- Passes logger to `ParallelPixmapFactory`

**ParallelPixmapFactory** (src/app/parsing/parallel_pixmap_factory.py):
- Logs each page as pixmap is generated
- Provides per-page progress feedback

## Usage

### Enabling Langfuse

1. **Install dependencies:**

```bash
pip install langfuse llama-index-callbacks-langfuse
```

2. **Set environment variables:**

Create or update `.env`:

```bash
LANGFUSE__ENABLED=true
LANGFUSE__PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE__SECRET_KEY=sk-lf-your-secret-key
LANGFUSE__HOST=https://cloud.langfuse.com  # or your self-hosted URL
```

3. **Restart the application:**

```bash
uvicorn src.app.main:app --reload
```

### Viewing Logs

**Console Logs:**
Clean progress logs are emitted to the console with the `batch_pipeline` logger.

**Langfuse UI:**
1. Navigate to your Langfuse instance (cloud.langfuse.com or self-hosted)
2. View traces for batch processing:
   - Filter by tag: `batch`
   - Search by batch_id
3. Drill down into document traces to see:
   - Stage-level timing
   - LLM calls with prompts and responses
   - Token usage and costs
   - Page-level operations

### Example: Tracing a Batch in Langfuse

```
Trace: batch_document_processing (batch=8fbc27f6)
├─ Trace: document_pipeline (doc=test1.pdf)
│  ├─ Span: ingestion (0.5s)
│  ├─ Span: parsing (15.2s)
│  │  ├─ Generation: pixmap_page_complete (page 1)
│  │  ├─ Generation: pixmap_page_complete (page 2)
│  │  └─ LLM Call: gpt-4o-mini (page 1 parsing) - 5.3s, 1.2k tokens
│  ├─ Span: cleaning (3.1s)
│  │  ├─ Generation: cleaning_page_complete (page 1)
│  │  └─ LLM Call: gpt-4o-mini (page 1 cleaning) - 1.5s, 0.3k tokens
│  ├─ Span: chunking (0.8s)
│  ├─ Span: enrichment (4.2s)
│  └─ Span: vectorization (2.1s)
└─ Trace: document_pipeline (doc=test2.pdf)
   └─ ... (similar structure)
```

## Benefits

1. **Cleaner Console Output**: No more noisy JSON dumps during batch processing
2. **Easy Progress Tracking**: See exactly which page/document is being processed at any moment
3. **Performance Debugging**: Millisecond timestamps help identify bottlenecks
4. **Multi-Process Visibility**: Thread/process IDs show parallelism in action
5. **Expert Tracing**: Langfuse provides comprehensive trace analysis, cost tracking, and performance metrics
6. **Batch Correlation**: All documents in a batch are grouped with the batch_id for easy analysis

## Migration Notes

### For Developers

- The old `LoggingObservabilityRecorder` is still used for non-batch operations
- Batch operations automatically use `BatchObservabilityRecorder`
- No changes needed to existing single-document processing
- Langfuse is opt-in via configuration (disabled by default)

### For Operators

- Enable Langfuse by setting environment variables
- Install langfuse dependencies: `pip install -r requirements.txt`
- Console logs remain clean even without Langfuse enabled
- Verbose mode can be enabled per-logger if needed for debugging

## Future Enhancements

1. **Custom Metrics**: Add custom Langfuse scores for quality tracking
2. **Alert Integration**: Send alerts on slow stages or failures
3. **Cost Analytics**: Track per-batch costs with Langfuse cost tracking
4. **A/B Testing**: Compare different prompt versions using Langfuse experiments
5. **Dashboard Integration**: Embed Langfuse metrics in the batch dashboard

## References

- [Langfuse Documentation](https://langfuse.com/docs)
- [LlamaIndex Callbacks](https://docs.llamaindex.ai/en/stable/module_guides/observability/)
- [Batch Processing Implementation Plan](./Batch%20Processing%20Implementation.plan.md)

