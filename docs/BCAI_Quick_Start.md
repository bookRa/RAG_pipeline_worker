# BCAI Quick Start Guide

## 3-Minute Setup

### 1. Configure Environment

Edit your `.env` file:

```bash
# Switch to BCAI
LLM__PROVIDER=bcai
LLM__MODEL=gpt-4o-mini
LLM__API_BASE=https://bcai-test.web.boeing.com
LLM__API_KEY=your-bcai-pat-token

# Embeddings (optional - inherits LLM credentials)
EMBEDDINGS__PROVIDER=bcai
EMBEDDINGS__MODEL=text-embedding-3-small
```

### 2. Restart Application

```bash
python -m uvicorn src.app.api.main:app --reload
```

### 3. Verify

Check startup logs for:
```
✓ LlamaIndex LLM configured: BCAI
```

**Done!** Your pipeline now uses BCAI.

---

## Test Your Setup

```bash
# Run BCAI tests
pytest tests/test_bcai_adapter.py -v

# Run full pipeline test
pytest tests/test_end_to_end.py -k "test_pipeline_with_pdf" -v
```

---

## What's Supported

✅ Text completion and chat  
✅ Multi-modal (images via base64)  
✅ Structured outputs (JSON schema)  
✅ Multiple embedding models  
✅ Automatic retries  
✅ Token usage tracking  

---

## Available Models

### LLM Models
- `gpt-4o-mini` (default, supports vision)
- `gpt-4.1-mini`

### Embedding Models
- `text-embedding-3-small` (1536 dims)
- `text-embedding-3-large` (3072 dims)
- `text-embedding-ada-002` (1536 dims)
- `all-MiniLM-L6-v2-us-sovereign` (384 dims)
- `nomic-us-sovereign` (768 dims)

---

## Troubleshooting

### Authentication Error (401)

```bash
# Verify your PAT token works
curl -X POST https://bcai-test.web.boeing.com/bcai-public-api/conversation \
  -H "Authorization: basic YOUR_PAT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"test"}],"stream":false}'
```

### Connection Timeout

- Ensure you're on Boeing network or VPN
- Verify `LLM__API_BASE` URL is correct

### Model Not Found

```bash
# List available models
curl https://bcai-test.web.boeing.com/bcai-public-security-api/models \
  -H "Authorization: basic YOUR_PAT_TOKEN"
```

---

## Next Steps

- **Full Guide**: See `docs/BCAI_Integration_Guide.md`
- **API Docs**: See `docs/BCAI_doc.md`
- **Implementation Details**: See `docs/BCAI_Implementation_Summary.md`

---

## Reverting to OpenAI

Just change one line in `.env`:

```bash
LLM__PROVIDER=openai  # Change back from "bcai"
```

Restart the application. That's it!

