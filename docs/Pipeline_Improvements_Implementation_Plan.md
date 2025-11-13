# RAG Pipeline Improvements: Implementation Plan

**Author**: AI Assistant  
**Date**: November 13, 2024  
**Priority**: **HIGH - Pre-Observability Integration**  
**Purpose**: Detailed implementation plan for architectural improvements to support document classification RAG use cases with contextual retrieval, context-aware chunking, and hierarchical RAG patterns.

---

## Executive Summary

Based on your feedback, we need to implement several critical improvements before integrating observability frameworks:

1. **Component-Aware Chunking**: Preserve document structure (tables, images, text types) through chunking
2. **Table Summarization**: Add LLM summaries for tables (like image descriptions)
3. **Cleaned-Text-First Architecture**: Chunk on `cleaned_text` instead of raw text
4. **Contextual Retrieval**: Enrich chunks with component metadata for downstream RAG
5. **Document-Level Context**: Pass full document summaries and metadata to enrichment
6. **Visual Context in Cleaning**: Provide pixmaps to cleaning LLM for better decisions

These changes support **Hierarchical RAG**, **Contextual Retrieval**, and **Context-Aware Chunking** patterns essential for document classification tasks.

---

## Table of Contents

1. [Use Case Context](#use-case-context)
2. [Current Architecture Issues](#current-architecture-issues)
3. [RAG Strategy Patterns](#rag-strategy-patterns)
4. [Implementation Plan](#implementation-plan)
5. [Detailed Technical Specifications](#detailed-technical-specifications)
6. [Testing Strategy](#testing-strategy)
7. [Timeline and Milestones](#timeline-and-milestones)

---

## Use Case Context

### Downstream RAG Requirements

Your document classification RAG agents need to:

✅ **Classification Tasks**:
- Identify document types (blueprints, manuals, specifications, etc.)
- Extract high-level concepts and themes
- Identify mentioned entities (organizations, standards, equipment)

✅ **Semantic Understanding**:
- Understand what drawings/diagrams represent
- Extract relationships between concepts
- Identify document purpose and scope

❌ **Not Required**:
- Specific measurements from drawings
- Precise dimensional data
- Low-level technical specifications

### Implications for Pipeline Design

1. **Metadata is Critical**: Component type (table/image/text), descriptions, and context must be preserved
2. **Summaries Over Details**: High-level summaries more valuable than exact text
3. **Visual Context**: Image descriptions and table summaries are first-class content
4. **Hierarchical Structure**: Document → Page → Component → Chunk hierarchy must be preserved
5. **Clean Text First**: Remove noise (stop words, repetition, irrelevant measurements) before chunking

---

## Current Architecture Issues

### Issue 1: Structured Parsing Lost in Chunking

**Problem**: 
- Parsing identifies components (text, image, table) with rich metadata
- Cleaning processes components individually with `needs_review` flags
- **Chunking discards component boundaries** and chunks on raw text
- Component metadata is attached to chunks but not used for chunking

**Impact**:
- A chunk might span multiple components (e.g., heading + table + paragraph)
- Cannot retrieve "all table chunks" or "image description chunks"
- Downstream RAG doesn't know if retrieved text came from table vs. paragraph

**Example**:
```json
{
  "components": [
    {"id": "1", "type": "heading", "text": "Revision Block"},
    {"id": "2", "type": "table", "rows": [...]},
    {"id": "3", "type": "text", "text": "If a revision has been made..."}
  ]
}
```

Current chunking creates: `chunk1 = "Revision Block [table data] If a revision..."`  
Should create: `chunk1 = heading, chunk2 = table, chunk3 = paragraph` (or component-aware boundaries)

---

### Issue 2: Tables Lack Summaries

**Problem**:
- Images get `description` field from vision LLM
- Tables are extracted as `rows` (raw data) with no summary
- Downstream RAG can't understand table content without parsing rows

**Impact**:
- Cannot retrieve tables based on semantic meaning
- RAG queries like "find tables about revision history" won't work
- Table embeddings are based on raw cell values, not meaning

**Solution**: Add `table_summary` field to tables during parsing or enrichment

---

### Issue 3: Chunking on Raw Text Instead of Cleaned Text

**Problem**:
```python
# Current: chunks raw text first
raw_text = page.text  # From pdfplumber
segments = self._split_text(raw_text, size, overlap)

# Then extracts cleaned text slice
chunk_cleaned_text = cleaned_text[start:end] if cleaned_text else None
```

**Impact**:
- Chunk boundaries determined by raw text (with noise, bad spacing)
- Cleaned text is just "attached" after the fact
- If cleaning removes content, slices might not align properly
- Embedding vectors are generated from cleaned text but chunks are defined by raw text boundaries

**Solution**: Chunk on `cleaned_text` as primary source, keep raw text for reference only

---

### Issue 4: Component Context Not Preserved with Vectors

**Problem**:
- Vectors stored in `chunk.metadata.extra.vector`
- Component type, description, table summary not in retrievable metadata
- Cannot filter retrieval by component type ("only search image descriptions")

**Impact**:
- Downstream RAG treats all chunks equally (text, table, image descriptions)
- Cannot implement contextual retrieval patterns
- Cannot weight chunks differently based on source (e.g., prioritize headings for classification)

**Solution**: Store component metadata alongside vectors in a structured way

---

### Issue 5: Document Context Missing from Enrichment

**Problem**:
- Each chunk enriched independently with no document-level context
- Chunk summaries don't reference document purpose, topic, or structure
- Document summary is just truncated concatenation (280 chars)

**Impact**:
- Chunks lack "where do I fit in the document" context
- Cannot implement hierarchical RAG (query doc summary → retrieve relevant pages → retrieve chunks)
- Enrichment quality is poor

**Solution**: Pass document-level and page-level summaries to chunk enrichment

---

### Issue 6: Cleaning Without Visual Context

**Problem**:
- Cleaning LLM receives `ParsedPage.components` (text only)
- No access to the page pixmap (image)
- Visual context could help cleaning decisions (e.g., identifying header/footer, detecting table structure)

**Impact**:
- Cleaning decisions based on text alone
- May incorrectly flag or clean content without visual context
- Cannot detect visual patterns (repeating headers, watermarks, etc.)

**Solution**: Pass pixmap path to cleaning LLM for visual reference

---

## RAG Strategy Patterns

### Pattern 1: Contextual Retrieval

**Concept** (from Anthropic):
- Prepend chunk context to each chunk before embedding
- Context includes: document title, page number, section heading, component type
- Improves retrieval by giving chunks "situational awareness"

**Example**:
```
Without context:
"If a revision has been made, the revision block will be in the upper right corner."

With context:
[Document: Blueprint Reading Manual | Page: 2 | Section: Revision Block | Type: Paragraph]
If a revision has been made, the revision block will be in the upper right corner.
```

**Implementation in Our Pipeline**:
1. During enrichment, prepend context string to chunk text before embedding
2. Store original text separately for generation
3. Embed the contextualized version

**Benefits for Document Classification**:
- Queries like "what is this document about" retrieve chunks with document context
- Can filter by component type ("image descriptions only")
- Better disambiguates similar text from different contexts

---

### Pattern 2: Context-Aware Chunking

**Concept**:
- Chunk boundaries respect document structure
- Don't split components (keep table rows together, keep heading with first paragraph)
- Preserve semantic units

**Strategies**:
1. **Component-Based Chunking**: One chunk per component (or group of small components)
2. **Hierarchical Chunking**: Create parent chunks (pages/sections) and child chunks (components)
3. **Boundary-Aware Splitting**: If fixed-size chunking, only split at component boundaries

**Implementation in Our Pipeline**:
- Primary: Component-based chunking (each component becomes a chunk)
- Secondary: Group small components (heading + first paragraph) if under size threshold
- Fallback: Split large components (long paragraphs) at sentence boundaries

**Benefits for Document Classification**:
- Entire table stays together (can be summarized and retrieved as unit)
- Image descriptions stay atomic (not split mid-description)
- Headings provide clear semantic boundaries

---

### Pattern 3: Hierarchical RAG

**Concept**:
- Store documents at multiple granularity levels:
  - Level 1: Document summary (high-level classification)
  - Level 2: Page summaries (section-level understanding)
  - Level 3: Component chunks (detailed content)
- Query strategy:
  1. First retrieve relevant document summaries
  2. Then retrieve relevant pages within those documents
  3. Finally retrieve specific chunks within those pages

**Implementation in Our Pipeline**:
1. **Document Node**: Store document-level summary and metadata as separate index entry
2. **Page Nodes**: Store page-level summaries as separate index entries (linked to document)
3. **Chunk Nodes**: Store component chunks (linked to pages)
4. **Retrieval**: Multi-stage retrieval with parent-child relationships

**Benefits for Document Classification**:
- Can answer "what type of document is this" from document-level summary alone
- Reduces search space (only search relevant pages for detail questions)
- Provides hierarchical context to generation

---

## Implementation Plan

### Phase 1: Schema and Data Model Changes [3-4 days]

**Goal**: Update schemas to support component metadata, table summaries, and hierarchical structure

#### Task 1.1: Update ParsedPage Schema

**File**: `src/app/parsing/schemas.py`

**Changes**:
```python
class ParsedTableComponent(BaseModel):
    type: Literal["table"] = "table"
    id: str
    order: int
    caption: str | None = None
    rows: list[dict[str, str]]
    bbox: dict[str, float] | None = None
    table_summary: str | None = None  # NEW: LLM-generated summary

class ParsedPage(BaseModel):
    document_id: str
    page_number: int
    raw_text: str
    components: list[ParsedTextComponent | ParsedImageComponent | ParsedTableComponent]
    page_summary: str | None = None  # Already planned, reiterate here
```

**Rationale**: Tables need summaries just like images have descriptions

---

#### Task 1.2: Update Chunk Metadata Schema

**File**: `src/app/domain/models.py`

**Changes**:
```python
class Metadata(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    page_number: int
    chunk_id: str
    start_offset: int
    end_offset: int
    title: str | None = None
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    
    # NEW: Component context for contextual retrieval
    component_id: str | None = None  # Links to parsed component
    component_type: str | None = None  # "text", "image", "table"
    component_order: int | None = None  # Order in page
    component_description: str | None = None  # For images
    component_summary: str | None = None  # For tables
    
    # NEW: Hierarchical context
    document_title: str | None = None
    document_summary: str | None = None
    page_summary: str | None = None
    section_heading: str | None = None  # Preceding heading if applicable
    
    extra: dict[str, Any] = Field(default_factory=dict)
```

**Rationale**: 
- Component metadata enables contextual retrieval
- Hierarchical context enables context-aware retrieval
- All metadata available at query time for filtering/ranking

---

#### Task 1.3: Add Contextualized Text Field to Chunk

**File**: `src/app/domain/models.py`

**Changes**:
```python
class Chunk(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    page_number: int
    text: str  # Original raw text (for reference)
    cleaned_text: str | None = None  # Cleaned text (for generation)
    contextualized_text: str | None = None  # NEW: Text with context prefix (for embedding)
    start_offset: int
    end_offset: int
    metadata: Metadata | None = None
```

**Rationale**: Separate text for embedding (with context) vs. generation (without context)

---

### Phase 2: Parsing Enhancements [4-5 days]

**Goal**: Add table summarization and page summaries to parsing stage

#### Task 2.1: Add Table Summarization to Parsing Prompt

**File**: `docs/prompts/parsing/user.md`

**Changes**:
```markdown
### Table Components

For each table, extract:
- `caption`: Table title or caption if present
- `rows`: Array of row objects with column:value pairs
- `table_summary`: **NEW** - A 2-3 sentence summary of what the table shows
  - Describe the table's purpose and key information
  - Example: "This table lists revision history for the drawing, showing revision letters, descriptions, authors, and approval dates. The table is currently empty, indicating no revisions have been made yet."

**Important**: Always provide `table_summary` even if the table is empty or simple.
```

**Files**: Update both `system.md` and `user.md` with table summarization instructions

---

#### Task 2.2: Update ImageAwareParsingAdapter

**File**: `src/app/adapters/llama_index/parsing_adapter.py`

**Changes**: Ensure `ParsedTableComponent.table_summary` is extracted from LLM response

**Testing**:
- Run parsing on documents with tables
- Verify `table_summary` is populated
- Verify summary quality (descriptive, accurate, concise)

---

#### Task 2.3: Add Page Summarization

**Already planned in previous report** - ensure implementation includes:
- `page_summary` field in prompt
- Summary describes page role in document
- Summary mentions key components (tables, images, headings)

---

### Phase 3: Cleaning Enhancements [3-4 days]

**Goal**: Provide visual context to cleaning LLM and preserve component structure

#### Task 3.1: Add Pixmap Parameter to CleaningAdapter

**File**: `src/app/adapters/llama_index/cleaning_adapter.py`

**Changes**:
```python
class CleaningAdapter(CleaningLLM):
    def __init__(
        self,
        llm: Any,
        prompt_settings: PromptSettings,
        use_structured_outputs: bool = True,
        use_vision: bool = True,  # NEW: Enable vision-based cleaning
    ) -> None:
        self._llm = llm
        self._use_structured_outputs = use_structured_outputs
        self._use_vision = use_vision
        # ... existing init ...

    def clean_page(
        self, 
        parsed_page: ParsedPage,
        pixmap_path: str | None = None,  # NEW: Optional page image
    ) -> CleanedPage:
        # If vision enabled and pixmap provided, include in LLM call
        if self._use_vision and pixmap_path:
            return self._clean_with_vision(parsed_page, pixmap_path)
        else:
            return self._clean_without_vision(parsed_page)
```

---

#### Task 3.2: Update Cleaning Prompt for Vision

**File**: `docs/prompts/cleaning/system.md`

**Changes**:
```markdown
You normalize parsed document content. Clean grammar and spacing but never fabricate information. 
Highlight segments that require manual review.

**When provided with a page image**:
- Use visual context to inform cleaning decisions
- Identify visual patterns (headers, footers, watermarks) that should be removed
- Verify OCR text against visual layout
- Detect tables/images that may have been missed in parsing
- Flag segments where visual context suggests inaccuracy
```

---

#### Task 3.3: Update CleaningService to Pass Pixmap

**File**: `src/app/services/cleaning_service.py`

**Changes**:
```python
def clean(self, document: Document) -> Document:
    # ... existing logic ...
    
    parsed_pages_meta = updated_metadata.get("parsed_pages", {})
    pixmap_assets = updated_metadata.get("pixmap_assets", {})  # NEW: Get pixmaps
    
    for page in document.pages:
        raw_text = page.text or ""
        cleaned_page_text = self.normalizer(raw_text)
        cleaned_segments: CleanedPage | None = None

        if self.structured_cleaner:
            parsed_payload = parsed_pages_meta.get(str(page.page_number))
            pixmap_path = pixmap_assets.get(str(page.page_number))  # NEW: Get pixmap for page
            
            if parsed_payload:
                parsed_page = ParsedPage.model_validate(parsed_payload)
                # Pass pixmap to cleaner
                cleaned_segments = self._run_structured_cleaner(parsed_page, pixmap_path)
                # ... rest of logic ...
```

---

### Phase 4: Chunking Overhaul [5-7 days]

**Goal**: Implement component-aware chunking on cleaned text with preserved structure

#### Task 4.1: Create Component-Based Chunking Strategy

**File**: `src/app/services/chunking_service.py` (major refactor)

**New Architecture**:
```python
class ChunkingService:
    def __init__(
        self,
        observability: ObservabilityRecorder,
        latency: float = 0.0,
        strategy: str = "component",  # NEW: "component", "hybrid", "fixed"
        component_merge_threshold: int = 100,  # Merge small components
        max_component_tokens: int = 500,  # Split large components
        # ... existing params ...
    ):
        self.strategy = strategy
        self.component_merge_threshold = component_merge_threshold
        self.max_component_tokens = max_component_tokens
        # ... existing init ...

    def chunk(self, document: Document) -> Document:
        if self.strategy == "component":
            return self._chunk_by_components(document)
        elif self.strategy == "hybrid":
            return self._chunk_hybrid(document)
        else:
            return self._chunk_fixed_size(document)  # Existing logic
```

---

#### Task 4.2: Implement Component-Based Chunking

**Strategy**:
1. Iterate through `parsed_pages[N].components` (from metadata)
2. For each component:
   - If component is small (< threshold tokens), group with next component
   - If component is large (> max tokens), split at sentence boundaries
   - Otherwise, create one chunk per component
3. Extract corresponding `cleaned_text` slice based on component text
4. Attach component metadata to chunk

**Pseudocode**:
```python
def _chunk_by_components(self, document: Document) -> Document:
    parsed_pages_meta = document.metadata.get("parsed_pages", {})
    
    for page in document.pages:
        parsed_page_data = parsed_pages_meta.get(str(page.page_number))
        if not parsed_page_data:
            # Fallback to fixed-size if no parsed components
            continue
        
        components = parsed_page_data["components"]
        chunks = []
        current_group = []
        current_tokens = 0
        
        for component in components:
            component_text = self._extract_component_text(component)
            component_tokens = len(component_text.split())
            
            # Strategy: Group small components, split large ones
            if component_tokens > self.max_component_tokens:
                # Split large component
                sub_chunks = self._split_large_component(component, page)
                chunks.extend(sub_chunks)
            elif current_tokens + component_tokens < self.component_merge_threshold:
                # Merge small components
                current_group.append(component)
                current_tokens += component_tokens
            else:
                # Flush current group and start new
                if current_group:
                    chunks.append(self._create_chunk_from_components(current_group, page))
                current_group = [component]
                current_tokens = component_tokens
        
        # Flush remaining
        if current_group:
            chunks.append(self._create_chunk_from_components(current_group, page))
        
        # Update page with chunks
        updated_page = page.model_copy(update={"chunks": chunks})
        document = document.replace_page(page.page_number, updated_page)
    
    return document.model_copy(update={"status": "chunked"})
```

---

#### Task 4.3: Extract Cleaned Text for Component Chunks

**Challenge**: Components are defined by `order` in parsed page, need to map to `cleaned_text` positions

**Solution**:
1. Use component text to find position in `page.cleaned_text`
2. Or: Store component start/end offsets during cleaning stage
3. Extract corresponding slice from cleaned text

**Implementation**:
```python
def _create_chunk_from_components(
    self, 
    components: list[dict], 
    page: Page
) -> Chunk:
    # Extract text from components
    component_texts = [self._extract_component_text(comp) for comp in components]
    combined_text = "\n\n".join(component_texts)
    
    # Find in cleaned text
    cleaned_slice = self._find_in_cleaned_text(combined_text, page.cleaned_text)
    
    # Get first and last component for metadata
    first_comp = components[0]
    last_comp = components[-1]
    
    # Build metadata with component context
    metadata = Metadata(
        document_id=page.document_id,
        page_number=page.page_number,
        chunk_id=str(uuid4()),
        component_id=first_comp["id"],
        component_type=first_comp["type"],
        component_order=first_comp["order"],
        # Add description/summary based on type
        component_description=first_comp.get("description") if first_comp["type"] == "image" else None,
        component_summary=first_comp.get("table_summary") if first_comp["type"] == "table" else None,
        # ... other metadata ...
    )
    
    return Chunk(
        id=metadata.chunk_id,
        document_id=page.document_id,
        page_number=page.page_number,
        text=combined_text,  # Raw component text
        cleaned_text=cleaned_slice,  # Cleaned version
        metadata=metadata,
    )
```

---

#### Task 4.4: Update Document Model with Helper Methods

**File**: `src/app/domain/models.py`

**Add**:
```python
class Document(BaseModel):
    # ... existing fields ...
    
    def replace_page(self, page_number: int, new_page: Page) -> Document:
        """Replace a page in the document."""
        updated_pages = [
            new_page if p.page_number == page_number else p
            for p in self.pages
        ]
        return self.model_copy(update={"pages": updated_pages})
```

---

### Phase 5: Enrichment Overhaul [4-5 days]

**Goal**: Add document-level context to chunk enrichment and implement contextual text generation

#### Task 5.1: Add Document Summarization Stage

**File**: `src/app/services/enrichment_service.py` or new `document_summarization_service.py`

**New Method**:
```python
def _generate_document_summary(self, document: Document) -> str:
    """Generate comprehensive document-level summary."""
    if not self.summary_generator:
        # Fallback: concatenate page summaries
        parsed_pages = document.metadata.get("parsed_pages", {})
        page_summaries = []
        for page_num in range(1, len(document.pages) + 1):
            parsed_page = parsed_pages.get(str(page_num))
            if parsed_page and parsed_page.get("page_summary"):
                page_summaries.append(f"Page {page_num}: {parsed_page['page_summary']}")
        return " ".join(page_summaries)[:500]
    
    # Use LLM to generate document summary
    # Collect cleaned text from all pages (or page summaries)
    content = []
    parsed_pages = document.metadata.get("parsed_pages", {})
    
    for page in document.pages:
        page_data = parsed_pages.get(str(page.page_number), {})
        if page_summary := page_data.get("page_summary"):
            content.append(f"**Page {page.page_number}**: {page_summary}")
        else:
            # Fallback to first 300 chars of cleaned text
            content.append(f"**Page {page.page_number}**: {(page.cleaned_text or page.text)[:300]}...")
    
    context = "\n\n".join(content)
    
    prompt = f"""Document: {document.filename}
File Type: {document.file_type}
Total Pages: {len(document.pages)}

Page Summaries:
{context}

Generate a comprehensive 3-4 sentence summary of this entire document. Focus on:
1. Document type and purpose
2. Main topics covered
3. Key entities or standards mentioned
4. Overall scope and audience

Summary:"""
    
    return self.summary_generator.summarize(prompt)
```

---

#### Task 5.2: Enhance Chunk Enrichment with Context

**File**: `src/app/services/enrichment_service.py`

**Changes**:
```python
def enrich(self, document: Document) -> Document:
    # FIRST: Generate document-level summary
    document_summary = self._generate_document_summary(document)
    
    # Get page summaries
    parsed_pages = document.metadata.get("parsed_pages", {})
    page_summaries = {
        str(page.page_number): parsed_pages.get(str(page.page_number), {}).get("page_summary")
        for page in document.pages
    }
    
    # Get preceding heading for each page (for section context)
    section_headings = self._extract_section_headings(document)
    
    summaries: list[str] = []
    updated_pages = []
    
    for page in document.pages:
        page_summary = page_summaries.get(str(page.page_number))
        section_heading = section_headings.get(page.page_number)
        
        updated_chunks = []
        for chunk in page.chunks:
            # Enrich chunk with hierarchical context
            enriched_chunk = self._enrich_chunk_with_context(
                chunk=chunk,
                document_title=document.filename,
                document_summary=document_summary,
                page_summary=page_summary,
                section_heading=section_heading,
            )
            updated_chunks.append(enriched_chunk)
            if enriched_chunk.metadata and enriched_chunk.metadata.summary:
                summaries.append(enriched_chunk.metadata.summary)
        
        updated_page = page.model_copy(update={"chunks": updated_chunks})
        updated_pages.append(updated_page)
    
    return document.model_copy(
        update={
            "pages": updated_pages,
            "summary": document_summary,  # Now a real summary!
            "status": "enriched",
        }
    )
```

---

#### Task 5.3: Generate Contextualized Text for Embedding

**File**: `src/app/services/enrichment_service.py`

**New Method**:
```python
def _enrich_chunk_with_context(
    self,
    chunk: Chunk,
    document_title: str,
    document_summary: str,
    page_summary: str | None,
    section_heading: str | None,
) -> Chunk:
    """Enrich chunk with summaries and generate contextualized text."""
    
    # Generate chunk summary if missing
    chunk_summary = chunk.metadata.summary if chunk.metadata else None
    if not chunk_summary and self.summary_generator:
        # Pass hierarchical context to summary generation
        summary_prompt = f"""Document: {document_title}
Document Summary: {document_summary}
Page {chunk.page_number} Summary: {page_summary or 'N/A'}
Component Type: {chunk.metadata.component_type if chunk.metadata else 'text'}

Chunk Text:
{chunk.cleaned_text or chunk.text}

Generate a 2-sentence summary of this chunk, explaining what information it contains and how it relates to the document's overall purpose.

Summary:"""
        chunk_summary = self.summary_generator.summarize(summary_prompt)
    
    # Build contextualized text for embedding (Anthropic pattern)
    context_parts = [
        f"Document: {document_title}",
        f"Page: {chunk.page_number}",
    ]
    
    if section_heading:
        context_parts.append(f"Section: {section_heading}")
    
    if chunk.metadata:
        if chunk.metadata.component_type:
            context_parts.append(f"Type: {chunk.metadata.component_type}")
        if chunk.metadata.component_description:
            context_parts.append(f"Description: {chunk.metadata.component_description}")
        if chunk.metadata.component_summary:
            context_parts.append(f"Table Summary: {chunk.metadata.component_summary}")
    
    context_prefix = " | ".join(context_parts)
    contextualized_text = f"[{context_prefix}]\n\n{chunk.cleaned_text or chunk.text}"
    
    # Update metadata
    updated_metadata = (chunk.metadata or Metadata(
        document_id=chunk.document_id,
        page_number=chunk.page_number,
        chunk_id=chunk.id,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
    )).model_copy(update={
        "summary": chunk_summary,
        "document_title": document_title,
        "document_summary": document_summary,
        "page_summary": page_summary,
        "section_heading": section_heading,
    })
    
    return chunk.model_copy(update={
        "metadata": updated_metadata,
        "contextualized_text": contextualized_text,
    })
```

---

#### Task 5.4: Extract Section Headings

**File**: `src/app/services/enrichment_service.py`

**Helper Method**:
```python
def _extract_section_headings(self, document: Document) -> dict[int, str]:
    """Extract section headings for each page."""
    parsed_pages = document.metadata.get("parsed_pages", {})
    headings = {}
    current_heading = None
    
    for page in document.pages:
        parsed_page = parsed_pages.get(str(page.page_number))
        if not parsed_page:
            headings[page.page_number] = current_heading
            continue
        
        # Find first heading component on page
        for component in parsed_page.get("components", []):
            if component.get("type") == "text" and component.get("text_type") == "heading":
                current_heading = component.get("text")
                break
        
        headings[page.page_number] = current_heading
    
    return headings
```

---

### Phase 6: Vectorization Updates [2-3 days]

**Goal**: Embed contextualized text and ensure metadata is retrievable

#### Task 6.1: Update VectorService to Embed Contextualized Text

**File**: `src/app/services/vector_service.py`

**Changes**:
```python
def vectorize(self, document: Document) -> Document:
    # ... existing setup ...
    
    for page in document.pages:
        updated_chunks = []
        # Use contextualized_text for embedding, not cleaned_text
        chunk_texts = [
            chunk.contextualized_text or chunk.cleaned_text or chunk.text 
            for chunk in page.chunks
        ]
        embeddings = self._embed_batch(chunk_texts)
        
        for chunk, vector in zip(page.chunks, embeddings):
            # Store vector with metadata
            if chunk.metadata:
                updated_extra = chunk.metadata.extra.copy()
                updated_extra["vector"] = vector
                updated_extra["vector_dimension"] = self.dimension
                updated_metadata = chunk.metadata.model_copy(update={"extra": updated_extra})
                updated_chunk = chunk.model_copy(update={"metadata": updated_metadata})
            else:
                updated_chunk = chunk
            
            updated_chunks.append(updated_chunk)
            # ... rest of logic ...
```

**Rationale**: Contextual retrieval improves by embedding the context-enriched text

---

#### Task 6.2: Update Vector Store Integration (Future)

**Note**: When integrating with vector database:
- Ensure `chunk.metadata.component_type`, `component_description`, `component_summary` are indexed as filterable fields
- Enable metadata filtering (e.g., "only retrieve from tables" or "only image descriptions")
- Store both `cleaned_text` (for generation) and `contextualized_text` (for embedding)

**Example Vector Store Schema**:
```python
{
    "id": "chunk-uuid",
    "vector": [0.1, 0.2, ...],  # From contextualized_text
    "metadata": {
        "document_id": "doc-uuid",
        "document_title": "Blueprint Reading Manual",
        "document_summary": "...",
        "page_number": 2,
        "page_summary": "...",
        "section_heading": "Revision Block",
        "component_type": "table",
        "component_summary": "This table lists revision history...",
        "chunk_summary": "...",
    },
    "content": "If a revision has been made..."  # cleaned_text for generation
}
```

---

### Phase 7: Update Container and Configuration [1-2 days]

**Goal**: Wire new components and make strategies configurable

#### Task 7.1: Update AppContainer

**File**: `src/app/container.py`

**Changes**:
```python
class AppContainer:
    def __init__(self):
        # ... existing initialization ...
        
        # Create summary generator (new)
        self.summary_generator = LLMSummaryAdapter(
            llm=self.llm,
            prompt_settings=self.prompt_settings
        )
        
        # Update cleaning service to use vision
        self.cleaning_service = CleaningService(
            observability=self.observability,
            structured_cleaner=CleaningAdapter(
                llm=self.llm,
                prompt_settings=self.prompt_settings,
                use_vision=self.settings.use_vision_cleaning,  # NEW config
            ),
        )
        
        # Update chunking service with component strategy
        self.chunking_service = ChunkingService(
            observability=self.observability,
            strategy=self.settings.chunking_strategy,  # NEW config
            component_merge_threshold=self.settings.component_merge_threshold,
            max_component_tokens=self.settings.max_component_tokens,
        )
        
        # Update enrichment service with summary generator
        self.enrichment_service = EnrichmentService(
            observability=self.observability,
            summary_generator=self.summary_generator,  # NOW WIRED
        )
```

---

#### Task 7.2: Add Configuration Settings

**File**: `src/app/config.py`

**Add**:
```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Chunking strategy
    chunking_strategy: str = Field(default="component", env="CHUNKING_STRATEGY")
    component_merge_threshold: int = Field(default=100, env="COMPONENT_MERGE_THRESHOLD")
    max_component_tokens: int = Field(default=500, env="MAX_COMPONENT_TOKENS")
    
    # Cleaning vision
    use_vision_cleaning: bool = Field(default=True, env="USE_VISION_CLEANING")
    
    # Enrichment
    use_llm_summarization: bool = Field(default=True, env="USE_LLM_SUMMARIZATION")
```

---

## Detailed Technical Specifications

### Component-Based Chunking Algorithm

**Input**: Document with `parsed_pages` metadata containing components  
**Output**: Document with component-aware chunks

**Algorithm**:
```
FOR each page in document:
    components = get_parsed_components(page)
    chunks = []
    current_group = []
    current_tokens = 0
    
    FOR each component in components:
        component_tokens = count_tokens(component.text)
        
        IF component_tokens > MAX_COMPONENT_TOKENS:
            # Component too large, split it
            sub_chunks = split_component_at_sentences(component)
            chunks.extend(sub_chunks)
        
        ELIF current_tokens + component_tokens < MERGE_THRESHOLD:
            # Component small enough to merge
            current_group.append(component)
            current_tokens += component_tokens
        
        ELSE:
            # Flush current group, start new one
            IF current_group not empty:
                chunks.append(create_chunk(current_group))
            current_group = [component]
            current_tokens = component_tokens
    
    # Flush remaining components
    IF current_group not empty:
        chunks.append(create_chunk(current_group))
    
    page.chunks = chunks

RETURN document
```

**Edge Cases**:
1. **No parsed components**: Fallback to fixed-size chunking on cleaned text
2. **Very large table**: Split table rows into multiple chunks (keep caption with first chunk)
3. **Image-only page**: Create single chunk with image description as text
4. **Empty components**: Skip empty components (e.g., empty table cells)

---

### Contextualized Text Generation

**Template**:
```
[Document: {document_title} | Page: {page_number} | Section: {section_heading} | Type: {component_type}]

{chunk_text}
```

**Example**:
```
[Document: Blueprint Reading Manual.pdf | Page: 2 | Section: Revision Block | Type: table]

| SYM | DESCRIPTION | BY | DATE APPD |
|-----|-------------|-----|-----------|
|     |             |     |           |
```

**For Images**:
```
[Document: Blueprint Reading Manual.pdf | Page: 1 | Type: image | Description: A circular emblem featuring a ship's wheel and an eagle]

A circular emblem featuring a ship's wheel and an eagle, surrounded by a blue and gold border. The emblem represents the Surface Warfare Officers School Command.
```

**Benefits**:
- Query "find tables about revisions" matches context prefix
- Embedding captures both content AND context
- Generation uses original text (without context prefix)

---

### Hierarchical RAG Index Structure

**Proposed Vector Store Layout**:

```
Documents Index:
- doc-uuid-1: {vector: [...], metadata: {type: "document_summary", title: "...", summary: "..."}}
- doc-uuid-2: {vector: [...], metadata: {type: "document_summary", title: "...", summary: "..."}}

Pages Index:
- page-uuid-1: {vector: [...], metadata: {type: "page_summary", doc_id: "...", page_num: 1, summary: "..."}}
- page-uuid-2: {vector: [...], metadata: {type: "page_summary", doc_id: "...", page_num: 2, summary: "..."}}

Chunks Index:
- chunk-uuid-1: {vector: [...], metadata: {type: "chunk", doc_id: "...", page_num: 1, component_type: "table", ...}}
- chunk-uuid-2: {vector: [...], metadata: {type: "chunk", doc_id: "...", page_num: 1, component_type: "text", ...}}
```

**Retrieval Strategy**:
```python
# Stage 1: Find relevant documents
relevant_docs = vector_store.search(query, filter={"type": "document_summary"}, top_k=3)

# Stage 2: Find relevant pages within those documents
doc_ids = [doc.metadata.doc_id for doc in relevant_docs]
relevant_pages = vector_store.search(query, filter={"type": "page_summary", "doc_id": {"$in": doc_ids}}, top_k=10)

# Stage 3: Find relevant chunks within those pages
page_ids = [(page.metadata.doc_id, page.metadata.page_num) for page in relevant_pages]
relevant_chunks = vector_store.search(query, filter={"type": "chunk", "page": {"$in": page_ids}}, top_k=20)

# Stage 4: Re-rank chunks and generate response
ranked_chunks = rerank_with_metadata(relevant_chunks, query)
response = generate(query, context=ranked_chunks)
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_chunking_component_aware.py`

**Test Cases**:
1. `test_component_chunking_preserves_table()`: Verify entire table becomes one chunk
2. `test_component_chunking_merges_small_components()`: Verify heading + paragraph merged
3. `test_component_chunking_splits_large_component()`: Verify long paragraph split at sentences
4. `test_component_metadata_preserved()`: Verify component type, description, summary in metadata
5. `test_cleaned_text_extraction()`: Verify cleaned text correctly extracted for component chunks

---

### Integration Tests

**File**: `tests/test_end_to_end_hierarchical.py`

**Test Cases**:
1. `test_pipeline_with_component_chunking()`: Run full pipeline, verify component chunks
2. `test_table_summarization()`: Verify tables have summaries
3. `test_contextualized_text_generation()`: Verify chunks have context prefixes
4. `test_document_summary_quality()`: Verify document summary covers all pages
5. `test_metadata_preservation()`: Verify all component metadata reaches vectorization

---

### Manual QA Tests

**Documents**:
1. **Blueprint with tables**: Verify table chunks have summaries
2. **Manual with images**: Verify image description chunks
3. **Multi-section document**: Verify section headings propagate
4. **Mixed content page**: Verify component boundaries respected

**Validation**:
- Inspect `document.json` output
- Verify `contextualized_text` makes sense
- Check chunk boundaries align with components
- Confirm metadata is complete

---

## Timeline and Milestones

### Week 1: Schema and Parsing (Tasks 1.1-2.3)
- **Days 1-2**: Update schemas (ParsedPage, Metadata, Chunk)
- **Days 3-4**: Add table summarization to parsing
- **Day 5**: Add page summarization, test parsing stage

**Deliverable**: Documents have table summaries and page summaries

---

### Week 2: Cleaning and Chunking (Tasks 3.1-4.4)
- **Days 1-2**: Add vision support to cleaning
- **Days 3-5**: Implement component-based chunking
- **Days 6-7**: Test chunking with sample documents

**Deliverable**: Documents chunked by components with preserved metadata

---

### Week 3: Enrichment and Vectorization (Tasks 5.1-6.2)
- **Days 1-3**: Implement document summarization and contextual enrichment
- **Days 4-5**: Update vectorization to use contextualized text
- **Days 6-7**: End-to-end testing

**Deliverable**: Full pipeline with hierarchical context and contextual retrieval

---

### Week 4: Integration and Testing (Task 7.1-7.2 + Testing)
- **Days 1-2**: Update container and configuration
- **Days 3-4**: Write comprehensive tests
- **Days 5-7**: Manual QA, bug fixes, documentation

**Deliverable**: Production-ready pipeline with full test coverage

---

## Success Criteria

### Functional Requirements

✅ **Component Preservation**:
- All chunks linked to source components (type, ID, order)
- Table chunks include table summaries
- Image chunks include descriptions

✅ **Cleaned Text First**:
- Chunking operates on `cleaned_text` as primary source
- Chunk boundaries respect component boundaries

✅ **Contextual Retrieval**:
- Chunks have `contextualized_text` with document/page/section context
- Metadata includes document_summary, page_summary, component metadata

✅ **Hierarchical Structure**:
- Document-level summary is high-quality LLM-generated
- Page summaries available
- Section headings propagated to chunks

✅ **Visual Context in Cleaning**:
- Cleaning LLM receives pixmap for visual context
- Visual patterns detected and handled

---

### Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Table summary quality | >90% relevant | Manual review of 20 tables |
| Document summary completeness | Covers all pages | Verify references to content from each page |
| Component chunk purity | >95% single-component chunks | Count mixed-component chunks |
| Metadata completeness | 100% chunks have component_type | Automated check |
| Contextualized text format | 100% have context prefix | Automated check |

---

### Performance Benchmarks

| Stage | Current | Target | Notes |
|-------|---------|--------|-------|
| Parsing (with table summarization) | ~21s/page | <25s/page | LLM call for table summary |
| Cleaning (with vision) | ~1.5s/page | <2.5s/page | Vision API may be slower |
| Chunking (component-based) | N/A | <0.5s/page | Should be faster (fewer chunks) |
| Enrichment (with context) | ~0.8s/chunk | <1.5s/chunk | Context-aware summarization |
| Total pipeline | ~48s/doc (2 pages) | <60s/doc | Acceptable for classification use case |

---

## Dependencies and Risks

### Dependencies

1. **LLM Provider**: Need vision-capable LLM for cleaning with pixmaps (GPT-4o-mini has vision)
2. **Token Limits**: Longer context for document summarization may hit limits
3. **Cost**: More LLM calls (table summaries, vision cleaning) increase cost

### Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Component chunking too slow | High | Low | Fallback to fixed-size if no parsed components |
| Table summaries low quality | Medium | Medium | Tune prompts, provide examples |
| Vision cleaning doesn't improve quality | Low | Medium | Make vision optional, A/B test |
| Context prefix confuses embedding | High | Low | Test retrieval quality, can disable prefix |
| Document summary tokens exceed limit | Medium | Medium | Truncate page summaries, use sampling |

---

## Rollout Strategy

### Phase 1: Shadow Mode (Week 1-2)
- Implement new chunking alongside old
- Generate both component chunks and fixed-size chunks
- Compare outputs manually
- No production impact

### Phase 2: A/B Testing (Week 3)
- Route 10% of documents through new pipeline
- Monitor quality metrics
- Compare retrieval performance (when RAG is built)
- Gather feedback

### Phase 3: Full Rollout (Week 4)
- Switch all documents to new pipeline
- Monitor for issues
- Keep fixed-size chunking as fallback

### Phase 4: Cleanup (Week 5)
- Remove old chunking code
- Optimize performance
- Update documentation

---

## Next Actions

1. **Review this plan with team** - Get feedback, adjust priorities
2. **Create GitHub issues** - One issue per task with acceptance criteria
3. **Assign owners** - Designate who implements each phase
4. **Set up tracking** - Project board to monitor progress
5. **Begin Phase 1** - Start with schema updates (low risk, foundational)
6. **Daily standups** - Check progress, unblock issues
7. **Weekly demos** - Show progress on sample documents

---

## Questions for Discussion

1. **Chunking Strategy**: Prefer component-based or hybrid? (Hybrid = component-aware but allow fixed-size within components)
2. **Table Summarization**: Should we summarize in parsing or enrichment? (Parsing is cleaner but slower)
3. **Vision Cleaning**: Worth the cost/latency? (Test on sample docs first)
4. **Context Prefix Format**: Current format good or need refinement?
5. **Hierarchical Indexing**: Implement now or after basic improvements?

---

## Conclusion

This implementation plan addresses all your feedback:

1. ✅ **Component context preserved** through metadata and chunking strategy
2. ✅ **Tables get summaries** via parsing stage enhancement
3. ✅ **Cleaned text first** in new chunking architecture
4. ✅ **Contextual retrieval** via contextualized text and metadata
5. ✅ **Document-level context** via hierarchical summarization
6. ✅ **Visual context in cleaning** via pixmap parameter

The plan is structured, detailed, and ready for implementation. It sets up your pipeline for advanced RAG patterns (hierarchical, contextual, context-aware) that will excel at document classification tasks.

**Estimated Total Effort**: 20-25 working days (1 engineer) or 10-15 days (2 engineers working in parallel)

**Recommended Start Date**: Immediately (before observability integration)

Ready to begin implementation? Let me know if you need clarification on any tasks or want to adjust priorities!

