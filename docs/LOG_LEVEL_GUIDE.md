# Log Level Configuration Guide

## Quick Start: How to Change Log Level

**Edit ONE file: `.env`**

```bash
# In your .env file at the project root:
LOG_LEVEL=DEBUG   # For verbose diagnostic output
LOG_LEVEL=INFO    # For clean progress logs (default)
```

That's it. No command-line flags needed. Just restart the server:

```bash
uvicorn src.app.main:app --reload
```

---

## Configuration Reference

| LOG_LEVEL | Description | When to Use |
|-----------|-------------|-------------|
| `DEBUG` | Verbose diagnostic logs | Debugging issues, development, BCAI troubleshooting |
| `INFO` | Clean progress logs | Production, monitoring batch jobs |
| `WARNING` | Only warnings and errors | Quiet production environments |
| `ERROR` | Only errors | Minimal logging |

### File Location

The log level is configured in your `.env` file at the project root:

```
RAG_pipeline_worker/
├── .env              ← Edit LOG_LEVEL here
├── .env.example      ← Reference template
├── src/
│   └── app/
│       └── config.py ← Reads LOG_LEVEL from .env
```

### What Gets Logged at Each Level

#### DEBUG Level

Shows everything, including:
- **BCAI API calls**: Full request details, message structure
- **Image processing**: Base64 data info, estimated sizes, token counts
- **LLM parsing**: Streaming progress, component extraction details
- **All INFO logs**: Plus detailed diagnostic information

Example DEBUG output for BCAI:
```
============================================================
BCAI API CALL DEBUG INFO
============================================================
URL: https://bcai-test.web.boeing.com/bcai-public-api/conversation
Model: gpt-4o-mini
Number of messages: 2
  Message 0 (role=system): text with 4,523 chars
  Message 1 (role=user): multimodal with 1 parts
    Part 0: image_url (data URL), header=data:image/png;base64, base64_len=2,847,392, ~2083.5KB
      Base64 start: iVBORw0KGgoAAAANSUhEUgAABgAAAAYACAYAAABvr...
      Base64 end: ...AASUVORK5CYII=
----------------------------------------
TOTALS: 4,523 text chars, 1 images
ESTIMATED TOKENS: ~1,130 (text) + ~1,000 (images) = ~2,130 total
============================================================
```

#### INFO Level (Default)

Shows clean progress logs:
```
10:46:24.352 | INFO     | Logging configured: level=INFO (from LOG_LEVEL=INFO)
10:46:24.352 | INFO     | [BATCH_STARTED] batch=5df85573
10:46:24.355 | INFO     | [INGESTION_STARTED] doc=doc_short_clean.pdf
10:46:28.123 | INFO     | [PARSING] doc=doc_short_clean.pdf 2 pages
10:46:32.456 | INFO     | [CLEANING] doc=doc_short_clean.pdf 2 pages
10:46:35.789 | INFO     | [PIPELINE_COMPLETE] doc=doc_short_clean.pdf ⏱ 11437ms
```

---

## Common Scenarios

### Scenario 1: Debugging BCAI "Invalid image" Error

```bash
# 1. Edit .env
LOG_LEVEL=DEBUG

# 2. Restart server
uvicorn src.app.main:app --reload

# 3. Run pipeline and check logs for:
#    - Base64 data prefix/suffix
#    - Image mimetype
#    - Estimated size in KB
```

### Scenario 2: Production Monitoring

```bash
# In .env
LOG_LEVEL=INFO
```

Clean, minimal output for batch monitoring.

### Scenario 3: Minimal Logging

```bash
# In .env
LOG_LEVEL=WARNING
```

Only warnings and errors appear.

---

## Technical Details

### How It Works

1. **`.env` file** defines `LOG_LEVEL=INFO` (or DEBUG, etc.)
2. **`src/app/config.py`** reads this into `settings.log_level`
3. **`src/app/observability/logging_setup.py`** configures all loggers at startup
4. **`src/app/main.py`** calls `setup_logging()` before the app starts

### Loggers Configured

The following loggers respect the `LOG_LEVEL` setting:

| Logger Name | Purpose |
|-------------|---------|
| `rag_pipeline` | Main pipeline logger |
| `batch_pipeline` | Batch processing |
| `src.app.adapters.llama_index.bcai_llm` | BCAI LLM calls |
| `src.app.adapters.llama_index.parsing_adapter` | Page parsing |
| `src.app.adapters.llama_index.cleaning_adapter` | Content cleaning |
| `src.app.services` | Application services |
| `src.app.api` | API routes |

### Third-Party Libraries

These are automatically set to WARNING to reduce noise:
- `uvicorn.access`, `uvicorn.error`
- `httpx`, `httpcore`, `urllib3`, `requests`
- `openai`, `langfuse`

---

## Troubleshooting

### Logs not showing?

1. **Check .env exists** at project root
2. **Check LOG_LEVEL value** is valid (DEBUG, INFO, WARNING, ERROR)
3. **Restart the server** after changing .env

### Still using PYTHONLOGLEVEL?

**Deprecated.** Use `LOG_LEVEL` in `.env` instead. The old `PYTHONLOGLEVEL` environment variable is no longer used.

### Need per-module control?

For advanced use cases, you can still configure specific loggers programmatically:

```python
import logging
logging.getLogger("src.app.adapters.llama_index.bcai_llm").setLevel(logging.DEBUG)
```

But the `.env` `LOG_LEVEL` setting should cover most needs.

---

## Summary

| What | Where |
|------|-------|
| **Configure log level** | `.env` → `LOG_LEVEL=DEBUG` |
| **Valid values** | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| **Restart required?** | Yes, after changing `.env` |
| **Command-line flags?** | None needed |
