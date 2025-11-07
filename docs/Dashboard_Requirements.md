# Dashboard Requirements (v0)

This addendum describes the developer dashboard that accompanies the RAG pipeline.
It captures the **manual testing goals**, **scope**, and **acceptance criteria** for the UI features added in v0.

---

## Goals

1. **Traceability** – show the inputs/outputs of ingestion, extraction, chunking, and enrichment for a single document without leaving FastAPI.
2. **Observability** – surface the same structured data that the services emit so engineers can reason about pagination, chunk offsets, cleaning profiles, vectors, and metadata.
3. **Manual QA workflow** – provide a low-friction way to upload fixtures (e.g., `tests/test_document.pdf`) and visually compare the processed structure with the original file.

---

## Functional Requirements

| Area | Requirement |
| --- | --- |
| Upload & execution | Upload PDF, DOCX, PPT/PPTX via `/dashboard`. File runs through the same `PipelineRunner` used by the API. |
| Stage inspection | Dashboard renders one numbered card per stage (ingestion, extraction, cleaning, chunking, enrichment, vectorization) with the serialized payload (page previews, chunk counts, cleaning stats, vectors) and duration metadata. |
| Document preview | Uploaded artifact is stored under `static/uploads/` and embedded next to stage data for side-by-side review. |
| Run history | Maintain at least the last 10 runs via the persistence layer so regressions can be compared quickly even after reloads. |
| Extensibility | When new stages (cleaning, vectorization, etc.) are added to `PipelineRunner`, they automatically appear in the dashboard with no additional frontend code. |

---

## Non-Functional Requirements

1. **In-app experience** – dashboard ships with FastAPI (no extra Node/React project). Uses Jinja + a lightweight vanilla-JS `fetch` helper for partial updates (no HTMX dependency).
2. **Lightweight assets** – Tailwind CDN only; no build tooling. Static uploads live under `static/uploads/`.
3. **Parity with logs** – data shown in the UI mirrors the structured events emitted from the services so CLI users and UI users share the same vocabulary.

---

## Acceptance Criteria

1. Visiting `/dashboard` displays the upload form, recent runs, and (when available) the most recent run trace.
2. Uploading `tests/test_document.pdf` produces:
   - A visible iframe preview of the PDF.
   - Stage cards (numbered 1-6) showing the JSON payload for ingestion, extraction, cleaning, chunking, enrichment, and vectorization.
   - Chunk tables showing page numbers, chunk IDs, offsets, and text excerpts.
3. The dashboard handles unsupported files gracefully (400 error rendered by the client-side fetch helper).
4. Developers can restart the server and the dashboard still functions (run history resets as designed).
5. Documentation (README + this file) explains how to operate the dashboard and how future stages should emit data to it.
6. A configurable `PIPELINE_STAGE_LATENCY` environment variable allows teams to simulate slow stages and validate the dashboard’s loading states, while the UI polls the run endpoint to surface stage completions in near real-time. `RUN_ARTIFACTS_DIR` controls where JSON artifacts are written locally before swapping in a cloud store.

---

## Future Enhancements

- Add cleaning/vectorization stages once implemented in the domain layer.
- Persist run history (e.g., SQLite) for long-lived comparisons.
- Overlay timing data and service metrics using the observability hooks.
- Provide toggles for viewing cleaned vs. raw text, alternate cleaning profiles, and high-dimensional vector previews.
