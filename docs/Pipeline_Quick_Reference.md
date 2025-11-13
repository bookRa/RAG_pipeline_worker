# RAG Pipeline: Quick Reference Guide

A cheat sheet for understanding data flow, storage locations, and key concepts in the RAG pipeline.

---

## Pipeline Stages: Data In → Data Out

### 1. Ingestion
```
IN:  Raw file bytes + basic Document metadata
OUT: Document with status="ingested"
     + document.metadata.raw_file_path (where bytes are stored)
     + document.metadata.raw_file_checksum (SHA-256)
     + document.metadata.ingested_at (timestamp)
```

### 2. Parsing
```
IN:  Ingested document + file bytes
OUT: Document with pages[], status="parsed"
     + page.text (raw text from pdfplumber)
     + document.metadata.parsed_pages (structured components from vision LLM)
     + document.metadata.pixmap_assets (PNG images of pages)
```

### 3. Cleaning
```
IN:  Parsed document with pages + parsed_pages metadata
OUT: Document with page.cleaned_text, status="cleaned"
     + page.cleaned_text (normalized text)
     + document.metadata.cleaning_metadata_by_page (cleaning reports + LLM segments)
     + llm_segments.segments[] (with needs_review flags)
```

### 4. Chunking
```
IN:  Cleaned document with pages
OUT: Document with page.chunks[], status="chunked"
     + chunk.text (raw chunk slice)
     + chunk.cleaned_text (cleaned chunk slice)
     + chunk.metadata.extra.cleaning (attached from stage 3)
```

### 5. Enrichment
```
IN:  Chunked document
OUT: Document with chunk summaries + document summary, status="enriched"
     + chunk.metadata.summary (per-chunk summary)
     + document.summary (concatenation of chunk summaries, truncated to 280 chars)
```

### 6. Vectorization
```
IN:  Enriched document
OUT: Document with vectors, status="vectorized"
     + chunk.metadata.extra.vector (embedding vector as list of floats)
     + document.metadata.vector_samples (sample vectors for debugging)
```

---

## Storage Locations

| Path | Contains | When Created |
|------|----------|--------------|
| `artifacts/ingestion/<doc_id>/<timestamp>_<filename>` | Raw file bytes | Ingestion stage |
| `artifacts/pixmaps/<doc_id>/page_N.png` | Page images (300 DPI) | Parsing stage |
| `artifacts/documents/<doc_id>.json` | **Final processed document** | After pipeline completion |
| `artifacts/runs/<run_id>/run.json` | Run metadata (status, timestamps, stage order) | Run start |
| `artifacts/runs/<run_id>/document.json` | Document snapshot (same as canonical) | Run completion |
| `artifacts/runs/<run_id>/stages/parsing.json` | Parsing stage output details | After parsing |
| `artifacts/runs/<run_id>/stages/cleaning.json` | Cleaning stage output details | After cleaning |
| `artifacts/runs/<run_id>/stages/vectorization.json` | Sample vectors only | After vectorization |

**Key Insight**: `artifacts/documents/<doc_id>.json` and `artifacts/runs/<run_id>/document.json` contain the **same document data**. The runs directory adds execution context.

---

## LLM Integration Points

### Parsing (Vision LLM)
- **Adapter**: `ImageAwareParsingAdapter`
- **Prompts**: `docs/prompts/parsing/system.md` + `user.md`
- **Input**: Page image (PNG) + optional raw text
- **Output**: `ParsedPage` (components array with text, images, tables)
- **Stored in**: `document.metadata.parsed_pages[page_num]`

### Cleaning (Text LLM)
- **Adapter**: `CleaningAdapter`
- **Prompts**: `docs/prompts/cleaning/system.md` + `user.md`
- **Input**: `ParsedPage.components` array (from parsing)
- **Output**: `CleanedPage` (segments with needs_review flags)
- **Stored in**: `document.metadata.cleaning_metadata_by_page[page_num].llm_segments`

### Enrichment (Text LLM, optional)
- **Adapter**: `LLMSummaryAdapter` (not yet implemented)
- **Prompts**: `docs/prompts/summarization/system.md`
- **Input**: Chunk text (cleaned or raw)
- **Output**: 2-sentence summary string
- **Stored in**: `chunk.metadata.summary`
- **Current fallback**: Simple truncation (`text[:120]`)

---

## Key Data Structures

### Document
```json
{
  "id": "uuid",
  "filename": "doc.pdf",
  "status": "vectorized",
  "summary": "Document-level summary (280 chars max)",
  "pages": [...],
  "metadata": {
    "raw_file_path": "...",
    "parsed_pages": {...},
    "cleaning_metadata_by_page": {...},
    "vector_dimension": 1536
  }
}
```

### Page
```json
{
  "id": "uuid",
  "page_number": 1,
  "text": "Raw text from pdfplumber",
  "cleaned_text": "Normalized text from cleaning stage",
  "chunks": [...]
}
```

### Chunk
```json
{
  "id": "uuid",
  "text": "Raw chunk slice",
  "cleaned_text": "Cleaned chunk slice",
  "start_offset": 0,
  "end_offset": 507,
  "metadata": {
    "chunk_id": "uuid",
    "title": "doc.pdf-p1-c0",
    "summary": "2-sentence summary from enrichment",
    "extra": {
      "cleaning": {
        "llm_segments": {...}
      },
      "vector": [0.1, 0.2, ...]
    }
  }
}
```

### ParsedPage (in metadata)
```json
{
  "document_id": "uuid",
  "page_number": 1,
  "raw_text": "Full markdown representation",
  "components": [
    {
      "type": "text",
      "id": "1",
      "order": 0,
      "text": "Component text",
      "text_type": "heading"
    },
    {
      "type": "image",
      "id": "2",
      "order": 1,
      "description": "Visual description",
      "recognized_text": "OCR text from image"
    },
    {
      "type": "table",
      "id": "3",
      "order": 2,
      "rows": [{...}],
      "caption": "Table title"
    }
  ]
}
```

### CleanedPage (in metadata)
```json
{
  "document_id": "uuid",
  "page_number": 1,
  "segments": [
    {
      "segment_id": "5",
      "text": "Cleaned segment text",
      "needs_review": true,
      "rationale": "Contact information should be verified"
    }
  ]
}
```

---

## Common Questions

### Q: Why do I see only one chunk per page?
**A**: The entire page text fits within the chunk size (default 200 tokens). Either:
- The page is short (< 200 tokens)
- Or you need to reduce `chunk_size` for finer granularity

### Q: Where are the vectors?
**A**: In two places:
1. Full vectors: `chunk.metadata.extra.vector` (in document.json)
2. Samples: `artifacts/runs/<run_id>/stages/vectorization.json` (first 3 chunks only)

### Q: What's the difference between page.text and page.cleaned_text?
**A**:
- `page.text`: Raw extraction from pdfplumber (may have extra whitespace, formatting issues)
- `page.cleaned_text`: Normalized by cleaning LLM (better grammar, spacing)

### Q: Where are the LLM segment breakdowns?
**A**: In `document.metadata.cleaning_metadata_by_page[page_num].llm_segments.segments[]`

Also copied to: `chunk.metadata.extra.cleaning.llm_segments.segments[]` during chunking

### Q: How do I find segments that need human review?
**A**: Filter segments where `needs_review == true`:
```python
for page_num, meta in document.metadata["cleaning_metadata_by_page"].items():
    segments = meta["llm_segments"]["segments"]
    flagged = [s for s in segments if s.get("needs_review")]
    for seg in flagged:
        print(f"Page {page_num}, Segment {seg['segment_id']}: {seg['rationale']}")
```

### Q: Why is the document summary inaccurate/partial?
**A**: It's a simple concatenation of chunk summaries, truncated to 280 chars. If the first chunk is long, you only see content from page 1. This is a known issue (see TODO #1).

### Q: How do I change what gets flagged for review?
**A**: Edit `docs/prompts/cleaning/system.md` to add/remove criteria for flagging segments.

### Q: Can I use a different chunk size?
**A**: Yes, either:
- Set in config: `ChunkingService(chunk_size=100, chunk_overlap=20)`
- Or pass at runtime: `chunking_service.chunk(document, size=100, overlap=20)`

---

## Prompt Tuning Quick Guide

### To improve parsing quality:
1. Edit `docs/prompts/parsing/system.md` (behavior directives)
2. Edit `docs/prompts/parsing/user.md` (output schema and examples)
3. Re-run pipeline on test document
4. Compare `document.metadata.parsed_pages` before/after

### To improve cleaning quality:
1. Edit `docs/prompts/cleaning/system.md` (cleaning rules and review criteria)
2. Edit `docs/prompts/cleaning/user.md` (input format explanation)
3. Re-run pipeline on test document
4. Compare `page.cleaned_text` and `llm_segments` before/after

### To improve summaries:
1. Edit `docs/prompts/summarization/system.md` (summarization style)
2. Implement `LLMSummaryAdapter` (currently not wired)
3. Wire adapter in `container.py`
4. Re-run pipeline on test document
5. Compare `chunk.metadata.summary` before/after

---

## Observability Checklist

### Current State
- ✅ Basic logging via `LoggingObservabilityRecorder`
- ✅ Stage timing captured in `PipelineStage` objects
- ❌ No LLM call tracing (prompts, responses, tokens)
- ❌ No quality metrics (faithfulness, relevance)
- ❌ No cost tracking
- ❌ No query-time observability

### After Langfuse Integration
- ✅ Full LLM call tracing (automatic via callback handler)
- ✅ Hierarchical spans (pipeline → stage → LLM call)
- ✅ Token and cost tracking
- ✅ Prompt versioning
- ✅ Links between document processing and LLM operations

### After Ragas Integration
- ✅ Faithfulness scores (no hallucination)
- ✅ Answer relevancy scores
- ✅ Context precision (retrieved chunks are relevant)
- ✅ Context recall (all relevant chunks retrieved)
- ✅ Quality regression tests in CI
- ✅ Continuous quality monitoring

---

## Debug Workflow

### Problem: Document summary is wrong
1. Check `document.summary` in `artifacts/documents/<doc_id>.json`
2. Check all `chunk.metadata.summary` values
3. Check if enrichment is using LLM or truncation (`EnrichmentService._summarize_chunk`)
4. Check `docs/prompts/summarization/system.md`
5. Check document-level summary logic in `EnrichmentService.enrich()` (line 54-56)

### Problem: Cleaning produced bad text
1. Check `page.cleaned_text` vs. `page.text` in document.json
2. Check `document.metadata.cleaning_metadata_by_page[N].llm_segments.segments`
3. Look for segments with `needs_review=true` and their rationales
4. Review `docs/prompts/cleaning/system.md` and `user.md`
5. Check if cleaning LLM is enabled (should be `CleaningAdapter` in container)

### Problem: Parsing missed content
1. Check `document.metadata.parsed_pages[N].components` array
2. Look for missing components (text, images, tables)
3. Check `document.metadata.parsed_pages[N].raw_text` (markdown representation)
4. Review `docs/prompts/parsing/system.md` (especially image extraction directives)
5. Check pixmap quality in `artifacts/pixmaps/<doc_id>/page_N.png`
6. Check if vision LLM is enabled (`ImageAwareParsingAdapter` in container)

### Problem: Chunks are too large/small
1. Check current chunk size: `ChunkingService.chunk_size` (default 200)
2. Count tokens in chunks: `len(chunk.text.split())`
3. Adjust size in container or pass as parameter
4. Consider semantic chunking if fixed-size doesn't work well

### Problem: No vectors in document
1. Check `document.status` (should be "vectorized")
2. Check `chunk.metadata.extra.vector` (should be list of floats)
3. Check `document.metadata.vector_dimension` (should match embedder)
4. Check if vectorization service is wired in container
5. Check if embedder is configured (currently uses deterministic placeholder)

---

## System Prompt Locations

| Stage | System Prompt | User Prompt |
|-------|---------------|-------------|
| Parsing | `docs/prompts/parsing/system.md` | `docs/prompts/parsing/user.md` |
| Cleaning | `docs/prompts/cleaning/system.md` | `docs/prompts/cleaning/user.md` |
| Enrichment | `docs/prompts/summarization/system.md` | N/A (just chunk text) |

**Note**: Prompts are loaded at adapter initialization from files. Changes require restarting the service.

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `src/app/services/pipeline_runner.py` | Orchestrates all stages, creates PipelineResult |
| `src/app/services/parsing_service.py` | Page extraction + vision LLM parsing |
| `src/app/services/cleaning_service.py` | Text normalization + segment flagging |
| `src/app/services/chunking_service.py` | Fixed-size chunk splitting |
| `src/app/services/enrichment_service.py` | Chunk/document summarization |
| `src/app/services/vector_service.py` | Embedding generation |
| `src/app/adapters/llama_index/parsing_adapter.py` | Vision LLM integration |
| `src/app/adapters/llama_index/cleaning_adapter.py` | Cleaning LLM integration |
| `src/app/container.py` | Dependency injection, wiring |
| `src/app/domain/models.py` | Document, Page, Chunk, Metadata schemas |
| `src/app/parsing/schemas.py` | ParsedPage, CleanedPage schemas |

---

## Useful Snippets

### Load and inspect a document
```python
import json
from pathlib import Path

# Load canonical document
doc_path = Path("artifacts/documents/<doc_id>.json")
doc = json.loads(doc_path.read_text())

print(f"Status: {doc['status']}")
print(f"Pages: {len(doc['pages'])}")
print(f"Summary: {doc['summary']}")

# Check chunks
for page in doc["pages"]:
    print(f"Page {page['page_number']}: {len(page['chunks'])} chunk(s)")
```

### Find flagged segments
```python
doc = json.loads(Path("artifacts/documents/<doc_id>.json").read_text())

for page_num, meta in doc["metadata"]["cleaning_metadata_by_page"].items():
    segments = meta["llm_segments"]["segments"]
    for seg in segments:
        if seg.get("needs_review"):
            print(f"Page {page_num}, Segment {seg['segment_id']}:")
            print(f"  Text: {seg['text'][:100]}...")
            print(f"  Rationale: {seg['rationale']}")
```

### Compare raw vs. cleaned text
```python
doc = json.loads(Path("artifacts/documents/<doc_id>.json").read_text())

for page in doc["pages"]:
    print(f"Page {page['page_number']}:")
    print(f"  Raw: {len(page['text'])} chars")
    print(f"  Cleaned: {len(page.get('cleaned_text', ''))} chars")
    print(f"  Diff: {len(page.get('cleaned_text', '')) - len(page['text'])} chars")
```

### Check LLM segments
```python
doc = json.loads(Path("artifacts/documents/<doc_id>.json").read_text())

parsed_pages = doc["metadata"]["parsed_pages"]
for page_num, parsed_page in parsed_pages.items():
    print(f"Page {page_num}: {len(parsed_page['components'])} components")
    for comp in parsed_page["components"]:
        print(f"  [{comp['order']}] {comp['type']}: {comp.get('text', comp.get('description', ''))[:50]}...")
```

---

## Next Steps

1. Read the full report: `Pipeline_Data_Flow_and_Observability_Report.md`
2. Review action items: `Observability_Integration_TODO.md`
3. Set up Langfuse tracing (highest ROI)
4. Fix document summarization (quick win)
5. Build HITL review workflow (high value)

---

**Questions?** See the detailed report or ask the team!

