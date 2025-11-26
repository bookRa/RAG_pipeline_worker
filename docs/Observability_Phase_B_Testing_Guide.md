# Observability Phase B: Implementation Summary & Testing Guide

**Date**: November 24, 2025  
**Status**: ✅ **Priority 1 & 2 Complete** - Ready for Manual Testing  
**Branch**: `observability`

---

## 📋 What Changed

### ✅ Priority 1: LLM Tracing with Langfuse [COMPLETE]

**Implementation Status**: All coding tasks complete, awaiting manual verification in Langfuse UI.

#### Key Changes:

1. **Configuration (`src/app/config.py`)**
   - Added `enable_langfuse`, `langfuse_public_key`, `langfuse_secret_key`, `langfuse_host` settings
   - Environment variables: `ENABLE_LANGFUSE`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`

2. **Container Initialization (`src/app/container.py`)**
   - Lines 84-111: Langfuse handler initialization
   - Integrates with LlamaIndex global callback manager
   - Graceful fallback if Langfuse packages not installed

3. **Pipeline Tracing (`src/app/services/pipeline_runner.py`)**
   - Lines 73-142: Root trace creation for each document pipeline run
   - Lines 150-405: Individual spans for each pipeline stage:
     - **Ingestion**: File upload and validation
     - **Parsing**: LLM vision parsing with pixmap previews
     - **Cleaning**: Text normalization and segment flagging
     - **Chunking**: Component-aware chunk generation
     - **Enrichment**: Document/chunk summarization
     - **Vectorization**: Embedding generation
   - Pixmap preview attachments (first 2 pages by default, configurable via `LANGFUSE_PIXMAP_PREVIEW_LIMIT`)
   - Session grouping via `session_id` (links all traces in a pipeline run)

4. **Observability Handler (`src/app/observability/langfuse_handler.py`)**
   - Custom `PipelineLangfuseHandler` extending LlamaIndex's Langfuse callback
   - Supports custom trace parameters (name, session_id, metadata, tags)
   - Thread-safe trace storage

5. **Dependencies (`requirements.txt`)**
   - Added: `langfuse>=2.0.0`
   - Added: `llama-index-callbacks-langfuse>=0.3.0`

6. **Documentation**
   - `README.md` § "Langfuse Tracing" (lines 229-247): Setup instructions
   - `docs/Langfuse_User_Guide.md`: Comprehensive usage guide

#### What Gets Traced:

- ✅ Full pipeline runs (root trace per document)
- ✅ Each stage as child spans with timing
- ✅ LLM calls (prompts, responses, tokens, costs) via LlamaIndex callbacks
- ✅ Metadata: chunk counts, component types, cleaning profiles, summaries
- ✅ Pixmap previews attached to parsing spans (multi-modal support)
- ✅ Session grouping (all traces for a run appear together)
- ✅ Trace IDs logged to console for correlation

---

### ✅ Priority 2: Human-in-the-Loop Review UI [COMPLETE]

**Implementation Status**: Full HITL workflow implemented and tested.

#### Key Changes:

1. **Backend Endpoints (`src/app/api/routers.py`)**
   
   **GET `/documents/{document_id}/segments-for-review`** (Lines 62-104)
   - Extracts all segments where `needs_review=true` from cleaning metadata
   - Returns: `document_id`, `page_number`, `chunk_id`, `segment_id`, `text`, `rationale`
   - Links segments back to source pages and chunks
   
   **POST `/segments/{segment_id}/approve`** (Lines 107-126)
   - Marks segment as reviewed/approved
   - Updates document metadata in repository
   - Returns approval confirmation
   
   **PUT `/segments/{segment_id}/edit`** (Lines 129-149)
   - Accepts corrected text from human reviewer
   - Stores correction in document (preserves original for audit)
   - Marks segment as reviewed
   - Returns edit confirmation

2. **Repository Methods (`src/app/persistence/adapters/document_filesystem.py`)**
   - `approve_segment()`: Updates segment review status in metadata
   - `edit_segment()`: Applies corrections and marks as reviewed
   - Both methods persist changes to disk immediately

3. **Frontend Review Dashboard (`src/app/api/templates/review.html`)**
   - **Document Selector**: Dropdown with all processed documents
   - **Segments Queue**: Shows all flagged segments with:
     - Segment text (formatted, pre-wrapped)
     - Review rationale (highlighted in yellow/amber)
     - Page number and chunk ID
     - Approve/Edit action buttons
   - **Edit Modal**: Text area for corrections with save/cancel
   - **URL State**: Preserves document selection in URL params (`?document_id=...`)
   - **Real-time Updates**: Queue updates as segments are reviewed
   - **Empty State**: Clean UI when no segments need review

4. **Dashboard Integration (`src/app/api/templates/dashboard.html`)**
   - Review button on each completed document (Line 41-42)
   - Direct link to review page with document pre-selected
   - Visual indicator for documents with flagged segments

5. **Dashboard Route (`src/app/api/dashboard.py`)**
   - `GET /dashboard/review` (Line 123+): Serves review UI template

#### Workflow:

```
1. Document Processing → Cleaning LLM flags segments with `needs_review=true`
2. Dashboard → "Review" button appears on completed documents
3. Review Page → Queue shows all flagged segments
4. Reviewer Actions:
   - ✅ **Approve**: Marks segment as reviewed (no changes)
   - ✏️ **Edit**: Saves corrected text + marks as reviewed
5. Queue Updates → Segment disappears from queue immediately
6. Storage → Changes persist to document JSON on disk
```

#### Test Coverage:

- ✅ `tests/test_dashboard.py::test_segments_review_endpoints_flow`
- ✅ `tests/test_document_repository.py::test_approve_segment_updates_metadata`
- ✅ `tests/test_document_repository.py::test_edit_segment_updates_text_and_page`

---

## 🧪 Manual Testing Instructions

### Prerequisites

1. **Start the server** (if not already running):
   ```bash
   cd /Users/bigo/Projects/TCS-onboard/RAG_pipeline_worker
   source .venv/bin/activate  # Activate your virtualenv
   uvicorn src.app.main:app --reload
   ```

2. **Verify Langfuse is enabled** in `.env`:
   ```bash
   grep LANGFUSE .env
   ```
   You should see:
   ```
   ENABLE_LANGFUSE=true
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://us.cloud.langfuse.com
   ```

---

### Test 1: Langfuse Tracing End-to-End

**Goal**: Verify that pipeline runs create traces in Langfuse with correct hierarchy and metadata.

#### Steps:

1. **Upload a test document via dashboard**:
   - Open browser: `http://localhost:8000/dashboard`
   - Upload a PDF (e.g., `tests/doc_short_clean.pdf` or any test PDF)
   - Wait for processing to complete (watch status progress)
   - Note the **document ID** from the completed run

2. **Check console logs for trace ID**:
   - In your terminal where the server is running, look for:
     ```
     Langfuse trace created: https://us.cloud.langfuse.com/trace/<trace_id>
     ```
   - Click the URL or copy the trace ID

3. **Open Langfuse UI**:
   - Navigate to: https://us.cloud.langfuse.com
   - Log in with your Langfuse account
   - Go to: **Traces** section

4. **Verify trace structure**:
   
   ✅ **Root Trace**: Should see `document_pipeline::<filename>`
   - Click on the trace to open details
   
   ✅ **Session Grouping**: 
   - Check that `session_id` matches the document/run ID
   - All traces for the same run should be grouped together
   
   ✅ **Child Spans** (should appear in hierarchy):
   ```
   └─ document_pipeline::test.pdf
      ├─ stage::ingestion
      ├─ stage::parsing
      │  └─ (LLM vision calls appear here automatically via LlamaIndex)
      ├─ stage::cleaning
      │  └─ (LLM cleaning calls appear here automatically)
      ├─ stage::chunking
      ├─ stage::enrichment
      │  └─ (LLM summarization calls appear here)
      └─ stage::vectorization
   ```
   
   ✅ **Metadata** (click on each span to view):
   - **Ingestion**: `file_size_bytes`, `content_type`, `checksum`
   - **Parsing**: `pages_parsed`, `total_components`, `pixmap_count`
   - **Cleaning**: `cleaning_profile`, `segments_flagged`, `pages_processed`
   - **Chunking**: `strategy`, `chunks_created`, `component_distribution`
   - **Enrichment**: `document_summary` (truncated), `chunks_contextualized`
   - **Vectorization**: `chunks_embedded`, `embedding_model`, `vector_dimension`
   
   ✅ **Pixmap Previews** (parsing span):
   - Click on **Parsing** span
   - Scroll to "Media" or "Attachments" section
   - Should see first 2 pages as image previews
   
   ✅ **LLM Observations** (automatic via LlamaIndex):
   - Within parsing/cleaning/enrichment spans, drill into nested LLM calls
   - Check: prompt, response, token counts, costs, latency

5. **Check Timing**:
   - Each span should have start/end times
   - Total trace duration = sum of all stages
   - Identify bottlenecks (which stage took longest?)

6. **Check Costs** (if available):
   - Langfuse automatically tracks token usage and costs for OpenAI calls
   - Navigate to: **Dashboard** → **Costs** to see aggregated spend

#### Expected Results:

- ✅ Trace appears in Langfuse UI within ~10 seconds of upload
- ✅ All 6 stages present as child spans
- ✅ LLM calls nested within relevant stages
- ✅ Metadata attached to each span
- ✅ Pixmap previews visible in parsing span
- ✅ Session ID links all traces from same run
- ✅ Console logs include clickable trace URL

#### Troubleshooting:

- **No traces appear**: 
  - Check `ENABLE_LANGFUSE=true` in `.env`
  - Verify API keys are correct
  - Check server logs for "Langfuse callback handler initialized"
  
- **Traces missing metadata**:
  - Check individual span details in Langfuse UI
  - Metadata should be in "Metadata" tab of each span
  
- **No pixmap previews**:
  - Check `CHUNKING__INCLUDE_IMAGES=true` in `.env`
  - Verify `artifacts/pixmaps/<doc_id>/` directory has PNG files
  - Increase preview limit: `LANGFUSE_PIXMAP_PREVIEW_LIMIT=5` (default is 2)

---

### Test 2: Human-in-the-Loop Review Workflow

**Goal**: Verify that flagged segments can be reviewed, approved, and edited via the dashboard.

#### Steps:

1. **Upload a document that triggers segment flagging**:
   - Use a "noisy" PDF: `tests/doc_short_noisy.pdf` (has OCR errors)
   - Or any document with contact info, measurements, acronyms, etc.
   - Upload via: `http://localhost:8000/dashboard`
   - Wait for processing to complete

2. **Check for flagged segments**:
   - On the completed run, look for a **"Review"** button (green badge)
   - If no button appears, the cleaning LLM didn't flag any segments
   - Try a different document or check cleaning prompt settings

3. **Open Review Queue**:
   - Click the **"Review"** button on a completed document
   - You should be redirected to: `http://localhost:8000/dashboard/review?document_id=<doc_id>`

4. **Verify Review UI**:
   
   ✅ **Document Selector**:
   - Dropdown should show all processed documents
   - Current document should be pre-selected
   
   ✅ **Segments List**:
   - Should show cards for each flagged segment
   - Each card displays:
     - Segment ID and page number
     - Original text (in dark code-like box)
     - Review rationale (yellow highlighted box explaining why it was flagged)
     - Two action buttons: **Approve** and **Edit**

5. **Test Approve Action**:
   - Click **"Approve"** on one segment
   - Confirm the prompt
   - ✅ Segment should disappear from queue immediately
   - ✅ Console should show: `POST /segments/<segment_id>/approve` → `200 OK`

6. **Test Edit Action**:
   - Click **"Edit"** on another segment
   - ✅ Modal should open with text area pre-filled with current text
   - Make corrections to the text
   - Click **"Save"**
   - ✅ Modal should close
   - ✅ Segment should disappear from queue
   - ✅ Console should show: `PUT /segments/<segment_id>/edit` → `200 OK`

7. **Verify Persistence**:
   - Refresh the review page
   - ✅ Previously reviewed segments should NOT reappear
   - ✅ Queue should only show remaining unreviewedsegments

8. **Check Document Storage**:
   - Open: `artifacts/documents/<doc_id>.json`
   - Search for the segment IDs you reviewed
   - ✅ Should see `"reviewed": true` on approved segments
   - ✅ Should see `"corrected_text": "..."` on edited segments
   - ✅ Original text should be preserved alongside corrections

9. **Test Empty Queue**:
   - Review all remaining segments
   - ✅ When queue is empty, should see:
     ```
     ✓
     No segments require review
     All segments in this document have been reviewed or none were flagged.
     ```

#### Expected Results:

- ✅ Review button appears on documents with flagged segments
- ✅ Review page loads with correct document pre-selected
- ✅ All flagged segments visible with text and rationale
- ✅ Approve action removes segment from queue
- ✅ Edit modal opens, accepts corrections, persists changes
- ✅ Queue updates in real-time as segments are reviewed
- ✅ Changes persist across page refreshes
- ✅ Empty state displays when queue is cleared

#### Troubleshooting:

- **No "Review" button on documents**:
  - Check if `cleaning_metadata_by_page` exists in `artifacts/documents/<doc_id>.json`
  - Look for segments with `"needs_review": true`
  - Cleaning LLM may not flag segments on very clean documents
  - Try `doc_short_noisy.pdf` which should trigger flags
  
- **Segments not disappearing after review**:
  - Check browser console for JavaScript errors
  - Verify API responses: should return `200 OK`
  - Check server logs for errors
  
- **Changes not persisting**:
  - Verify write permissions on `artifacts/documents/` directory
  - Check repository logs for save errors

---

### Test 3: End-to-End Combined Workflow

**Goal**: Verify Langfuse tracing and HITL review work together.

#### Steps:

1. **Upload a noisy document** (e.g., `tests/doc_short_noisy.pdf`)
2. **Check Langfuse trace**:
   - Verify cleaning span shows `segments_flagged > 0` in metadata
3. **Review flagged segments**:
   - Click "Review" button
   - Approve or edit segments
4. **Check Langfuse again**:
   - Note: Review actions are NOT currently traced (future enhancement)
   - But pipeline trace should show which documents have segments needing review

---

## 📊 Success Criteria

### Priority 1: Langfuse Tracing

- ✅ All pipeline runs create traces in Langfuse UI
- ✅ 6 stages appear as child spans with correct hierarchy
- ✅ LLM calls nested within stages (parsing, cleaning, enrichment)
- ✅ Metadata attached to each span
- ✅ Pixmap previews visible in parsing span
- ✅ Session IDs group traces correctly
- ✅ Trace URLs logged to console
- ✅ No errors or warnings in server logs

### Priority 2: HITL Review UI

- ✅ Flagged segments appear in review queue
- ✅ Approve action marks segments as reviewed
- ✅ Edit action saves corrections and marks as reviewed
- ✅ Queue updates in real-time
- ✅ Changes persist to disk
- ✅ Empty state displays correctly
- ✅ All tests pass: `pytest tests/test_dashboard.py tests/test_document_repository.py -k review`

---

## 🔜 Next Steps

### Remaining Work from Observability TODO:

1. **Priority 1 Follow-up**:
   - [ ] Design observability abstraction layer (adapter pattern) to swap Langfuse for other providers
   - [ ] Manual verification complete in Langfuse UI (this testing guide)

2. **Priority 2 Follow-up**:
   - [ ] Add filter/search by document, page, rationale type (enhancement)

3. **Priority 3**: Tune Cleaning Prompts for Better Review Flags [2-3 hours]
   - Review current flagged segments and adjust prompt criteria
   - Measure precision/recall of review flags

4. **Priority 4**: Integrate Ragas for Quality Evaluation [1-2 weeks]
   - Create eval dataset with Q&A pairs
   - Implement Ragas metrics (faithfulness, relevance, precision, recall)
   - Score traces in Langfuse

---

## 🐛 Known Issues / Limitations

1. **Langfuse Pixmap Previews**:
   - Limited to first 2 pages by default (configurable)
   - Large pixmaps may be resized to meet Langfuse size limits

2. **HITL Review**:
   - No bulk approve/edit actions (must review one at a time)
   - No search/filter by rationale type yet
   - Review actions themselves are not traced in Langfuse (future enhancement)

3. **Session Grouping**:
   - Multiple uploads in quick succession may share session IDs
   - Use unique `run_id` for better isolation

---

## 📞 Support

**Questions or blockers?** 
- Check implementation files referenced above
- Review `docs/Langfuse_User_Guide.md` for detailed Langfuse usage
- Contact AI agent for troubleshooting assistance

---

**Happy Testing! 🎉**

