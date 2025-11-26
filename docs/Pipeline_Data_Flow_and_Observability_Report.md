# RAG Pipeline: Data Flow, Stage Interplay, and Observability Integration

**Author**: AI Assistant  
**Date**: November 13, 2024  
**Purpose**: Comprehensive analysis of pipeline stages, data flow, system prompts, and recommendations for integrating Langfuse and Ragas observability frameworks.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Document Storage Structure](#document-storage-structure)
3. [Pipeline Stage-by-Stage Analysis](#pipeline-stage-by-stage-analysis)
4. [System Prompts and LLM Integration Points](#system-prompts-and-llm-integration-points)
5. [Answers to Specific Questions](#answers-to-specific-questions)
6. [Human-in-the-Loop Integration](#human-in-the-loop-integration)
7. [Observability Framework Integration](#observability-framework-integration)
8. [Recommendations and Action Items](#recommendations-and-action-items)

---

## Executive Summary

This report provides a detailed analysis of your RAG pipeline's architecture, focusing on:

- **Data Flow**: How each stage transforms the document and passes data to subsequent stages
- **Storage Model**: Understanding the dual storage pattern (documents vs. runs)
- **LLM Integration Points**: Where and how system prompts influence processing
- **Observability Gap**: Current limitations and how Langfuse/Ragas can address them
- **Actionable Next Steps**: Specific recommendations for improvement

**Key Findings**:
1. Document-level summary is **concatenated chunk summaries**, not a true LLM-generated overview
2. The `summary` field in chunk metadata **IS** the enrichment output
3. LLM segments already include `needs_review` flags for HITL workflows
4. The pipeline is well-structured for observability integration via callback handlers

---

## Document Storage Structure

### 1. Understanding the Two Storage Locations

**Q: Why do we have both `artifacts/documents/<doc_id>.json` and `artifacts/runs/<run_id>/document.json`?**

**A**: These serve different but complementary purposes:

| Location | Purpose | When Created | Contains |
|----------|---------|--------------|----------|
| `artifacts/documents/<doc_id>.json` | **Canonical document store** | After pipeline completion (by `DocumentRepository`) | Final processed document with all stages applied |
| `artifacts/runs/<run_id>/document.json` | **Run-specific snapshot** | During pipeline execution (by `PipelineRunRepository`) | Same document content, but in context of a specific run |
| `artifacts/runs/<run_id>/stages/*.json` | **Stage outputs** | After each stage completes | Detailed stage-specific data (parsing components, vectorization details) |
| `artifacts/runs/<run_id>/run.json` | **Run metadata** | At run start/completion | Status, timestamps, stage order, error messages |

**Why This Design?**

1. **Document-centric access**: API endpoints like `/documents/<doc_id>` can serve the canonical version without knowing about runs
2. **Run-centric debugging**: The run directory provides a complete audit trail of how that specific execution processed the document
3. **Stage-level inspection**: Each stage's output is preserved for debugging, evaluation, and iterative improvement
4. **Immutability**: Multiple runs can process the same document, each preserving its own execution history

**Practical Example**:
```
# Same document, processed twice
artifacts/documents/abc-123.json         # Final state after run-2
artifacts/runs/run-1/document.json       # Snapshot from first processing
artifacts/runs/run-2/document.json       # Snapshot from reprocessing with new prompts
```

### 2. Vectors Storage

**Q: Where are the vectors?**

**A**: Vectors are stored in **two places**:

1. **Per-chunk in document.json**: `chunk.metadata.extra.vector` (full vector array)
2. **Sample in run stage**: `artifacts/runs/<run_id>/stages/vectorization.json` contains sample vectors for quick inspection

The `vectorization.json` stage file is useful for debugging without loading the entire document.

---

## Pipeline Stage-by-Stage Analysis

### Stage 1: Ingestion

**Service**: `IngestionService`  
**Input**: Raw file bytes + `Document` with basic metadata  
**Output**: `Document` with status="ingested"  

**Data Transformations**:
```python
# What gets added to document.metadata
{
    "raw_file_path": "artifacts/ingestion/<doc_id>/<timestamped_filename>",
    "raw_file_checksum": "sha256_hash",
    "ingested_at": "2024-11-13T02:08:12.463884"
}
```

**Feeds into**: Parsing stage (reads from `raw_file_path`)

---

### Stage 2: Parsing

**Service**: `ParsingService`  
**Input**: Ingested document + file bytes  
**Output**: `Document` with `pages` populated, status="parsed"  

**LLM Integration Point**: `ImageAwareParsingAdapter` (LlamaIndex)

**System Prompt**: `docs/prompts/parsing/system.md` + `docs/prompts/parsing/user.md`

**Data Transformations**:

1. **Basic text extraction** (via pdfplumber): Each page gets raw text
2. **Pixmap generation**: High-res PNG images of each page (300 DPI)
3. **Vision-based structured parsing**: LLM analyzes page image and produces:
   ```json
   {
     "document_id": "...",
     "page_number": 1,
     "raw_text": "Full markdown representation",
     "components": [
       {"type": "text", "id": "1", "order": 0, "text": "...", "text_type": "heading"},
       {"type": "image", "id": "2", "order": 1, "description": "...", "recognized_text": "..."},
       {"type": "table", "id": "3", "order": 2, "rows": [...], "caption": "..."}
     ]
   }
   ```

**Stored in `document.metadata`**:
```python
{
    "parsed_pages": {
        "1": { # ParsedPage object as dict
            "document_id": "...",
            "page_number": 1,
            "raw_text": "...",
            "components": [...]
        },
        "2": {...}
    },
    "pixmap_assets": {
        "1": "artifacts/pixmaps/<doc_id>/page_1.png",
        "2": "artifacts/pixmaps/<doc_id>/page_2.png"
    },
    "pixmap_metrics": {
        "generated": 2,
        "attached": 2,
        "total_size_bytes": 1283335,
        "dpi": 300,
        "avg_structured_latency_ms": 20693.71
    }
}
```

**Key Insight**: The parser provides **TWO representations**:
- `page.text`: Simple string (from pdfplumber)
- `metadata.parsed_pages[N].components`: Structured breakdown (from LLM with vision)

**Feeds into**: Cleaning stage (uses `parsed_pages` metadata)

---

### Stage 3: Cleaning

**Service**: `CleaningService`  
**Input**: Parsed document with pages + `parsed_pages` metadata  
**Output**: `Document` with `page.cleaned_text` populated, status="cleaned"  

**LLM Integration Point**: `CleaningAdapter` (LlamaIndex)

**System Prompt**: `docs/prompts/cleaning/system.md` + `docs/prompts/cleaning/user.md`

**Data Transformations**:

1. **For each page**:
   - Takes `parsed_pages[N].components` from metadata
   - Sends components to LLM with cleaning instructions
   - LLM returns `CleanedPage` with segments:
     ```json
     {
       "document_id": "...",
       "page_number": 1,
       "segments": [
         {
           "segment_id": "1",
           "text": "Cleaned text from component 1",
           "needs_review": false,
           "rationale": null
         },
         {
           "segment_id": "5",
           "text": "Cleaned contact information",
           "needs_review": true,
           "rationale": "Contact information should be verified for accuracy."
         }
       ]
     }
     ```
   
2. **Concatenates all segment texts** to create `page.cleaned_text`

3. **Stores cleaning metadata** in `document.metadata.cleaning_metadata_by_page`:
   ```python
   {
     "cleaning_metadata_by_page": {
       1: {
         "cleaned_tokens_count": 118,
         "diff_hash": "b913e2af...",
         "cleaning_ops": ["whitespace"],
         "needs_review": false,  # True if ANY segment needs review
         "profile": "default",
         "llm_segments": {  # Full CleanedPage object
           "document_id": "...",
           "page_number": 1,
           "segments": [...]
         }
       }
     }
   }
   ```

**Important**: The `llm_segments` object contains the **segment-level breakdown with review flags**. This is how the LLM directs segmentation and flags items for human review.

**Feeds into**: Chunking stage (uses `cleaned_text` and attaches cleaning metadata to chunks)

---

### Stage 4: Chunking

**Service**: `ChunkingService`  
**Input**: Cleaned document with pages  
**Output**: `Document` with `page.chunks` populated, status="chunked"  

**No LLM Integration** (rule-based splitting)

**Data Transformations**:

1. **For each page**:
   - Splits `page.text` (raw) into overlapping chunks (default: 200 tokens, 50 overlap)
   - For each chunk slice, extracts corresponding slice from `page.cleaned_text`
   - Creates `Chunk` object with:
     ```python
     Chunk(
         id="uuid",
         document_id="...",
         page_number=1,
         text="raw chunk slice",           # From page.text
         cleaned_text="cleaned chunk slice", # From page.cleaned_text
         start_offset=0,
         end_offset=507,
         metadata=Metadata(
             chunk_id="uuid",
             title="doc.pdf-p1-c0",
             summary=None,  # Added in enrichment stage
             extra={
                 "cleaning": {
                     # Cleaning metadata from stage 3
                     "llm_segments": {...}
                 }
             }
         )
     )
     ```

2. **Attaches cleaning metadata**: The `llm_segments` from stage 3 are copied into `chunk.metadata.extra.cleaning`

**Key Insight**: If a page has only one chunk, it means the entire page text fits within the chunk size limit (200 tokens by default). For a 2-page document, you'd see:
```json
{
  "pages": [
    {"page_number": 1, "chunks": [<one chunk object>]},
    {"page_number": 2, "chunks": [<one chunk object>]}
  ]
}
```

**Feeds into**: Enrichment stage (adds summaries to chunk metadata)

---

### Stage 5: Enrichment

**Service**: `EnrichmentService`  
**Input**: Chunked document  
**Output**: `Document` with chunk summaries + document summary, status="enriched"  

**LLM Integration Point**: `SummaryGenerator` interface (optional, currently using simple truncation)

**System Prompt**: `docs/prompts/summarization/system.md` (only used if real LLM summarizer is configured)

**Data Transformations**:

1. **For each chunk**:
   - If `chunk.metadata.summary` is empty:
     - Calls `self._summarize_chunk(chunk.cleaned_text or chunk.text)`
     - Default implementation: `return text[:120].strip()` (simple truncation)
     - **If `SummaryGenerator` is injected**: Calls LLM to generate 2-sentence summary
   - Updates `chunk.metadata.summary`

2. **Builds document-level summary**:
   ```python
   # From enrichment_service.py lines 54-56
   document_summary = document.summary
   if summaries and not document_summary:
       document_summary = " ".join(summaries)[:280]
   ```
   
   **⚠️ Critical Finding**: The document summary is simply **all chunk summaries concatenated and truncated to 280 chars**. This explains why you see only the first page's content!

**Feeds into**: Vectorization stage (no changes to text, just metadata)

---

### Stage 6: Vectorization

**Service**: `VectorService`  
**Input**: Enriched document  
**Output**: `Document` with vectors in chunk metadata, status="vectorized"  

**LLM Integration Point**: `Embedder` interface (optional, currently using deterministic placeholder vectors)

**Data Transformations**:

1. **For each chunk**:
   - Generates embedding vector from `chunk.cleaned_text` (or `chunk.text` if no cleaned version)
   - Default: Deterministic vector based on text hash (for testing)
   - **Production**: Would use OpenAI embeddings, LlamaIndex embeddings, etc.
   - Stores in `chunk.metadata.extra.vector` (list of floats)

2. **Stores sample vectors** in `document.metadata.vector_samples` for debugging

**Final Output**: Fully processed document ready for retrieval

---

## System Prompts and LLM Integration Points

### 1. Parsing Prompts

**Location**: `docs/prompts/parsing/system.md` + `user.md`

**Purpose**: Instruct LLM (with vision capabilities) to extract structured components from page images

**Key Directives** (from `system.md`):
- "You must be THOROUGH and extract ALL content from the page"
- "DO NOT SKIP ANY IMAGES - You must identify and describe EVERY image"
- "The order of components MUST reflect the visual layout from top to bottom, left to right"

**Output Schema**: `ParsedPage` (enforced via structured outputs)

**How to Modify**:
1. Edit `docs/prompts/parsing/system.md` to change LLM behavior
2. For example, to improve image descriptions:
   ```markdown
   When describing images, focus on:
   1. Technical content (diagrams, charts, graphs)
   2. Spatial relationships between elements
   3. Any text or labels visible within the image
   4. Visual style and purpose (illustration, photograph, technical drawing)
   ```
3. Changes take effect immediately on next run (no code changes needed)

**Current Issue**: The prompt doesn't ask for a page-level summary, only component extraction.

---

### 2. Cleaning Prompts

**Location**: `docs/prompts/cleaning/system.md` + `user.md`

**Purpose**: Normalize parsed content and flag segments needing human review

**Key Directives** (from `system.md`):
- "You normalize parsed document content"
- "Clean grammar and spacing but never fabricate information"
- "Highlight segments that require manual review"

**Input Format** (from `user.md`):
```json
{
  "document_id": "...",
  "page_number": 1,
  "components": [
    {"type": "text", "id": "1", "text": "NONRESIDENT\nTRAINING\nCOURSE", ...},
    {"type": "image", "id": "2", "description": "...", "recognized_text": "..."},
    {"type": "table", "id": "3", "rows": [...]}
  ]
}
```

**Output Schema**: `CleanedPage` with segments array

**How LLM Directs Segmentation**:
The LLM receives each component separately and decides:
1. How to clean the text (normalize whitespace, fix grammar)
2. Whether to flag it for review (`needs_review: true/false`)
3. Why it needs review (`rationale: "Contact information should be verified"`)

**Example Output**:
```json
{
  "segments": [
    {
      "segment_id": "5",
      "text": "Notice: The Naval Education and Training Professional Development and Technology Center (NETPDTC) is no longer responsible for the content accuracy of the Nonresident Training Courses (NRTCs).",
      "needs_review": true,
      "rationale": "The sentence is long and may contain specific terminology that requires verification."
    }
  ]
}
```

**How to Modify**:
1. Edit `docs/prompts/cleaning/system.md` to change review criteria:
   ```markdown
   Flag segments for review when they contain:
   - Contact information (phone, email, address)
   - Dates or version numbers that may be outdated
   - Technical specifications or measurements
   - Legal disclaimers
   - Acronyms or abbreviations without definitions
   ```

---

### 3. Summarization Prompts

**Location**: `docs/prompts/summarization/system.md`

**Purpose**: Generate concise chunk-level summaries during enrichment

**Current Directive**: "You are a concise technical summarizer. Given one or more cleaned segments, return a two sentence summary highlighting the main decision or insight."

**Current Status**: **Not actively used** because no `SummaryGenerator` is configured in the container. The enrichment service falls back to simple truncation (`text[:120]`).

**How to Activate**:
1. Create an `LLMSummaryAdapter` that implements `SummaryGenerator`
2. Wire it in `container.py`:
   ```python
   summary_generator = LLMSummaryAdapter(
       llm=self.llm,
       prompt_settings=self.prompt_settings
   )
   self.enrichment_service = EnrichmentService(
       observability=self.observability,
       summary_generator=summary_generator
   )
   ```

---

## Answers to Specific Questions

### Q1: Document vs Run JSON Files

**A**: See [Document Storage Structure](#document-storage-structure) section above.

**Summary**:
- `artifacts/documents/<doc_id>.json` = Canonical final document
- `artifacts/runs/<run_id>/document.json` = Same content, run-specific context
- Both contain identical document data
- Runs directory adds stage outputs and run metadata

---

### Q2: Document Summary - Where Does It Come From?

**A**: The document-level `summary` field is created in **EnrichmentService** (lines 54-56):

```python
document_summary = document.summary
if summaries and not document_summary:
    document_summary = " ".join(summaries)[:280]
```

**What It Actually Does**:
1. Collects summaries from **all chunks** (which are either LLM-generated or truncated text)
2. Concatenates them with spaces: `"Summary1 Summary2 Summary3 ..."`
3. Truncates to **280 characters**

**Why It's Partial/Inaccurate**:
- If your document has 50 chunks but the first chunk's summary is 280 chars, you'll only see content from page 1
- This is **not a true document-level summary** - it's a truncated concatenation of chunk summaries

**How to Fix It**:

**Option A: Add a dedicated document summarization step**

Create a new service that generates a proper document-level summary using an LLM:

```python
class DocumentSummarizationService:
    def summarize_document(self, document: Document) -> str:
        # Collect key content from all pages
        page_summaries = []
        for page in document.pages:
            # Get first N chars from each page
            page_summaries.append(page.cleaned_text[:500])
        
        # Ask LLM to summarize the whole document
        full_context = "\n\n---\n\n".join(page_summaries)
        prompt = f"Summarize this {len(document.pages)}-page document in 2-3 sentences:\n\n{full_context}"
        return llm.complete(prompt).text
```

Add this after enrichment in `PipelineRunner.run()`.

**Option B: Use the summarization prompt with full document context**

Modify `EnrichmentService` to pass all chunk summaries to the summarization LLM:

```python
# Instead of simple truncation
if summaries and not document_summary:
    all_summaries = "\n".join(f"- {s}" for s in summaries)
    if self.summary_generator:
        document_summary = self.summary_generator.summarize(
            f"Document: {document.filename}\nChunk Summaries:\n{all_summaries}"
        )
    else:
        document_summary = " ".join(summaries)[:280]
```

Then tune `docs/prompts/summarization/system.md`:
```markdown
You are a concise technical summarizer. Given a list of chunk summaries from a multi-page document, 
synthesize them into a 2-3 sentence high-level summary that captures the document's main purpose, 
scope, and key topics. Do not just concatenate - identify the overarching themes.
```

---

### Q3: Single Chunk Per Page?

**A**: Yes, if you see `"chunks": [<one object>]` for each page, it means **the entire page was turned into a single chunk**.

**Why This Happens**:
- Default chunk size is 200 tokens with 50 token overlap (see `ChunkingService.__init__`)
- If a page's text is ≤ 200 tokens, it won't be split
- Your sample document has short cover pages (page 1 is ~120 tokens after cleaning)

**How to Verify**:
```python
# From your document.json
page = document["pages"][0]
chunks = page["chunks"]
print(f"Page {page['page_number']}: {len(chunks)} chunk(s)")

chunk = chunks[0]
print(f"Chunk text length: {len(chunk['text'])} chars")
print(f"Chunk token estimate: {len(chunk['text'].split())} tokens")
```

**Is This a Problem?**

It depends on your use case:
- ✅ **Good**: For cover pages, tables of contents, short sections
- ❌ **Bad**: For dense technical pages that should be split for better retrieval granularity

**How to Adjust**:
1. Reduce chunk size: `ChunkingService(chunk_size=100, chunk_overlap=20)`
2. Use semantic chunking: Inject a `text_splitter` that splits on section boundaries
3. Use component-based chunking: Create one chunk per component (heading, paragraph, table, image) instead of fixed-size chunks

---

### Q4: How Does the System Prompt Direct Chunk Segmentation?

**A**: The `llm_segments` object shows how the **CleaningAdapter** breaks down content.

**The Process**:

1. **Parsing stage** (LLM with vision) identifies components:
   - Component 1: Heading "NONRESIDENT TRAINING COURSE"
   - Component 2: Paragraph "September 2015"
   - Component 3: Heading "Blueprint Reading and Sketching"
   - etc.

2. **Cleaning stage** (cleaning LLM) processes each component:
   - Receives full list of components in JSON format
   - Normalizes text for each component
   - Decides if each segment needs review
   - Returns cleaned segments (one per component)

3. **Chunking stage** (no LLM):
   - Splits the raw page text into fixed-size chunks
   - Attaches the `llm_segments` metadata to each chunk

**Key Insight**: The segmentation is driven by the **parsing prompt** (which identifies components) and the **cleaning prompt** (which normalizes and flags them). The chunking stage just splits the concatenated text.

**How to Improve Segmentation**:

Modify `docs/prompts/parsing/system.md` to better identify semantic boundaries:
```markdown
When identifying text components:
- Treat each section with a heading as a separate component group
- Identify topic boundaries (changes in subject matter)
- Keep related paragraphs together (e.g., a concept and its explanation)
- Separate different types of content (instructions vs. examples vs. definitions)
```

This will produce better component boundaries, leading to more meaningful segments.

---

### Q5: How to Surface Human-in-the-Loop Review?

**A**: The infrastructure is **already in place**! The `llm_segments.segments` array contains `needs_review` and `rationale` fields.

**Current State**:
```json
{
  "llm_segments": {
    "segments": [
      {
        "segment_id": "5",
        "text": "Notice: The Naval Education and Training Professional Development and Technology Center...",
        "needs_review": true,
        "rationale": "The sentence is long and may contain specific terminology that requires verification."
      }
    ]
  }
}
```

**Where This Data Lives**:
- `document.metadata.cleaning_metadata_by_page[page_num].llm_segments.segments`
- Also copied to `chunk.metadata.extra.cleaning.llm_segments.segments` during chunking

**How to Build HITL Workflow**:

**Step 1: Use the review API to fetch flagged segments**

```python
# src/app/api/routers.py
@router.get("/documents/{document_id}/segments-for-review")
async def get_segments_for_review(document_id: str, use_case: GetDocumentUseCase = Depends(get_get_use_case)) -> dict:
    document = use_case.execute(document_id)
    cleaning_metadata = document.metadata.get("cleaning_metadata_by_page", {}) if document.metadata else {}
    flagged_segments = []

    for page in document.pages:
        page_meta = _get_page_cleaning_metadata(cleaning_metadata, page.page_number)
        segments = page_meta.get("llm_segments", {}).get("segments", [])
        for segment in segments:
            if segment.get("needs_review"):
                chunk_id = None
                for chunk in page.chunks:
                    cleaning_extra = (chunk.metadata and chunk.metadata.extra.get("cleaning")) or {}
                    llm_segments = cleaning_extra.get("llm_segments", {})
                    if any(s.get("segment_id") == segment.get("segment_id") for s in llm_segments.get("segments", [])):
                        chunk_id = chunk.id
                        break
                flagged_segments.append(
                    {
                        "document_id": document_id,
                        "page_number": page.page_number,
                        "chunk_id": chunk_id,
                        "segment_id": segment.get("segment_id"),
                        "text": segment.get("text", ""),
                        "rationale": segment.get("rationale"),
                    }
                )
    return {"flagged_segments": flagged_segments}
```

**Step 2: Review UI (`/dashboard/review`)**

`src/app/api/templates/review.html` renders a dedicated queue:

- Populates the document selector via `GET /documents`
- Calls `/documents/{document_id}/segments-for-review` and renders cards with rationale, page/chunk context, and action buttons
- Provides inline Approve and Edit actions with optimistic UI updates plus a modal for corrections
- Uses the same design system as the dashboard while keeping the pipeline view untouched

**Step 3: Approve/Edit endpoints write back to storage**

```python
# src/app/api/routers.py
@router.post("/segments/{segment_id}/approve")
async def approve_segment(segment_id: str, document_id: str = Body(...)) -> dict:
    repository = get_app_container().document_repository
    updated = repository.approve_segment(document_id, segment_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Segment not found")
    return {"status": "approved", "segment_id": segment_id}

@router.put("/segments/{segment_id}/edit")
async def edit_segment(segment_id: str, document_id: str = Body(...), corrected_text: str = Body(...)) -> dict:
    repository = get_app_container().document_repository
    updated = repository.edit_segment(document_id, segment_id, corrected_text)
    if not updated:
        raise HTTPException(status_code=404, detail="Segment not found")
    return {"status": "edited", "segment_id": segment_id, "corrected_text": corrected_text}
```

Both helpers delegate to `FileSystemDocumentRepository`, which toggles `needs_review`, appends to `review_history`, and rebuilds `page.cleaned_text` so downstream services always read the corrected content.

**Tuning the Review Criteria**:

Edit `docs/prompts/cleaning/system.md` to adjust what gets flagged:

```markdown
Flag segments for review (set needs_review=true) when they contain:

1. Contact information (phone numbers, email addresses, physical addresses)
2. Version numbers or dates that may become outdated
3. Technical specifications with measurements or tolerances
4. Legal disclaimers or compliance statements
5. Acronyms or abbreviations used without prior definition
6. Long sentences (>30 words) with complex terminology
7. Any content where OCR confidence is low (garbled text)

Provide a specific rationale explaining why review is needed.
```

---

### Q6: Adding Page-Level Summaries to Parser Output

**A**: This is a great enhancement! Currently the parser provides:
- `raw_text` (markdown representation)
- `components` (detailed breakdown)

**Recommendation**: Add a `page_summary` field to `ParsedPage` schema.

**Implementation Steps**:

**Step 1: Update the schema**

```python
# In src/app/parsing/schemas.py
class ParsedPage(BaseModel):
    document_id: str
    page_number: int
    raw_text: str
    components: list[ParsedTextComponent | ParsedImageComponent | ParsedTableComponent]
    page_summary: str | None = None  # NEW: High-level page summary
```

**Step 2: Update the parsing prompt**

```markdown
# In docs/prompts/parsing/user.md

Return JSON with keys `document_id`, `page_number`, `raw_text`, `components`, and `page_summary`.

**New Field**:
- `page_summary`: A 1-2 sentence overview of the page's main purpose and content. 
  Focus on what information the page conveys and its role in the document structure.
  
Example:
- "This cover page identifies the document as a training manual for blueprint reading, 
  published in September 2015 by the Naval Education and Training Professional Development 
  and Technology Center."
```

**Step 3: Update the adapter to include page_summary in the schema instruction**

The `ImageAwareParsingAdapter` already includes the schema in the prompt, so this will automatically be picked up.

**Step 4: Use page summaries in enrichment**

```python
# In enrichment_service.py
def enrich(self, document: Document) -> Document:
    # ... existing chunk enrichment ...
    
    # Build better document summary from page summaries
    parsed_pages = document.metadata.get("parsed_pages", {})
    page_summaries = []
    for page_num in range(1, len(document.pages) + 1):
        parsed_page = parsed_pages.get(str(page_num))
        if parsed_page and parsed_page.get("page_summary"):
            page_summaries.append(parsed_page["page_summary"])
    
    if page_summaries:
        # Join all page summaries or ask LLM to synthesize
        document_summary = " ".join(page_summaries)
        # Optionally: Pass to summarization LLM for synthesis
```

This would give you much better document-level summaries!

---

### Q7: Enrichment Outputs - Where Are They?

**A**: The enrichment outputs **ARE** present - they're the `summary` fields in chunk metadata.

**Location in JSON**:
```json
{
  "pages": [
    {
      "chunks": [
        {
          "id": "7221c9c1-...",
          "metadata": {
            "summary": "The Naval Education and Training Professional Development and Technology Center (NETPDTC) has disclaimed responsibility for the accuracy of content in Nonresident Training Courses (NRTCs). For any content-related inquiries, individuals should contact the Surface Warfare Officers School Command (SWOS).",
            "extra": { ... }
          }
        }
      ]
    }
  ]
}
```

**What Enrichment Does**:
1. Iterates through all chunks
2. For each chunk without a summary, calls `_summarize_chunk()`
3. Currently: Just truncates to 120 chars
4. If `SummaryGenerator` is configured: Calls LLM to generate 2-sentence summary
5. Updates `chunk.metadata.summary`

**Why You Might Not See Rich Enrichment**:
- No real LLM summarizer is configured (uses truncation fallback)
- The summarization prompt exists but isn't being used

**How to Enable Proper Enrichment**:

Create an LLM summary adapter:

```python
# In src/app/adapters/llama_index/summary_adapter.py
from ...application.interfaces import SummaryGenerator
from ...config import PromptSettings
from ...prompts.loader import load_prompt

class LLMSummaryAdapter(SummaryGenerator):
    def __init__(self, llm, prompt_settings: PromptSettings):
        self._llm = llm
        self._system_prompt = load_prompt(prompt_settings.summarization_system_prompt_path)
    
    def summarize(self, text: str) -> str:
        if len(text) < 50:  # Too short to summarize
            return text
        
        prompt = f"{self._system_prompt}\n\nText to summarize:\n{text}\n\nSummary:"
        response = self._llm.complete(prompt)
        return response.text.strip()
```

Wire it in `container.py`:

```python
# In container.py
self.summary_generator = LLMSummaryAdapter(
    llm=self.llm,
    prompt_settings=self.prompt_settings
)

self.enrichment_service = EnrichmentService(
    observability=self.observability,
    summary_generator=self.summary_generator  # ADD THIS
)
```

Now every chunk will get a proper 2-sentence LLM-generated summary!

---

## Human-in-the-Loop Integration

See detailed answer to Q5 above. Summary:

1. **Data is already flagged**: `llm_segments.segments[].needs_review` and `rationale`
2. **Build query endpoint**: Extract flagged segments from document
3. **Create review UI**: Dashboard page showing segments needing review
4. **Add approval workflow**: Endpoints to approve or edit segments
5. **Tune criteria**: Modify cleaning prompts to adjust what gets flagged

---

## Observability Framework Integration

### Current State

**Existing Observability**:
- `LoggingObservabilityRecorder`: Writes structured JSON events to Python logging
- Events emitted at each pipeline stage with timing and metadata
- No tracing, no parent-child relationships, no evaluation metrics

**Limitations**:
1. No visibility into LLM calls (prompts, responses, tokens used)
2. No way to link a chunk back to its parsing/cleaning/enrichment LLM calls
3. No evaluation metrics (faithfulness, relevance, hallucination detection)
4. No query-time tracing (retrieval → ranking → generation)
5. No cost tracking or performance analytics

### Langfuse Integration

**What Langfuse Provides**:
- **Tracing**: Hierarchical spans for each operation (parse page → clean page → enrich chunk)
- **Prompt Management**: Version and track prompts, A/B test different versions
- **Token & Cost Tracking**: Automatic tracking of LLM usage and costs
- **User Sessions**: Track end-to-end user sessions across multiple queries
- **Evaluation**: Score traces with custom metrics or Ragas integration

**How to Integrate with LlamaIndex**:

**Step 1: Install Langfuse**

```bash
pip install langfuse llama-index-callbacks-langfuse
```

**Step 2: Configure Langfuse callback handler**

```python
# In src/app/config.py
class Settings(BaseSettings):
    # ... existing settings ...
    
    langfuse_public_key: str = Field(default="", env="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", env="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", env="LANGFUSE_HOST")
    enable_langfuse: bool = Field(default=False, env="ENABLE_LANGFUSE")
```

**Step 3: Initialize Langfuse in container**

```python
# In src/app/container.py
from llama_index.core import Settings as LlamaIndexSettings
from llama_index.core.callbacks import CallbackManager

class AppContainer:
    def __init__(self):
        # ... existing initialization ...
        
        # Setup Langfuse callback if enabled
        if self.settings.enable_langfuse:
            from langfuse.llama_index import LlamaIndexCallbackHandler
            
            langfuse_handler = LlamaIndexCallbackHandler(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key,
                host=self.settings.langfuse_host,
            )
            
            # Set global callback manager
            LlamaIndexSettings.callback_manager = CallbackManager([langfuse_handler])
            
            # Store handler for custom traces
            self.langfuse_handler = langfuse_handler
```

**Step 4: Add custom trace context for pipeline stages**

```python
# In src/app/services/pipeline_runner.py
def run(
    self,
    document: Document,
    *,
    file_bytes: bytes | None = None,
    progress_callback: Callable[[PipelineStage, Document], None] | None = None,
) -> PipelineResult:
    
    # Create a Langfuse trace for this pipeline run
    if hasattr(self, 'langfuse_handler'):
        trace = self.langfuse_handler.langfuse.trace(
            name="document_processing_pipeline",
            input={"document_id": document.id, "filename": document.filename},
            metadata={
                "file_type": document.file_type,
                "size_bytes": document.size_bytes,
            }
        )
        
        # Add trace ID to document metadata for linking
        document = document.model_copy(
            update={"metadata": {**document.metadata, "langfuse_trace_id": trace.id}}
        )
    
    # ... existing pipeline stages ...
    
    # Parsing stage
    with trace.span(name="parsing", input={"page_count": 0}) as span:
        document = self.parsing.parse(document, file_bytes=file_bytes)
        span.end(output={"page_count": len(document.pages)})
    
    # Cleaning stage
    with trace.span(name="cleaning") as span:
        document = self.cleaning.clean(document)
        span.end(output={"pages_cleaned": len(document.pages)})
    
    # ... other stages ...
    
    trace.update(output={"final_status": document.status})
    
    return PipelineResult(document=document, stages=stages)
```

**Step 5: Track LLM calls automatically**

LlamaIndex LLM calls are automatically traced by Langfuse callback handler! No changes needed to:
- `ImageAwareParsingAdapter._parse_with_vision_structured()`
- `CleaningAdapter._clean_with_structured_llm()`

**What You Get**:

In the Langfuse UI, you'll see:
```
Trace: document_processing_pipeline (doc_short_clean.pdf)
├─ Span: parsing (42s)
│  ├─ LLM Call: gpt-4o-mini (page 1) - 20.5s, 1.2k tokens
│  │  ├─ Input: [system prompt + image]
│  │  └─ Output: {ParsedPage JSON}
│  └─ LLM Call: gpt-4o-mini (page 2) - 21.5s, 1.8k tokens
├─ Span: cleaning (3s)
│  ├─ LLM Call: gpt-4o-mini (page 1) - 1.5s, 0.3k tokens
│  └─ LLM Call: gpt-4o-mini (page 2) - 1.5s, 0.4k tokens
├─ Span: chunking (0.1s)
├─ Span: enrichment (2s)
│  ├─ LLM Call: gpt-4o-mini (chunk 1) - 0.8s
│  └─ LLM Call: gpt-4o-mini (chunk 2) - 0.9s
└─ Span: vectorization (1s)

Total duration: 48.1s
Total cost: $0.023
```

**Benefits**:
- See exactly which LLM calls are slow
- Track token usage and costs per document
- Drill into any LLM call to see full prompt and response
- Compare different prompt versions
- Identify documents that fail or take too long

---

### Ragas Integration

**What Ragas Provides**:
- **Faithfulness**: Does the response contain only information from the source?
- **Answer Relevancy**: Is the response relevant to the question?
- **Context Precision**: Are the retrieved chunks relevant?
- **Context Recall**: Are all relevant chunks retrieved?
- **Aspect Critique**: Custom evaluation dimensions (harmfulness, correctness, etc.)

**When to Use Ragas**:
- **Query time**: Evaluate retrieval and generation quality for user queries
- **Batch evaluation**: Test pipeline changes on a dataset of questions
- **Continuous monitoring**: Track quality metrics over time

**How to Integrate**:

**Step 1: Install Ragas**

```bash
pip install ragas
```

**Step 2: Create evaluation dataset**

```python
# In tests/evaluation/rag_eval_dataset.py
from datasets import Dataset

# Format: question, ground_truth, contexts (retrieved chunks), answer (generated)
eval_data = {
    "question": [
        "What is the NAVEDTRA number for the Blueprint Reading course?",
        "Who should be contacted for content issues in the training manual?",
    ],
    "ground_truth": [
        "NAVEDTRA 14040A",
        "Surface Warfare Officers School Command (SWOS) at (757) 444-5332",
    ],
    "contexts": [
        # Retrieved chunks for question 1
        [
            "Blueprint Reading and Sketching\nNAVEDTRA 14040A",
            "September 2015\nBlueprint Reading and Sketching",
        ],
        # Retrieved chunks for question 2
        [
            "For content issues, contact the servicing Center of Excellence: Surface Warfare Officers School Command (SWOS) at (757) 444-5332 or DSN 564-5332."
        ],
    ],
    "answer": [
        "The NAVEDTRA number is 14040A.",
        "Contact SWOS at (757) 444-5332 for content issues.",
    ],
}

dataset = Dataset.from_dict(eval_data)
```

**Step 3: Evaluate with Ragas**

```python
# In tests/evaluation/test_rag_quality.py
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)

def test_rag_pipeline_quality():
    # Load evaluation dataset
    dataset = load_eval_dataset()
    
    # Run evaluation
    result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )
    
    print(result)
    # Output:
    # {
    #   'faithfulness': 0.95,
    #   'answer_relevancy': 0.88,
    #   'context_precision': 0.92,
    #   'context_recall': 0.85
    # }
    
    # Assert minimum quality thresholds
    assert result['faithfulness'] > 0.90
    assert result['answer_relevancy'] > 0.80
```

**Step 4: Integrate Ragas with Langfuse**

Ragas can score Langfuse traces automatically:

```python
from langfuse import Langfuse
from ragas.integrations.langfuse import langfuse_evaluate

# Initialize Langfuse client
langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host,
)

# Fetch traces from Langfuse
traces = langfuse.fetch_traces(
    name="rag_query",
    from_timestamp=datetime.now() - timedelta(days=1),
    limit=100,
)

# Score traces with Ragas
langfuse_evaluate(
    langfuse=langfuse,
    traces=traces,
    metrics=[faithfulness, answer_relevancy],
)

# Scores are now visible in Langfuse UI!
```

**Benefits**:
- Automatically score every RAG query with quality metrics
- Track metrics over time (detect quality degradation)
- Filter low-quality responses for review
- A/B test prompt changes and measure impact on quality

---

### Recommended Observability Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Langfuse Cloud/Self-hosted              │
│  - Trace storage & visualization                            │
│  - Prompt management & versioning                           │
│  - Cost tracking & analytics                                │
│  - Quality metrics (from Ragas)                             │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ Traces, Metrics, Scores
                              │
┌─────────────────────────────────────────────────────────────┐
│                  RAG Pipeline Worker                         │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Ingestion  │→ │   Parsing    │→ │   Cleaning   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                  │                  │             │
│         │                  │                  │             │
│         ▼                  ▼                  ▼             │
│  ┌──────────────────────────────────────────────────┐      │
│  │     Langfuse Callback Handler (LlamaIndex)       │      │
│  │  - Automatically captures LLM calls              │      │
│  │  - Records prompts, responses, tokens            │      │
│  │  - Links spans hierarchically                    │      │
│  └──────────────────────────────────────────────────┘      │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Chunking   │→ │  Enrichment  │→ │ Vectorization│      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │     Custom Pipeline Spans (in PipelineRunner)      │    │
│  │  - Stage timing and status                         │    │
│  │  - Document metadata                               │    │
│  │  - Links to stage artifacts                        │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Quality Evaluation
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         Ragas                                │
│  - Evaluates traces from Langfuse                           │
│  - Computes faithfulness, relevancy, precision, recall      │
│  - Scores stored back in Langfuse                           │
│  - Runs in CI/CD and production monitoring                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Recommendations and Action Items

### Immediate Actions (High Priority)

1. **Fix Document Summary Generation** [2-4 hours]
   - **Problem**: Current summary is just first 280 chars of concatenated chunk summaries
   - **Solution**: Implement proper document-level summarization (see Q2 answer)
   - **Files to modify**:
     - `src/app/services/enrichment_service.py` (enrich method)
     - `docs/prompts/summarization/system.md` (tune for document-level synthesis)

2. **Enable LLM Summarization for Chunks** [1-2 hours]
   - **Problem**: Chunks are summarized via truncation, not LLM
   - **Solution**: Create `LLMSummaryAdapter` and wire into `EnrichmentService`
   - **Files to create/modify**:
     - `src/app/adapters/llama_index/summary_adapter.py` (new)
     - `src/app/container.py` (wire summarizer)

3. **Add Page-Level Summaries to Parser** [2-3 hours]
   - **Problem**: No quick overview of page content
   - **Solution**: Add `page_summary` field to `ParsedPage` schema and prompt
   - **Files to modify**:
     - `src/app/parsing/schemas.py` (add field)
     - `docs/prompts/parsing/user.md` (update schema description)

### Short-term Enhancements (1-2 weeks)

4. **Integrate Langfuse for LLM Tracing** [4-6 hours]
   - **Benefit**: Full visibility into LLM calls, costs, and performance
   - **Effort**: Install package, configure callback handler, add custom spans
   - **Files to modify**:
     - `requirements.txt` (add langfuse dependencies)
     - `src/app/config.py` (add Langfuse settings)
     - `src/app/container.py` (initialize callback handler)
     - `src/app/services/pipeline_runner.py` (add trace context)

5. **Build Human-in-the-Loop Review UI** [1 week]
   - **Benefit**: Surface segments flagged by LLM for human review
   - **Effort**: Add API endpoints and dashboard page
   - **Files to create/modify**:
     - `src/app/api/routers.py` (review endpoints)
     - `src/app/api/templates/review.html` (new page)
     - `src/app/api/dashboard.py` (add link to review queue)

6. **Tune Cleaning Prompts for Better Review Flags** [2-3 hours]
   - **Benefit**: More accurate flagging of segments needing review
   - **Effort**: Refine criteria in prompt and test on sample documents
   - **Files to modify**:
     - `docs/prompts/cleaning/system.md`

### Medium-term Improvements (1 month)

7. **Integrate Ragas for Quality Evaluation** [1-2 weeks]
   - **Benefit**: Quantitative metrics for retrieval and generation quality
   - **Effort**: Build eval dataset, integrate Ragas, set up CI tests
   - **Files to create**:
     - `tests/evaluation/rag_eval_dataset.py`
     - `tests/evaluation/test_rag_quality.py`
     - `.github/workflows/rag_evaluation.yml` (CI integration)

8. **Implement Semantic Chunking** [1 week]
   - **Benefit**: Better chunk boundaries based on content structure
   - **Effort**: Use LlamaIndex `SemanticSplitterNodeParser` or component-based chunking
   - **Files to modify**:
     - `src/app/services/chunking_service.py`
     - `src/app/container.py` (configure semantic splitter)

9. **Add Query-time Observability** [1 week]
   - **Benefit**: Trace retrieval → ranking → generation for user queries
   - **Effort**: Instrument query endpoint with Langfuse spans
   - **Files to modify**:
     - `src/app/api/routers.py` (query endpoints)
     - Add retrieval service with observability

### Long-term Vision (3-6 months)

10. **Prompt Version Management**
    - Store prompts in Langfuse, not just files
    - A/B test prompt variations
    - Track metrics per prompt version

11. **Continuous Quality Monitoring**
    - Run Ragas evaluation on production queries
    - Alert on quality degradation
    - Build quality dashboard

12. **Fine-tuning Pipeline**
    - Use human corrections from HITL to fine-tune models
    - Improve cleaning accuracy over time
    - Reduce need for human review

13. **Multi-tenant Observability**
    - Tag traces by user/customer
    - Per-tenant quality metrics
    - Cost allocation by tenant

---

## Conclusion

Your RAG pipeline is well-architected with clear separation of concerns and a solid foundation for observability. The key gaps are:

1. **Document summarization** is too simplistic (concatenation + truncation)
2. **Enrichment** isn't using LLM summarization yet (just truncation)
3. **HITL workflow** has the data but no UI/API to surface it
4. **Observability** is limited to basic logging (no tracing, evaluation, or cost tracking)

By following the recommendations above, you'll have:
- ✅ Accurate, LLM-generated document and chunk summaries
- ✅ Full LLM tracing with Langfuse (prompts, responses, costs, timing)
- ✅ Quality metrics with Ragas (faithfulness, relevance, precision)
- ✅ Human-in-the-loop review workflow for flagged segments
- ✅ Continuous monitoring and improvement pipeline

The architecture is already LlamaIndex-native, so integration with Langfuse and Ragas will be straightforward using their official callback handlers and evaluation APIs.

**Next Steps**:
1. Review this report with your team
2. Prioritize the action items based on your immediate needs
3. Start with fixing document summarization (quick win, high impact)
4. Then add Langfuse for immediate observability gains
5. Build out HITL and Ragas integration iteratively

Let me know if you need more detailed implementation guidance for any of these items!

