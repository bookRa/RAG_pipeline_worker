# RAG Pipeline: Complete TODO List

This document provides a prioritized TODO list for the RAG pipeline. Based on feedback, we're now prioritizing **pipeline architectural improvements** before observability integration.

---

## ⚠️ UPDATED PRIORITY: Pipeline Improvements First

**New Order**:
1. **Phase A: Pipeline Improvements** (3-4 weeks) - Implement contextual retrieval, component-aware chunking, hierarchical RAG
2. **Phase B: Observability Integration** (1-2 weeks) - Add Langfuse and Ragas once pipeline is optimized

**Rationale**: Need clean architecture with component metadata before adding observability. This ensures we're tracing the *right* pipeline, not a flawed one.

---

## Phase A: Pipeline Improvements (PRIORITY 1) - Next 3-4 Weeks

**See `Pipeline_Improvements_Implementation_Plan.md` for detailed specifications.**

### Week 1: Schema and Parsing Enhancements

#### A1. Update Data Schemas [2-3 days]
- [ ] Add `table_summary` field to `ParsedTableComponent`
- [ ] Add component context fields to `Metadata` (component_id, component_type, component_description, component_summary)
- [ ] Add hierarchical context fields to `Metadata` (document_title, document_summary, page_summary, section_heading)
- [ ] Add `contextualized_text` field to `Chunk`
- [ ] Update domain models with helper methods
- [ ] Run tests to ensure backward compatibility

**Files**: `src/app/parsing/schemas.py`, `src/app/domain/models.py`

---

#### A2. Add Table Summarization to Parsing [2-3 days]
- [ ] Update parsing prompts to request table summaries
  - Edit `docs/prompts/parsing/system.md`
  - Edit `docs/prompts/parsing/user.md`
  - Add examples of good table summaries
- [ ] Verify `ImageAwareParsingAdapter` extracts table summaries
- [ ] Test on documents with tables (verify summary quality)
- [ ] Add unit tests for table summarization

**Files**: `docs/prompts/parsing/*.md`, `src/app/adapters/llama_index/parsing_adapter.py`

---

#### A3. Add Page-Level Summaries [1-2 days]
- [ ] Update parsing prompts to request `page_summary`
- [ ] Verify parsing adapter extracts page summaries
- [ ] Test on multi-page documents
- [ ] Validate summary quality (should describe page role in document)

**Files**: `docs/prompts/parsing/user.md`

---

### Week 2: Cleaning and Chunking Overhaul

#### A4. Add Visual Context to Cleaning [2-3 days]
- [ ] Add `pixmap_path` parameter to `CleaningAdapter.clean_page()`
- [ ] Implement vision-based cleaning method
- [ ] Update cleaning prompts for visual context
  - Edit `docs/prompts/cleaning/system.md`
  - Add instructions for using visual layout
- [ ] Update `CleaningService` to pass pixmaps
- [ ] Test with/without vision (compare quality)
- [ ] Make vision optional via config

**Files**: `src/app/adapters/llama_index/cleaning_adapter.py`, `src/app/services/cleaning_service.py`, `docs/prompts/cleaning/system.md`

---

#### A5. Implement Component-Based Chunking [5-7 days]
- [ ] Create new chunking algorithm:
  - Iterate through `parsed_pages[N].components`
  - Group small components (< threshold tokens)
  - Split large components (> max tokens) at sentence boundaries
  - Create one chunk per component (or component group)
- [ ] Extract cleaned text for component chunks
  - Map components to cleaned_text positions
  - Extract corresponding slices
- [ ] Attach component metadata to chunks
  - Set `component_id`, `component_type`, `component_order`
  - Add `component_description` for images
  - Add `component_summary` for tables
- [ ] Add configuration for chunking strategy ("component", "hybrid", "fixed")
- [ ] Test on documents with mixed content (text, tables, images)
- [ ] Compare with fixed-size chunking (manual QA)
- [ ] Write comprehensive unit tests

**Files**: `src/app/services/chunking_service.py`, `src/app/config.py`

**Critical**: This is the biggest change. Allocate extra time for testing and iteration.

---

### Week 3: Enrichment and Vectorization

#### A6. Implement Document-Level Summarization [2-3 days]
- [ ] Create `_generate_document_summary()` method in `EnrichmentService`
  - Collect all page summaries
  - Pass to LLM for synthesis
  - Generate 3-4 sentence comprehensive summary
- [ ] Update `enrich()` to call document summarization first
- [ ] Test document summary quality on multi-page docs
- [ ] Ensure summary covers all pages (not just first page)

**Files**: `src/app/services/enrichment_service.py`

---

#### A7. Add Hierarchical Context to Chunk Enrichment [2-3 days]
- [ ] Extract section headings from parsed pages
- [ ] Pass document summary, page summary, section heading to chunk enrichment
- [ ] Update chunk summarization to use hierarchical context
- [ ] Generate contextualized text with context prefix:
  - Format: `[Document: X | Page: Y | Section: Z | Type: table]`
  - Prepend to chunk text before embedding
- [ ] Store original text separately for generation
- [ ] Test contextualized text format and quality

**Files**: `src/app/services/enrichment_service.py`

---

#### A8. Create LLM Summary Adapter [1 day]
- [ ] Create `LLMSummaryAdapter` implementing `SummaryGenerator`
- [ ] Load summarization prompt from `docs/prompts/summarization/system.md`
- [ ] Handle short text (< 50 chars) - return as-is
- [ ] Test summary generation quality
- [ ] Wire into `EnrichmentService` via container

**Files**: `src/app/adapters/llama_index/summary_adapter.py` (new), `src/app/container.py`

---

#### A9. Update Vectorization for Contextual Retrieval [1-2 days]
- [ ] Modify `VectorService` to embed `contextualized_text` (not `cleaned_text`)
- [ ] Ensure metadata fields are preserved in vector storage
  - `component_type`, `component_description`, `component_summary`
  - `document_title`, `document_summary`, `page_summary`
- [ ] Store both contextualized_text (embedded) and cleaned_text (for generation)
- [ ] Test vector generation with new metadata

**Files**: `src/app/services/vector_service.py`

---

### Week 4: Integration and Testing

#### A10. Update Container and Configuration [1-2 days]
- [ ] Wire `LLMSummaryAdapter` into container
- [ ] Add configuration settings:
  - `CHUNKING_STRATEGY` (component/hybrid/fixed)
  - `COMPONENT_MERGE_THRESHOLD` (default 100)
  - `MAX_COMPONENT_TOKENS` (default 500)
  - `USE_VISION_CLEANING` (default True)
  - `USE_LLM_SUMMARIZATION` (default True)
- [ ] Update `CleaningService` instantiation (vision parameter)
- [ ] Update `ChunkingService` instantiation (strategy parameters)
- [ ] Update `EnrichmentService` instantiation (summary generator)

**Files**: `src/app/container.py`, `src/app/config.py`

---

#### A11. Comprehensive Testing [3-4 days]
- [ ] **Unit Tests**:
  - Component chunking preserves tables
  - Component chunking merges small components
  - Component chunking splits large components
  - Component metadata preserved in chunks
  - Cleaned text extraction for components
  - Table summarization
  - Contextualized text generation
- [ ] **Integration Tests**:
  - Full pipeline with component chunking
  - Table summaries end-to-end
  - Document summary quality
  - Metadata preservation through all stages
- [ ] **Manual QA**:
  - Test on blueprint documents (tables, images, diagrams)
  - Test on manuals (mixed content)
  - Test on multi-section documents (headings)
  - Verify chunk boundaries make sense
  - Inspect contextualized text format
  - Check metadata completeness in final document.json

**Files**: `tests/test_chunking_component_aware.py` (new), `tests/test_end_to_end_hierarchical.py` (new)

---

#### A12. Documentation and Knowledge Transfer [1 day]
- [ ] Update README with new pipeline architecture
- [ ] Document chunking strategies and when to use each
- [ ] Document component metadata fields and their purpose
- [ ] Add examples of contextualized text
- [ ] Create troubleshooting guide
- [ ] Demo new pipeline to team

**Files**: `README.md`, `docs/ARCHITECTURE.md`

---

## Phase B: Observability Integration (PRIORITY 2) - After Pipeline Improvements

**Note**: Start this phase only after Phase A is complete and tested.

### Week 5: Immediate Actions (High Priority)

### 1. Fix Document Summary Generation [2-4 hours]

**Problem**: Document summary shows only first page content (280 char truncation of concatenated chunk summaries)

**Tasks**:
- [ ] Create document-level summarization method in `EnrichmentService`
- [ ] Modify enrichment to collect page summaries from `parsed_pages` metadata
- [ ] Update summarization prompt for document-level synthesis
- [ ] Test on sample documents and verify summary quality

**Files**:
- `src/app/services/enrichment_service.py`
- `docs/prompts/summarization/system.md`

---

### 2. Enable LLM Summarization for Chunks [1-2 hours]

**Problem**: Chunks use simple truncation instead of LLM-generated summaries

**Tasks**:
- [ ] Create `LLMSummaryAdapter` implementing `SummaryGenerator` interface
- [ ] Load and use summarization prompt from `docs/prompts/summarization/system.md`
- [ ] Wire adapter into `EnrichmentService` via `container.py`
- [ ] Test chunk summaries are now 2-sentence LLM outputs

**Files**:
- `src/app/adapters/llama_index/summary_adapter.py` (new)
- `src/app/container.py`

---

### 3. Add Page-Level Summaries to Parser [2-3 hours]

**Problem**: Parser doesn't provide high-level overview of page content

**Tasks**:
- [ ] Add `page_summary: str | None` field to `ParsedPage` schema
- [ ] Update parsing user prompt to include `page_summary` in output schema
- [ ] Modify enrichment to use page summaries for document summary
- [ ] Test parser produces page summaries from vision LLM

**Files**:
- `src/app/parsing/schemas.py`
- `docs/prompts/parsing/user.md`
- `src/app/services/enrichment_service.py`

---

## Short-term Enhancements (1-2 weeks)

### 4. Integrate Langfuse for LLM Tracing [4-6 hours]

**Benefits**:
- Full visibility into LLM calls (prompts, responses, tokens, costs)
- Performance analysis (identify slow calls)
- Prompt versioning and A/B testing
- Links between pipeline stages and LLM operations

**Tasks**:
- [ ] Install `langfuse` and `llama-index-callbacks-langfuse` packages
- [ ] Add Langfuse configuration to `Settings` (public key, secret key, host, enable flag)
- [ ] Initialize `LlamaIndexCallbackHandler` in `AppContainer` if enabled
- [ ] Set global callback manager for LlamaIndex
- [ ] Add custom trace context in `PipelineRunner.run()` for document processing
- [ ] Add spans for each pipeline stage (parsing, cleaning, chunking, enrichment, vectorization)
- [ ] Test traces appear in Langfuse UI with correct hierarchy
- [ ] Document setup in README for team

**Files**:
- `requirements.txt`
- `src/app/config.py`
- `src/app/container.py`
- `src/app/services/pipeline_runner.py`
- `README.md` (update with Langfuse setup instructions)

**Environment Variables**:
```bash
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=https://cloud.langfuse.com  # or self-hosted URL
```

---

### 5. Build Human-in-the-Loop Review UI [1 week]

**Benefits**:
- Surface segments flagged by cleaning LLM
- Allow human review and correction
- Collect feedback for prompt tuning and model fine-tuning

**Tasks**:

**Backend**:
- [ ] Add `GET /documents/{document_id}/segments-for-review` endpoint
  - Extract segments with `needs_review=true` from chunk metadata
  - Return list with segment text, rationale, location info
- [ ] Add `POST /segments/{segment_id}/approve` endpoint
  - Mark segment as reviewed
  - Update document metadata
- [ ] Add `PUT /segments/{segment_id}/edit` endpoint
  - Accept corrected text from human reviewer
  - Store correction (possibly in separate corrections table)
  - Link correction back to original segment

**Frontend**:
- [ ] Create review dashboard page (`api/templates/review.html`)
- [ ] Show queue of segments needing review
- [ ] Display segment text, rationale, and context (page number, surrounding text)
- [ ] Add approve/edit buttons
- [ ] Implement edit modal with text area and save button
- [ ] Add filter/search by document, page, rationale type

**Testing**:
- [ ] Test with documents that have flagged segments
- [ ] Verify review actions update document state
- [ ] Test correction storage and retrieval

**Files**:
- `src/app/api/routers.py` (review endpoints)
- `src/app/api/templates/review.html` (new)
- `src/app/api/templates/dashboard.html` (add link to review page)
- `src/app/persistence/ports.py` (add methods for segment operations)

---

### 6. Tune Cleaning Prompts for Better Review Flags [2-3 hours]

**Benefits**:
- More accurate flagging of segments that actually need review
- Reduce false positives (flagging things that don't need review)
- Provide clearer rationales for why review is needed

**Tasks**:
- [ ] Review current flagged segments in sample documents
- [ ] Identify false positives (wrongly flagged) and false negatives (should be flagged)
- [ ] Update cleaning system prompt with specific criteria:
  - Contact information (phone, email, address)
  - Version numbers and dates
  - Technical specs with measurements
  - Legal disclaimers
  - Acronyms without definitions
  - Long/complex sentences
  - Low OCR confidence areas
- [ ] Test on sample documents and measure improvement
- [ ] Document review criteria for team

**Files**:
- `docs/prompts/cleaning/system.md`

**Evaluation**:
```python
# Create test set of segments with ground truth labels
# Measure precision and recall of review flags
# Target: >90% precision, >80% recall
```

---

## Medium-term Improvements (1 month)

### 7. Integrate Ragas for Quality Evaluation [1-2 weeks]

**Benefits**:
- Quantitative quality metrics (faithfulness, relevance, precision, recall)
- Automated quality regression testing
- Compare prompt versions objectively
- Identify low-quality documents/chunks

**Tasks**:

**Evaluation Dataset**:
- [ ] Create eval dataset with question/answer pairs based on sample documents
  - Questions: User queries about document content
  - Ground truth: Correct answers from documents
  - Contexts: Retrieved chunks (simulate retrieval)
  - Answers: Generated responses (simulate generation)
- [ ] Aim for 20-50 question/answer pairs to start
- [ ] Store in `tests/evaluation/rag_eval_dataset.py`

**Ragas Integration**:
- [ ] Install `ragas` package
- [ ] Create test functions using Ragas metrics:
  - `faithfulness`: Response only uses source content
  - `answer_relevancy`: Response is relevant to question
  - `context_precision`: Retrieved chunks are relevant
  - `context_recall`: All relevant chunks retrieved
- [ ] Set minimum quality thresholds (e.g., faithfulness > 0.90)
- [ ] Run evaluation in CI on every PR

**Langfuse Integration**:
- [ ] Fetch traces from Langfuse programmatically
- [ ] Score traces with Ragas metrics using `langfuse_evaluate()`
- [ ] View scores in Langfuse UI alongside traces
- [ ] Set up monitoring dashboard for quality trends

**Files**:
- `requirements.txt` (add ragas)
- `tests/evaluation/rag_eval_dataset.py` (new)
- `tests/evaluation/test_rag_quality.py` (new)
- `.github/workflows/rag_evaluation.yml` (new, CI integration)

---

### 8. Implement Semantic Chunking [1 week]

**Benefits**:
- Better chunk boundaries based on content structure
- Improved retrieval relevance
- Preserve semantic coherence within chunks

**Tasks**:
- [ ] Research LlamaIndex chunking strategies:
  - `SemanticSplitterNodeParser` (splits on embedding similarity)
  - `SentenceSplitter` (splits on sentence boundaries)
  - Component-based chunking (one chunk per component)
- [ ] Implement chosen strategy in `ChunkingService`
- [ ] Make strategy configurable (fixed-size vs. semantic vs. component-based)
- [ ] Compare retrieval quality with fixed-size chunking (using Ragas)
- [ ] Document trade-offs for team

**Files**:
- `src/app/services/chunking_service.py`
- `src/app/container.py`
- `docs/Chunking_Strategy_Comparison.md` (new, document findings)

**Evaluation**:
- [ ] Run Ragas evaluation with both strategies
- [ ] Measure context precision and recall
- [ ] Measure latency impact (semantic chunking may be slower)

---

### 9. Add Query-time Observability [1 week]

**Benefits**:
- Trace user queries end-to-end (retrieval → ranking → generation)
- Identify slow retrieval operations
- Track query-level quality metrics
- Link user feedback to specific traces

**Tasks**:

**Query Endpoints** (if not already built):
- [ ] Create `POST /query` endpoint for RAG queries
  - Accept user question + optional filters
  - Retrieve relevant chunks from vector store
  - Generate response using LLM + retrieved context
  - Return response + source chunks

**Observability**:
- [ ] Add Langfuse trace for each query:
  - Input: User question
  - Metadata: User ID, session ID, timestamp
- [ ] Add spans for each operation:
  - `embedding`: Convert query to vector
  - `retrieval`: Search vector store
  - `ranking`: Re-rank results (if applicable)
  - `generation`: Generate response with LLM
- [ ] Capture costs and latency per operation
- [ ] Link back to source document traces (via document ID)

**Quality Scoring**:
- [ ] Score query traces with Ragas metrics in real-time or batch
- [ ] Store scores in Langfuse
- [ ] Alert on low scores (e.g., faithfulness < 0.8)

**Files**:
- `src/app/api/routers.py` (query endpoints)
- `src/app/services/retrieval_service.py` (new, retrieval logic)
- `src/app/services/generation_service.py` (new, response generation)

---

## Long-term Vision (3-6 months)

### 10. Prompt Version Management

- [ ] Migrate prompts from files to Langfuse prompt management
- [ ] Tag traces with prompt version
- [ ] A/B test prompt variations automatically
- [ ] Measure quality impact per prompt version

---

### 11. Continuous Quality Monitoring

- [ ] Run Ragas evaluation on sample of production queries daily
- [ ] Build quality dashboard showing trends over time
- [ ] Set up alerts for quality degradation (e.g., faithfulness drops below threshold)
- [ ] Automated reports to team (weekly quality summary)

---

### 12. Fine-tuning Pipeline

- [ ] Collect human corrections from HITL review
- [ ] Build fine-tuning dataset from corrections
- [ ] Fine-tune smaller model for cleaning task
- [ ] Compare fine-tuned model vs. GPT-4o-mini (cost, quality, latency)
- [ ] Iterate on model improvements

---

### 13. Multi-tenant Observability

- [ ] Add user/tenant ID to all traces
- [ ] Per-tenant cost tracking
- [ ] Per-tenant quality metrics
- [ ] Tenant-specific prompt versions
- [ ] Isolated debugging per tenant

---

## Success Metrics

Track these metrics to measure observability improvements:

| Metric | Baseline (Current) | Target |
|--------|-------------------|--------|
| Document summary accuracy | Poor (first page only) | >90% capture full document |
| Chunk summary quality | N/A (using truncation) | Faithfulness >0.90 |
| LLM call visibility | 0% (no tracing) | 100% traced in Langfuse |
| HITL review coverage | 0% (no workflow) | 100% flagged segments surfaced |
| Quality regression detection | Manual/None | Automated Ragas in CI |
| Time to debug LLM issues | Hours (manual log inspection) | Minutes (Langfuse trace drill-down) |
| Cost per document | Unknown | Tracked per stage, per document |

---

## Team Assignments (Example)

- **Week 1**: Engineer A (Fix summaries), Engineer B (Langfuse integration)
- **Week 2**: Engineer A (HITL UI), Engineer B (Ragas evaluation)
- **Week 3**: Engineer A (Semantic chunking), Engineer B (Query observability)
- **Month 2-3**: Continuous improvement, fine-tuning, monitoring

---

## Next Steps

1. Review this TODO with team in planning meeting
2. Assign owners and deadlines for each item
3. Create Jira/GitHub issues for tracking
4. Start with immediate actions (highest ROI)
5. Schedule weekly check-ins on observability progress
6. Update this doc as tasks are completed

---

**Questions or blockers?** Contact the AI agent for implementation guidance!

