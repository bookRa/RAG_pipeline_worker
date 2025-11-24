# ⚡ Quick Testing Checklist - Phase B

**Time**: ~10 minutes | **Goal**: Verify Langfuse tracing + HITL review work

---

## 🚀 Setup (1 min)

```bash
# 1. Start server (if not running)
cd /Users/bigo/Projects/TCS-onboard/RAG_pipeline_worker
uvicorn src.app.main:app --reload

# 2. Verify Langfuse enabled in terminal output:
#    ✅ Look for: "Langfuse callback handler initialized"

# 3. Have Langfuse UI open:
open https://us.cloud.langfuse.com
```

---

## ✅ Test 1: Langfuse Tracing (3 min)

### Steps:
1. **Upload document**:
   - Open: http://localhost:8000/dashboard
   - Upload: `tests/doc_short_clean.pdf`
   - Wait for "✅ completed"

2. **Check server logs**:
   - Look for: `Langfuse trace created: https://...`
   - Copy trace URL

3. **Open Langfuse UI** → Traces:
   - ✅ See: `document_pipeline::doc_short_clean.pdf`
   - ✅ Click trace → 6 child spans visible:
     - stage::ingestion
     - stage::parsing (should have 📷 pixmap previews)
     - stage::cleaning
     - stage::chunking
     - stage::enrichment
     - stage::vectorization
   - ✅ Click parsing span → Check "Media" tab for page images
   - ✅ Each span has metadata (click span → Metadata tab)

### Pass Criteria:
- [ ] Trace appears in Langfuse < 10 seconds
- [ ] All 6 stages present
- [ ] Pixmap previews visible in parsing span
- [ ] Metadata attached (chunk counts, etc.)

---

## ✅ Test 2: HITL Review Workflow (5 min)

### Steps:
1. **Upload noisy document**:
   - Dashboard: http://localhost:8000/dashboard
   - Upload: `tests/doc_short_noisy.pdf` (has OCR errors)
   - Wait for completion

2. **Check for Review button**:
   - ✅ Green [Review] badge appears on completed document
   - Click it

3. **Review Queue** (you should see):
   - ✅ Document dropdown pre-selected
   - ✅ Segment cards with:
     - Original text (dark box)
     - Review rationale (yellow box)
     - [Approve] and [Edit] buttons

4. **Test Approve**:
   - Click [Approve] on one segment
   - ✅ Segment disappears from queue

5. **Test Edit**:
   - Click [Edit] on another segment
   - ✅ Modal opens with text area
   - Make a small change
   - Click [Save]
   - ✅ Modal closes, segment disappears

6. **Verify Persistence**:
   - Refresh page (`Cmd+R` or `Ctrl+R`)
   - ✅ Reviewed segments don't reappear
   - ✅ Only unreviewed segments remain

### Pass Criteria:
- [ ] Review button appears on completed documents
- [ ] Flagged segments visible in queue
- [ ] Approve removes segment
- [ ] Edit saves correction and removes segment
- [ ] Changes persist after refresh

---

## 🎯 Bonus: Combined Test (1 min)

1. **Check Langfuse for noisy document**:
   - Go to Traces → Find `doc_short_noisy.pdf` trace
   - Click on `stage::cleaning` span
   - Check Metadata tab
   - ✅ Should see: `"segments_flagged": N` (where N > 0)

2. **Cross-reference**:
   - Number in Langfuse metadata should match segments in review queue

---

## 🐛 Troubleshooting

### No traces in Langfuse?
```bash
# Check .env file:
grep ENABLE_LANGFUSE .env  # Should be: true
grep LANGFUSE_PUBLIC_KEY .env  # Should have: pk-lf-...

# Check server logs for:
"Langfuse callback handler initialized"  # ✅ Good
"Failed to initialize Langfuse"  # ❌ Check keys
```

### No Review button?
```bash
# Try a document known to have noise:
# - tests/doc_short_noisy.pdf
# - tests/doc_welding.pdf

# Check if segments were flagged:
cat artifacts/documents/<doc_id>.json | grep needs_review
# Should see: "needs_review": true
```

### Segments not disappearing after review?
```bash
# Check browser console (F12) for errors
# Check server logs for 200 OK responses:
# POST /segments/{id}/approve -> 200
# PUT /segments/{id}/edit -> 200
```

---

## ✨ Expected Results

### Langfuse UI Trace:
```
document_pipeline::doc_short_clean.pdf
├─ stage::ingestion (0.2s)
├─ stage::parsing (5.3s) ← 📷 Has pixmap previews
│  └─ LLM calls (auto-traced)
├─ stage::cleaning (3.1s)
├─ stage::chunking (0.4s)
├─ stage::enrichment (2.8s)
└─ stage::vectorization (1.2s)
```

### Review Queue:
```
📝 Segment seg_1 (Page 3)
⚠️ Contains contact information
┌─────────────────────────┐
│ Contact: ...            │
└─────────────────────────┘
[✓ Approve]  [✏️ Edit]
```

---

## 📊 Success = All Checked ✅

- [ ] Server starts with "Langfuse callback handler initialized"
- [ ] Trace appears in Langfuse UI with 6 stages
- [ ] Pixmap previews visible in parsing span
- [ ] Metadata present on each span
- [ ] Review button appears on completed documents
- [ ] Segments visible in review queue
- [ ] Approve action works
- [ ] Edit action works
- [ ] Changes persist after refresh

---

**All checked? 🎉 Phase B implementation verified!**

Next: See `Observability_Integration_TODO.md` for Priority 3 (Prompt Tuning) and Priority 4 (Ragas Evaluation)

