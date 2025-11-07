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

## 4. Unify Document Persistence Across API & Dashboard
- **Problem:** REST endpoints keep documents in a module-level dict, while the
  dashboard persists runs via `FileSystemPipelineRunRepository`. The two user
  paths never see each other’s artifacts.
- **Plan of Attack:**
  - Extract a `DocumentRepository` port (list/get/save) and back it with the
    same filesystem artifacts used by the dashboard, or wrap the existing run
    repository.
  - Update API routes to store and fetch via the repository, eliminating the
    in-memory `DOCUMENT_STORE`.
  - Ensure dashboard history queries read from the same source, so `/upload`
    and `/dashboard` reflect the same data.
- **Test Plan:**
  - Add repository tests for list/get persistence semantics.
  - Expand the E2E FastAPI test to assert that documents uploaded via `/upload`
    appear in the dashboard repository (can be indirect by verifying the
    repository contents after a run).

## 5. Decouple Observability from Domain Logic
- **Problem:** Every service imports `log_event` directly, tying domain logic
  to the logging adapter.
- **Plan of Attack:**
  - Define an `ObservabilityPort` (e.g., `record_event(stage, details)`).
  - Inject an implementation via the container. The current
    `observability.logger` becomes one adapter; future OpenTelemetry exporters
    can implement the same interface.
  - Update services and `PipelineRunner` to depend on the port instead of the
    module-level function.
- **Test Plan:**
  - Provide a fake observability adapter in unit tests and assert that each
    service emits the expected events (e.g., ingestion records document id).
  - Optionally add an integration test ensuring the real adapter forwards to
    Python logging.

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
