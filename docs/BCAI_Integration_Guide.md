# Boeing Conversational AI (BCAI) Integration Guide

This guide explains how to configure and use the BCAI adapter in the RAG pipeline worker.

## Overview

The BCAI adapter provides seamless integration with Boeing's Conversational AI API, which is OpenAI-compatible but uses basic authentication. The adapter supports:

✅ **Text Completion and Chat**  
✅ **Multi-Modal (Vision) Support** - Images via base64  
✅ **Structured Outputs** - JSON schema validation  
✅ **Embeddings** - Multiple embedding models  
✅ **Streaming** - Planned (currently returns single responses)  

---

## Quick Start

### 1. Configuration

Update your `.env` file:

```bash
# BCAI LLM Configuration
LLM__PROVIDER=bcai
LLM__MODEL=gpt-4o-mini
LLM__API_BASE=https://bcai-test.web.boeing.com
LLM__API_KEY=your-bcai-pat-token
LLM__TEMPERATURE=0.1
LLM__CONVERSATION_MODE=non-rag
LLM__CONVERSATION_SOURCE=rag-pipeline-worker

# BCAI Embeddings (uses same credentials as LLM by default)
EMBEDDINGS__PROVIDER=bcai
EMBEDDINGS__MODEL=text-embedding-3-small
EMBEDDINGS__DIMENSIONS=1536  # Optional: override dimensions for text-embedding-3 models
```

### 2. Available Models

**LLM Models:**
- `gpt-4o-mini`
- `gpt-4.1-mini`
- Other models available via BCAI Security API

**Embedding Models:**
- `text-embedding-3-small` (1536 dims, configurable)
- `text-embedding-3-large` (3072 dims, configurable)
- `text-embedding-ada-002` (1536 dims)
- `all-MiniLM-L6-v2-us-sovereign` (384 dims)
- `nomic-us-sovereign` (768 dims)

### 3. Run the Pipeline

```bash
# Start the API server
python -m uvicorn src.app.api.main:app --reload

# Or run tests
pytest tests/test_bcai_adapter.py -v
```

---

## Configuration Details

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM__PROVIDER` | Yes | `openai` | Set to `bcai` |
| `LLM__MODEL` | Yes | `gpt-4o-mini` | BCAI model name |
| `LLM__API_BASE` | Yes | - | BCAI base URL (e.g., `https://bcai-test.web.boeing.com`) |
| `LLM__API_KEY` | Yes | - | BCAI PAT token |
| `LLM__TEMPERATURE` | No | `0.1` | Sampling temperature (0-2) |
| `LLM__MAX_OUTPUT_TOKENS` | No | `256` | Max tokens to generate |
| `LLM__CONVERSATION_MODE` | No | `non-rag` | BCAI conversation mode (`non-rag` or RAG name) |
| `LLM__CONVERSATION_SOURCE` | No | `rag-pipeline-worker` | System identifier for BCAI tracking |
| `EMBEDDINGS__PROVIDER` | No | `openai` | Set to `bcai` for BCAI embeddings |
| `EMBEDDINGS__MODEL` | No | `text-embedding-3-small` | BCAI embedding model |
| `EMBEDDINGS__DIMENSIONS` | No | - | Override dimensions (text-embedding-3 only) |

### Authentication

BCAI uses **Basic Authentication** instead of Bearer tokens:

```
Authorization: basic <UDAL_PAT>
```

The adapter automatically formats the authentication header correctly.

---

## Features

### Text Completion

The BCAI adapter supports standard text completion:

```python
from src.app.adapters.llama_index.bcai_llm import BCAILLM

llm = BCAILLM(
    api_base="https://bcai-test.web.boeing.com",
    api_key="your-pat-token",
    model="gpt-4o-mini",
)

response = llm.complete("What is RAG?")
print(response.text)
```

### Chat with Conversation History

```python
from llama_index.core.base.llms.base import ChatMessage
from llama_index.core.base.llms.types import MessageRole

messages = [
    ChatMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
    ChatMessage(role=MessageRole.USER, content="Explain document parsing."),
]

response = llm.chat(messages)
print(response.message.content)
```

### Multi-Modal (Vision)

BCAI supports image inputs via base64 encoding:

```python
from pathlib import Path
import base64

# Load and encode image
image_path = Path("diagram.png")
image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
image_url = f"data:image/png;base64,{image_data}"

# Create multi-modal message
messages = [
    ChatMessage(
        role=MessageRole.USER,
        content=[
            {"type": "text", "text": "Describe this diagram."},
            {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}}
        ]
    )
]

response = llm.chat(messages)
```

### Structured Outputs

BCAI supports JSON schema validation:

```python
schema = {
    "type": "object",
    "properties": {
        "document_type": {"type": "string"},
        "key_entities": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"}
    },
    "required": ["document_type", "key_entities", "summary"],
    "additionalProperties": False
}

response = llm.chat(messages, structured_output_schema=schema)
# Response will be valid JSON matching the schema
```

### Embeddings

```python
from src.app.adapters.llama_index.bcai_embedding import BCAIEmbedding

embedding = BCAIEmbedding(
    api_base="https://bcai-test.web.boeing.com",
    api_key="your-pat-token",
    model="text-embedding-3-small",
    dimensions=1536,  # Optional override
)

# Single text
vector = embedding._get_text_embedding("Document chunk text")

# Batch
texts = ["Chunk 1", "Chunk 2", "Chunk 3"]
vectors = embedding._get_text_embeddings(texts)
```

---

## Architecture Integration

### Hexagonal Architecture Compliance

The BCAI adapter follows the hexagonal architecture principles:

```
Domain Layer (Core)
  ↓
Ports (src/app/application/interfaces.py)
  ↓ ParsingLLM, CleaningLLM, EmbeddingGenerator
Adapters (src/app/adapters/llama_index/)
  ↓ bcai_llm.py, bcai_embedding.py
External Systems
  ↓ BCAI API
```

- **Domain models** remain framework-agnostic
- **Services** depend only on port interfaces
- **BCAI adapter** implements LlamaIndex interfaces
- **No domain logic** in the adapter

### Bootstrap Configuration

The `bootstrap.py` module handles BCAI initialization:

```python
from src.app.config import Settings
from src.app.adapters.llama_index.bootstrap import configure_llama_index

settings = Settings(llm__provider="bcai")
configure_llama_index(settings)

# LLM and embeddings are now configured globally
```

### Container Wiring

The `AppContainer` automatically wires BCAI when configured:

```python
from src.app.container import get_app_container

container = get_app_container()
# If BCAI is configured, all services use BCAI automatically
```

---

## Pipeline Integration

### Parsing Service

The parsing service uses BCAI for structured document parsing:

1. **Page Extraction**: PDF → Text + Images (300 DPI)
2. **Structured Parsing**: BCAI analyzes text and images
3. **Schema Validation**: Output matches `ParsedPage` schema
4. **Metadata Storage**: Results stored in document metadata

### Cleaning Service

Uses BCAI to normalize parsed content:

1. **Load Parsed Pages**: From document metadata
2. **LLM Cleaning**: BCAI normalizes structure
3. **Vision Context**: Optional pixmap references
4. **Schema Validation**: Output matches `CleanedPage` schema

### Enrichment Service

BCAI generates summaries at multiple levels:

1. **Chunk Summaries**: 2-sentence summaries with context
2. **Page Summaries**: Page-level abstracts
3. **Document Summaries**: 3-4 sentence overviews

### Vectorization Service

BCAI embeddings power semantic search:

1. **Batch Processing**: Efficient batch embeddings
2. **Dimension Control**: Override dimensions if needed
3. **Contextual Text**: Embeds context-enriched chunks
4. **Metadata Preservation**: Links vectors to source chunks

---

## BCAI-Specific Features

### Conversation Modes

BCAI supports different conversation modes:

- `non-rag`: Standard LLM interaction (default)
- `<rag-name>`: RAG-enhanced conversation with specific data sources

Set via `LLM__CONVERSATION_MODE` environment variable.

### Conversation Tracking

BCAI can track conversations for analytics:

- `conversation_source`: Identifies your application
- `conversation_guid`: Unique conversation ID
- `skip_db_save`: Set to `true` to avoid persistence (default)

### Cost Tracking

BCAI responses include token usage:

```json
{
  "usage": {
    "prompt_tokens": 111,
    "completion_tokens": 97,
    "total_tokens": 208
  }
}
```

Use Langfuse integration to track costs across pipeline runs.

---

## Testing

### Unit Tests

Run BCAI adapter tests:

```bash
pytest tests/test_bcai_adapter.py -v
```

### Integration Tests

Test with actual BCAI API (requires credentials):

```bash
# Set BCAI credentials
export BCAI_API_KEY="your-pat-token"
export BCAI_API_BASE="https://bcai-test.web.boeing.com"

# Run contract tests (if enabled)
RUN_CONTRACT_TESTS=1 pytest tests_contracts/test_bcai_contracts.py
```

### End-to-End Tests

Test full pipeline with BCAI:

```bash
# Configure BCAI in .env
LLM__PROVIDER=bcai

# Run end-to-end test
pytest tests/test_end_to_end.py -v -k "test_pipeline_with_pdf"
```

---

## Troubleshooting

### Authentication Errors

**Problem**: `401 Unauthorized`

**Solution**: Verify your BCAI PAT token is valid and properly formatted.

```bash
# Test authentication
curl -X POST \
  https://bcai-test.web.boeing.com/bcai-public-api/conversation \
  -H "Authorization: basic YOUR_PAT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "test"}]}'
```

### Connection Errors

**Problem**: `Connection timeout` or `Connection refused`

**Solution**: 
1. Verify you're on Boeing network or VPN
2. Check `LLM__API_BASE` URL is correct
3. Confirm firewall allows outbound HTTPS

### Model Errors

**Problem**: `Invalid model name`

**Solution**: Check available models via BCAI Security API:

```bash
curl https://bcai-test.web.boeing.com/bcai-public-security-api/models \
  -H "Authorization: basic YOUR_PAT_TOKEN"
```

### Response Format Errors

**Problem**: `Failed to extract text from response`

**Solution**: BCAI response format may have changed. Check adapter's `_extract_text_from_response` method.

---

## Migration from OpenAI

Minimal changes required:

### 1. Update Environment Variables

```diff
- LLM__PROVIDER=openai
+ LLM__PROVIDER=bcai

- LLM__API_KEY=sk-...
+ LLM__API_KEY=your-bcai-pat

- OPENAI_API_KEY=sk-...
+ LLM__API_BASE=https://bcai-test.web.boeing.com
```

### 2. Model Names

Update model names if different:

```diff
- LLM__MODEL=gpt-4o-mini
+ LLM__MODEL=gpt-4o-mini  # Same name supported
```

### 3. Test

```bash
# Restart application
uvicorn src.app.api.main:app --reload

# Verify BCAI is active (check logs)
# Should see: "LlamaIndex LLM configured: BCAI"
```

---

## Performance Considerations

### Latency

BCAI latency comparable to OpenAI:
- Simple completion: ~1-3s
- With vision: ~3-5s
- Structured outputs: ~2-4s

### Rate Limits

Check BCAI documentation for current rate limits. The adapter includes:
- Automatic retries with exponential backoff
- Configurable timeout (`LLM__TIMEOUT_SECONDS`)
- Batch size control for embeddings

### Caching

Consider implementing response caching for repeated queries:
- Use `conversation_guid` for session tracking
- Cache embeddings for frequently accessed documents
- Monitor costs via Langfuse

---

## References

- [BCAI API Documentation](docs/BCAI_doc.md)
- [Architecture Guide](docs/ARCHITECTURE.md)
- [LLM Integration Patterns](docs/LLM_Integration_Patterns.md)
- [Testing Guide](docs/TESTING.md)

---

## Support

For BCAI-specific issues:
- Check BCAI Swagger UI for API details
- Consult BCAI Security API for model availability
- Contact BCAI support team for authentication or access issues

For integration issues:
- Review adapter code: `src/app/adapters/llama_index/bcai_*.py`
- Check bootstrap configuration: `src/app/adapters/llama_index/bootstrap.py`
- Run tests: `pytest tests/test_bcai_adapter.py -v`

