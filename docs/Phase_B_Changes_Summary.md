# Phase B: What Changed - Quick Visual Summary

**Branch**: `observability` | **Status**: ✅ Ready for Testing

---

## 🎯 Priority 1: Langfuse Tracing

### Files Changed:

```
requirements.txt                          +2 packages (langfuse, llama-index-callbacks-langfuse)
src/app/config.py                         +4 settings (lines 106-109)
src/app/container.py                      +28 lines (Langfuse handler setup, lines 84-111)
src/app/services/pipeline_runner.py       +260 lines (tracing logic, lines 73-405)
src/app/observability/langfuse_handler.py +NEW FILE (custom handler)
docs/Langfuse_User_Guide.md               +NEW FILE (comprehensive guide)
README.md                                  +18 lines (setup instructions, lines 229-247)
```

### Environment Variables Added:

```bash
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

### What You'll See:

#### In Server Logs:
```
Langfuse callback handler initialized
Langfuse trace created: https://us.cloud.langfuse.com/trace/abc123...
```

#### In Langfuse UI:
```
📊 Traces
└─ document_pipeline::test.pdf [session: doc-123]
   ├─ 🔹 stage::ingestion       (0.2s) → file_size, checksum
   ├─ 🔹 stage::parsing          (5.3s) → pages, components, 📷 pixmaps
   │  └─ LLM calls (auto-traced by LlamaIndex)
   ├─ 🔹 stage::cleaning         (3.1s) → segments_flagged, profile
   │  └─ LLM calls
   ├─ 🔹 stage::chunking         (0.4s) → chunks_created, strategy
   ├─ 🔹 stage::enrichment       (2.8s) → document_summary, contexts
   │  └─ LLM calls
   └─ 🔹 stage::vectorization    (1.2s) → embeddings, model, dimension
```

---

## 🎯 Priority 2: Human-in-the-Loop Review UI

### Files Changed:

```
src/app/api/routers.py                         +90 lines (3 new endpoints, lines 62-149)
src/app/api/dashboard.py                       +NEW ROUTE /dashboard/review
src/app/api/templates/review.html              +NEW FILE (381 lines, full UI)
src/app/api/templates/dashboard.html           +2 lines (Review button link)
src/app/persistence/adapters/document_filesystem.py  +50 lines (approve/edit methods)
tests/test_dashboard.py                        +60 lines (HITL workflow tests)
tests/test_document_repository.py              +40 lines (persistence tests)
```

### New API Endpoints:

```http
GET  /documents/{document_id}/segments-for-review
     → Returns: {flagged_segments: [...]}

POST /segments/{segment_id}/approve
     → Body: {document_id: "..."}
     → Marks segment as reviewed

PUT  /segments/{segment_id}/edit
     → Body: {document_id: "...", corrected_text: "..."}
     → Saves correction + marks reviewed
```

### What You'll See:

#### In Dashboard:
```
📄 Documents List
└─ ✅ test_document.pdf (completed)
   └─ [Review] ← Click this button (green badge)
```

#### In Review Page:
```
🔍 Segment Review Queue

Select Document: [test_document.pdf ▼]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Segment seg_1
   Page 3 · Chunk abc123...

   ⚠️ Review Reason: Contains contact information that may need verification

   ┌─────────────────────────────────────┐
   │ Contact us at: support@example.com  │
   │ Phone: 555-1234                     │
   └─────────────────────────────────────┘

   [✓ Approve]  [✏️ Edit]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### After Clicking Edit:
```
┌─────────────────────────────────────────┐
│ Edit Segment                            │
├─────────────────────────────────────────┤
│ Corrected Text:                         │
│ ┌─────────────────────────────────────┐ │
│ │ Contact: support@example.com        │ │
│ │ Tel: +1-555-1234                    │ │
│ └─────────────────────────────────────┘ │
│                                         │
│           [Cancel]  [💾 Save]          │
└─────────────────────────────────────────┘
```

---

## 📊 Architecture Overview

### Langfuse Integration:

```
┌────────────────┐
│  FastAPI App   │
└────────┬───────┘
         │
         ▼
┌────────────────────────┐
│ PipelineRunner.run()   │ ← Creates root trace
├────────────────────────┤
│ • trace name            │
│ • session_id            │
│ • document metadata     │
└────────┬───────────────┘
         │
         ├──▶ 🔹 Ingestion span
         ├──▶ 🔹 Parsing span (+ pixmap previews)
         ├──▶ 🔹 Cleaning span
         ├──▶ 🔹 Chunking span
         ├──▶ 🔹 Enrichment span
         └──▶ 🔹 Vectorization span
         
All LLM calls auto-traced by LlamaIndex callback ⚡
```

### HITL Review Flow:

```
┌──────────────┐
│ 📄 Document   │
│  Uploaded    │
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│ CleaningService      │ ← LLM flags segments
│  needs_review=true   │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Dashboard                    │
│ [Review] button appears      │
└──────┬───────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│ Review UI                       │
│ GET /segments-for-review        │
│  → Show queue                   │
└──────┬──────────────────────────┘
       │
       ├──▶ [Approve] → POST /approve → reviewed=true
       │
       └──▶ [Edit] → PUT /edit → corrected_text + reviewed=true
              │
              ▼
       ┌─────────────────────┐
       │ FileSystemRepository │ ← Persists to disk
       │ artifacts/documents/ │
       └─────────────────────┘
```

---

## 🧪 Quick Test Commands

### Start Server:
```bash
cd /Users/bigo/Projects/TCS-onboard/RAG_pipeline_worker
uvicorn src.app.main:app --reload
```

### Run Tests:
```bash
# All tests
pytest

# HITL review tests only
pytest tests/test_dashboard.py::test_segments_review_endpoints_flow -v
pytest tests/test_document_repository.py -k segment -v

# Architecture compliance (should pass)
pytest tests/test_architecture.py -v
```

### Manual Testing:
```bash
# 1. Open dashboard
open http://localhost:8000/dashboard

# 2. Upload test document
# Use: tests/doc_short_noisy.pdf (has segments that should be flagged)

# 3. Click "Review" button when processing completes

# 4. Open Langfuse UI
open https://us.cloud.langfuse.com/trace/<trace_id>
```

---

## 📈 Metrics & Observability

### What Langfuse Captures:

| Metric | Location | Example |
|--------|----------|---------|
| **Pipeline Duration** | Root trace | 12.8 seconds |
| **Stage Breakdown** | Child spans | Parsing: 5.3s, Cleaning: 3.1s |
| **LLM Token Usage** | Nested observations | 2,450 tokens total |
| **LLM Costs** | Automatic tracking | $0.042 per run |
| **Component Counts** | Metadata | 15 components (8 text, 5 tables, 2 images) |
| **Segments Flagged** | Cleaning metadata | 3 segments need review |
| **Chunks Created** | Chunking metadata | 28 chunks (component strategy) |

### What HITL Captures:

| Metric | Location | Example |
|--------|----------|---------|
| **Segments Flagged** | Document metadata | `"needs_review": true` × 3 |
| **Review Actions** | Document metadata | `"reviewed": true`, `"reviewed_at": "..."` |
| **Corrections** | Document metadata | `"corrected_text": "..."` (original preserved) |
| **Review History** | Document metadata | `"review_history": [...]` |

---

## 🎨 UI Preview

### Dashboard with Review Button:

```
┌────────────────────────────────────────────────────────┐
│ 📊 Pipeline Dashboard                                  │
├────────────────────────────────────────────────────────┤
│                                                         │
│ Recent Runs:                                           │
│                                                         │
│ ┌─────────────────────────────────────────────────┐   │
│ │ ✅ test_document.pdf                            │   │
│ │ Status: completed                               │   │
│ │ Duration: 12.8s                                 │   │
│ │                                       [Review 🔍]│   │
│ └─────────────────────────────────────────────────┘   │
│                                                         │
└────────────────────────────────────────────────────────┘
```

### Review Queue UI:

```
┌────────────────────────────────────────────────────────┐
│ 🔍 Segments Requiring Review                          │
├────────────────────────────────────────────────────────┤
│                                                         │
│ Select Document: [test_document.pdf            ▼]     │
│                                                         │
│ ┌───────────────────────────────────────────────────┐ │
│ │ 📝 Segment seg_1                    Page 3        │ │
│ │ ─────────────────────────────────────────────     │ │
│ │ ⚠️ Contains contact information                   │ │
│ │                                                   │ │
│ │ ┌───────────────────────────────────────────┐   │ │
│ │ │ Contact: support@example.com              │   │ │
│ │ │ Phone: 555-1234                           │   │ │
│ │ └───────────────────────────────────────────┘   │ │
│ │                                                   │ │
│ │ [✓ Approve]  [✏️ Edit]                           │ │
│ └───────────────────────────────────────────────────┘ │
│                                                         │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Completion Checklist

### Before Testing:
- [x] All code changes committed
- [x] Langfuse credentials in `.env`
- [x] Server starts without errors
- [x] Tests pass: `pytest tests/test_dashboard.py tests/test_document_repository.py`

### During Testing:
- [ ] Upload document via dashboard
- [ ] Check Langfuse UI for trace
- [ ] Verify all 6 stages present
- [ ] Check pixmap previews in parsing span
- [ ] Click "Review" button on completed document
- [ ] Approve a segment
- [ ] Edit a segment
- [ ] Verify changes persist

### After Testing:
- [ ] Mark Priority 1 & 2 as complete in TODO
- [ ] Document any issues found
- [ ] Plan Priority 3 (prompt tuning) and Priority 4 (Ragas)

---

**Ready to test? See: `Observability_Phase_B_Testing_Guide.md` for detailed step-by-step instructions!**

