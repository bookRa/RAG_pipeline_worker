# Batch Observability Quick Start

## What Changed?

The batch processing pipeline has **clean, minimal logging** instead of noisy JSON dumps, with full **Langfuse tracing** support for expert observability.

## Before vs After

### Before (Noisy)
```
2025-11-25 12:34:56 - INFO - stage=parsing details=
{
  "document_id": "12804c0e-53a4-4aa8-85ec-daaefd18192e",
  "filename": "test.pdf",
  "page_count": 10,
  "pixmap_metrics": {
    "generated": 10,
    "attached": 10,
    ...
  }
}
```

### After (Clean)
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

## Key Features

✅ **Clean, minimal progress logging** - See exactly what's happening  
✅ **Millisecond timestamps** - Track performance precisely  
✅ **Multi-process/thread tracking** - See parallelism in action  
✅ **Langfuse integration** - Expert tracing with batch_id correlation  
✅ **Per-page progress** - Track each page through parsing/cleaning  

## Enable Langfuse (Optional)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Add to `.env`:
```bash
LANGFUSE__ENABLED=true
LANGFUSE__PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE__SECRET_KEY=sk-lf-your-secret-key
LANGFUSE__HOST=https://cloud.langfuse.com
```

### 3. Restart Application
```bash
uvicorn src.app.main:app --reload
```

### 4. View Traces
- Go to your Langfuse dashboard
- Filter by tag: `batch`
- Search by `batch_id` to see all documents in a batch
- Drill down to see LLM calls, timing, costs

## What You'll See in Logs

### Batch Started
```
12:34:56.000 | [BATCH_STARTED] batch=8fbc27f6 total_documents=3
```

### Per-Document Progress
```
12:34:56.100 | [INGESTION_STARTED] batch=8fbc27f6 job=12804c0e doc=test1.pdf
12:34:56.500 | [INGESTION] batch=8fbc27f6 job=12804c0e doc=test1.pdf page_count=10
```

### Per-Page Progress (Parallel)
```
12:34:57.001 | [PIXMAP_PAGE_COMPLETE] batch=8fbc27f6 doc=test1.pdf page=1/10 thread=Worker-1
12:34:57.002 | [PIXMAP_PAGE_COMPLETE] batch=8fbc27f6 doc=test1.pdf page=2/10 thread=Worker-2
12:34:57.003 | [PIXMAP_PAGE_COMPLETE] batch=8fbc27f6 doc=test1.pdf page=3/10 thread=Worker-3
```

### Stage Completion
```
12:35:00.234 | [PARSING] batch=8fbc27f6 job=12804c0e doc=test1.pdf 10 pages
12:35:05.678 | [CLEANING] batch=8fbc27f6 job=12804c0e doc=test1.pdf 10 pages 1234 tokens
12:35:07.890 | [CHUNKING] batch=8fbc27f6 job=12804c0e doc=test1.pdf 45 chunks
```

### Batch Completed
```
12:35:20.000 | [BATCH_COMPLETED] batch=8fbc27f6 completed=3 failed=0 total=3
```

## Testing

Run batch observability tests:
```bash
pytest tests/test_batch_observability.py -v
```

All tests should pass! ✅

## Troubleshooting

### Langfuse not working?
- Check environment variables are set correctly
- Verify you installed `langfuse` and `llama-index-callbacks-langfuse`
- Check logs for "✓ Langfuse tracing enabled" message on startup

### Still seeing verbose JSON logs?
- The old logger is used for single-document processing (intentional)
- Batch processing automatically uses the clean logger
- Upload multiple documents via `/batch/upload` to see clean logs

## Learn More

- [Full Implementation Summary](./Batch_Observability_Implementation_Summary.md)
- [Langfuse Documentation](https://langfuse.com/docs)
- [Batch Processing Plan](./Batch%20Processing%20Implementation.plan.md)


