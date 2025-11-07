# Hexagonal Refactor Plan

This checklist translates the audit findings into concrete remediation steps.
Each section describes the current issue, the plan of attack, and the tests
we will rely on to prove the refactor is complete.

---

## 1. Introduce a Composition Root & Dependency Injection (Status: Complete)
- **Problem:** `PipelineRunner`, services, and adapters are instantiated at
  import time inside API modules (`src/app/api/routers.py`,
  `src/app/api/dashboard.py`). `PipelineRunManager` imports
  `fastapi.BackgroundTasks`, so the domain layer depends on the web framework.
- **Plan of Attack:**
  - Create an application container (e.g., `src/app/container.py`) that wires
    services, repositories, adapters, and observability ports using settings.
  - Expose FastAPI dependencies (or a simple factory) that returns the shared
    container so routers obtain services via injection instead of globals.
  - Move background-task orchestration into an adapter or an application
    service that the container provides, keeping `PipelineRunManager` unaware of
    FastAPI.
  - Ensure stage latency configuration, repository paths, etc. are only defined
    once inside the container.
- **Test Plan:**
  - Unit-test the container/factory to ensure it returns singleton instances
    where expected.
  - Update API route tests to verify dependency overrides work and that uploads
    still complete end-to-end (`tests/test_end_to_end.py`).

## 2. Preserve Raw Ingestion Artifacts & Cleaning Contracts (Status: Complete)
- **Problem:** `IngestionService` annotates metadata but never persists the
  raw file. `CleaningService` overwrites `page.text` and `chunk.text` in place,
  violating the requirement to keep immutable raw extraction output.
- **Plan of Attack:**
  - Define an `IngestionRepository` port responsible for storing uploads and
    returning stable file references (filesystem adapter first, S3 later).
  - Update ingestion to call this repository and record the storage key in
    document metadata.
  - Refactor cleaning to emit cleaned payloads alongside raw ones (e.g.,
    `chunk.metadata.extra["raw_text"]` vs. `"cleaned_text"`, or a dedicated
    `CleanedChunk` model). Ensure the diff/hash metadata described in the spec
    is stored.
- **Test Plan:**
  - Add unit tests for the ingestion repository adapter (write/read round-trip).
  - Extend `tests/test_services.py` to assert raw text remains accessible after
    cleaning and that cleaning metadata captures token counts + diff hashes.

## 3. Use Parser & LLM Adapters via Ports ✅
- **What we fixed:** Introduced the `DocumentParser` and `SummaryGenerator`
  ports (`src/app/application/interfaces.py`) and rewired PDF/DOCX/PPT/LLM
  adapters to implement them. `ExtractionService` now resolves the correct
  parser (falling back to placeholder text only when necessary) and can pull
  bytes from either the current request or the persisted ingestion artifact.
  `EnrichmentService` accepts a `SummaryGenerator`, so the LLM adapter is
  injected instead of imported directly. The container wires all adapters up.
- **Tests in place:** `tests/test_services.py` now includes parser-path and
  summary-generator regression tests to prove that (a) extraction honors the
  injected parser and stored raw file path, and (b) enrichment defers to the
  summary generator. Additional adapter-specific tests are still optional, but
  the service-level tests provide coverage of the integration.

## 4. Unify Document Persistence Across API & Dashboard ✅
- **What we fixed:** Added a `DocumentRepository` port with a filesystem
  adapter (`artifacts/documents/`). The container now exposes a shared
  repository instance, API routes use it instead of an in-memory dict, and
  `PipelineRunManager` saves each completed document so dashboard-triggered
  runs land in the same store. Both `/upload` and `/dashboard` therefore read
  from the identical backing directory.
- **Tests in place:** `tests/test_document_repository.py` verifies save/get/list
  semantics, and the existing end-to-end/API tests implicitly exercise the new
  wiring (documents uploaded anywhere can now be fetched via `/documents`).

## 5. Decouple Observability from Domain Logic ✅
- **What we fixed:** Added an `ObservabilityRecorder` port plus two adapters
  (logging + no-op). Every service and the `PipelineRunner` now accept an
  injected recorder instead of importing `log_event`, and the container wires a
  single `LoggingObservabilityRecorder` instance through the stack. Swapping in
  OpenTelemetry or other exporters no longer requires touching domain code.
- **Tests in place:** `tests/test_services.py` defines a stub recorder and
  asserts that ingestion emits an event and the pipeline runner records
  `pipeline_complete`. This ensures the new port stays exercised in unit tests.

## 6. Stabilize Vector Generation
- **Problem:** `VectorService` seeds Python’s salted `hash()` per chunk text,
  so different processes produce different vectors. That breaks determinism for
  stored artifacts and tests.
- **Plan of Attack:**
  - Replace the `hash()` usage with a stable digest (e.g., SHA-256 of
    `chunk.id` or text) before seeding `Random`.
  - Record the vector “version”/dimension in metadata so downstream systems
    know which embedding contract produced the values.
- **Test Plan:**
  - Add a regression test that runs vectorization twice on identical documents
    and asserts vectors are identical.
  - Optionally add a snapshot test for stored `vector_samples`.

## 7. Expand Test Coverage for Infrastructure Layers
- **Problem:** No tests exist for persistence adapters, run manager orchestration,
  or dashboard endpoints, so regressions in these critical hexagonal pieces go
  unnoticed.
- **Plan of Attack:**
  - Add pytest suites for:
    - `FileSystemPipelineRunRepository` (start/update/complete/fail flows).
    - `PipelineRunManager` (progress callback & failure handling) using fakes.
    - Dashboard routes (`/dashboard`, `/dashboard/upload`, polling endpoint)
      with temporary artifact directories.
  - Integrate these tests into CI to guard subsequent refactors.
- **Test Plan:**
  - Use `tmp_path` fixtures to isolate filesystem writes.
  - Mock background tasks to run synchronously so tests remain fast.
  - Assert rendered templates include stage data after a simulated run.

---

Tracking completion of each checklist item will ensure the codebase truly
matches the modular, hexagonal architecture promised in the specification.
