# RAG Pipeline: Observability Integration Roadmap

This document outlines the roadmap for comprehensive observability, tracing, and evaluation in the RAG pipeline.

---

## ✅ Completed

### Pipeline Architecture Improvements
✅ **Component-Aware Chunking**: Tables, images, and text blocks are preserved as semantic units  
✅ **Table Summarization**: LLM-generated summaries for all table components  
✅ **Page Summarization**: LLM-generated summaries for each page  
✅ **Document-Level Summarization**: Generated from page summaries  
✅ **Contextualized Retrieval**: Anthropic's contextual retrieval pattern implemented  
✅ **Hierarchical Context**: Document → Page → Section → Component metadata attached to chunks  
✅ **LLM Integration**: Vision parsing, text cleaning, summarization via LlamaIndex adapters  
✅ **Structured Outputs**: Using `as_structured_llm()` for reliable JSON extraction

### Batch Processing & Observability
✅ **Batch Processing**: Multi-document concurrent processing with rate limiting  
✅ **Batch Observability**: Clean logging with Langfuse integration  
✅ **Multi-Level Parallelism**: Document, page, and pixmap-level parallel processing  
✅ **Real-Time Progress**: Server-Sent Events (SSE) for batch monitoring  
✅ **Langfuse Integration**: Basic tracing with batch_id correlation  

---

## 🎯 In Progress

## Priority 1: Enhanced Langfuse Integration

**Status**: Basic integration complete for batch processing  
**Remaining Work**: Extend to single-document pipeline

**Benefits**:
- Full visibility into LLM calls (prompts, responses, tokens, costs)
- Performance analysis (identify slow calls)
- Prompt versioning and A/B testing
- Links between pipeline stages and LLM operations

**Tasks**:
- [x] Install `langfuse` and `llama-index-callbacks-langfuse` packages
- [x] Add Langfuse configuration to `Settings`
- [x] Implement batch observability with Langfuse tracing
- [ ] Extend Langfuse tracing to single-document pipeline
- [ ] Add detailed LLM call metrics (token counts, costs per stage)
- [ ] Implement prompt versioning with Langfuse
- [ ] Add custom trace metadata for filtering and analysis

**Configuration**:
```bash
LANGFUSE__ENABLED=true
LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=https://cloud.langfuse.com
```

---

---

## 📋 Planned

## Priority 2: Human-in-the-Loop Review UI

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

## Priority 3: Tune Cleaning Prompts for Better Review Flags

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

## Priority 4: Integrate Ragas for Quality Evaluation

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

---

## 🔮 Future Enhancements

## Semantic Chunking Experiments

**Note**: Component-aware chunking already provides semantic boundaries. This would be experimental/comparative work.

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

## Query-time Observability

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

## Long-Term Vision

### Prompt Version Management

- [ ] Migrate prompts from files to Langfuse prompt management
- [ ] Tag traces with prompt version
- [ ] A/B test prompt variations automatically
- [ ] Measure quality impact per prompt version

---

### Continuous Quality Monitoring

- [ ] Run Ragas evaluation on sample of production queries daily
- [ ] Build quality dashboard showing trends over time
- [ ] Set up alerts for quality degradation (e.g., faithfulness drops below threshold)
- [ ] Automated reports to team (weekly quality summary)

---

### Fine-tuning Pipeline

- [ ] Collect human corrections from HITL review
- [ ] Build fine-tuning dataset from corrections
- [ ] Fine-tune smaller model for cleaning task
- [ ] Compare fine-tuned model vs. GPT-4o-mini (cost, quality, latency)
- [ ] Iterate on model improvements

---

### Multi-tenant Observability

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

## Next Steps

1. Extend Langfuse integration to single-document pipeline
2. Build HITL review UI for flagged segments
3. Integrate Ragas for automated quality evaluation
4. Implement query-time observability for RAG queries
5. Add prompt versioning and A/B testing capabilities

