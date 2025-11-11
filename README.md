# Document Parsing Pipeline for RAG

This repository contains a FastAPI application that ingests office documents, runs them through a deterministic document-processing pipeline, and surfaces the intermediate artifacts for Retrieval Augmented Generation (RAG) workflows. The codebase is intentionally modular: domain models capture immutable document state, services orchestrate pipeline stages, ports expose the seams for adapters, and a dashboard makes every stage observable.

---

## Pipeline Overview

The pipeline executes the following stages in order. Each service returns a new `Document` instance and emits structured telemetry through the `ObservabilityRecorder` port.

| Stage | Service (`src/app/services`) | Resulting `Document.status` | Key Outputs |
| --- | --- | --- | --- |
| Ingestion | `IngestionService` | `ingested` | Copies raw bytes to `artifacts/ingestion/<document_id>/`, records checksum + content metadata |
| Parsing | `ParsingService` | `parsed` | Uses `DocumentParser` adapters (pdfplumber-backed PDF parser plus DOCX/PPT stubs) to create `Page` models, falling back to placeholder text if parsing fails |
| Cleaning | `CleaningService` | `cleaned` | Normalizes whitespace, records `cleaning_report` plus `cleaning_metadata_by_page` so chunking can attach cleaning metadata |
| Chunking | `ChunkingService` | `chunked` | Slices each page into overlapping `Chunk` objects, keeps raw text + cleaned text slices, attaches cleaning metadata |
| Enrichment | `EnrichmentService` | `enriched` | Invokes the injected `SummaryGenerator` (default `LLMSummaryAdapter` stub) to title/summary chunks and stitch a lightweight document summary |
| Vectorization | `VectorService` | `vectorized` | Generates deterministic placeholder vectors per chunk, stores sample vectors and vector dimension on document metadata |

`PipelineRunner` coordinates these services, records per-stage duration/details, and `PipelineRunManager` persists progress snapshots so the dashboard can stream updates while a run is executing asynchronously.

### Visual Pipeline Flow

```mermaid
flowchart LR
    subgraph Runner["Pipeline Runner"]
        direction LR
        Upload([Upload API or Dashboard]) --> Ingestion
        Ingestion --> Parsing
        Parsing --> Cleaning
        Cleaning --> Chunking
        Chunking --> Enrichment
        Enrichment --> Vectorization
    end

    Ingestion -->|raw copy| RawArtifacts[(Ingestion Storage)]
    Vectorization -->|final snapshot| DocumentStore[(Document Store)]
    DocumentStore --> DashboardViews[Dashboard Views]

    Runner -.stage events.-> RunManager[[Pipeline Run Manager]]
    RunManager --> RunTimeline[(Run Timeline Artifacts)]
    RunTimeline --> DashboardViews

    subgraph Telemetry["Structured Telemetry"]
        Observability[[Observability Recorder]]
    end

    Ingestion -.-> Observability
    Parsing -.-> Observability
    Cleaning -.-> Observability
    Chunking -.-> Observability
    Enrichment -.-> Observability
    Vectorization -.-> Observability
```

_Figure 1: End-to-end pipeline flow showing how uploads move through services, storage targets, observability, and dashboard-facing artifacts._

---

## Repository Structure

```
RAG_pipeline_worker/
├── AGENTS.md
├── README.md
├── requirements.txt
├── artifacts/                 # File-system persistence targets (configurable via env vars)
│   ├── documents/
│   ├── ingestion/
│   └── runs/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── Parsing_Service_Implementation_Guide.md
│   ├── LLM_Integration_Implementation_Guide.md
│   └── research/
│       └── README.md
├── src/
│   └── app/
│       ├── api/
│       │   ├── dashboard.py            # Manual QA dashboard + upload form
│       │   ├── routers.py              # REST API (upload/list/get)
│       │   ├── task_scheduler.py       # BackgroundTasks adapter
│       │   └── templates/
│       ├── adapters/                   # Parser + LLM summary stubs
│       ├── application/
│       │   ├── interfaces.py           # Ports (DocumentParser, SummaryGenerator, ObservabilityRecorder, TaskScheduler)
│       │   └── use_cases/              # Upload/List/Get use cases
│       ├── config.py
│       ├── container.py                # Composition root wiring concrete adapters
│       ├── domain/                     # Immutable models + pipeline run dataclasses
│       ├── observability/              # LoggingObservabilityRecorder adapter
│       ├── persistence/                # Repository ports + filesystem adapters
│       ├── services/                   # Pipeline stage implementations
│       └── main.py                     # FastAPI entry point
├── static/
│   └── uploads/                        # Dashboard document previews
├── tests/
│   ├── test_architecture.py            # Import guardrails (hexagonal compliance)
│   ├── test_dashboard.py               # Dashboard flow and background runs
│   ├── test_end_to_end.py              # Upload/list/get API round-trip
│   ├── test_pdf_parser.py              # pdfplumber adapter tests
│   ├── test_persistence_filesystem.py  # Repository adapters
│   ├── test_run_manager.py
│   ├── test_services.py
│   └── test_use_cases.py
└── tmp/                                # Scratch space for manual experiments
```

---

## Core Modules

- **Domain models (`src/app/domain`)** – `Document`, `Page`, `Chunk`, and `Metadata` capture every transformation applied to an upload. Helper methods like `add_page` and `add_chunk` always return copies, preserving immutability.
- **Application layer (`src/app/application`)** – Protocols in `interfaces.py` define ports for document parsers, summary generators, schedulers, and observability recorders. Use cases (Upload/List/Get) translate HTTP concerns into pipeline invocations.
- **Services (`src/app/services`)** – Each class encapsulates one stage of the pipeline and depends strictly on domain models + ports. `PipelineRunner` strings the stages together, and `PipelineRunManager` handles persistence plus async execution via the injected `TaskScheduler`.
- **Adapters (`src/app/adapters`)** – Contain infrastructure-specific code: `PdfParserAdapter` wraps `pdfplumber`, the DOCX/PPT parsers are still placeholders, and `LLMSummaryAdapter` is a lightweight stub that truncates text. Swapping in production-ready adapters happens without changing services.
- **Persistence (`src/app/persistence`)** – Defines repository ports plus filesystem-backed adapters:
  - `FileSystemIngestionRepository` stores raw uploads;
  - `FileSystemDocumentRepository` persists processed `Document` snapshots;
  - `FileSystemPipelineRunRepository` captures per-stage JSON artifacts for the dashboard.
- **Observability (`src/app/observability/logger.py`)** – Default adapter that writes structured JSON payloads to Python logging. Inject a different `ObservabilityRecorder` to push traces elsewhere.
- **Composition (`src/app/container.py`)** – Centralizes dependency injection, reads environment variables (`RUN_ARTIFACTS_DIR`, `INGESTION_STORAGE_DIR`, `DOCUMENT_STORAGE_DIR`, `PIPELINE_STAGE_LATENCY`), and exposes fully-wired use cases to the FastAPI routes.

---

## FastAPI Surface

- `POST /upload` – Accepts a single file and processes it synchronously by calling `UploadDocumentUseCase`. Returns the final `Document` with pages, chunks, metadata, and vectors.
- `GET /documents` – Lists all stored documents via `ListDocumentsUseCase`.
- `GET /documents/{doc_id}` – Fetches a single processed document.
- `GET /dashboard` – Renders the manual test harness. Uploads kick off `PipelineRunManager.run_async`, and the UI polls `/dashboard/runs/{run_id}/fragment` to stream stage details, chunk previews, metrics, and duration data. File previews are served from `static/uploads/`.

The dashboard uses only server-side templates (Jinja2) plus a small amount of vanilla JS to refresh runs. No external frontend build tooling is required.

---

## Data & Artifacts

All persistence paths default to the `artifacts/` directory inside the repo but can be overridden via environment variables:

- `RUN_ARTIFACTS_DIR` → timeline JSON for each pipeline run (consumed by the dashboard)
- `INGESTION_STORAGE_DIR` → immutable upload copies + checksums
- `DOCUMENT_STORAGE_DIR` → processed document snapshots read by the API/use cases
- `PIPELINE_STAGE_LATENCY` → optional float (seconds) used to simulate slow stages and make dashboard updates easier to see

The dashboard stores uploaded files under `static/uploads/` for inline previews. Clean up the `artifacts/` and `static/uploads/` directories periodically during local development if disk space becomes an issue.

---

## Configuration

`src/app/config.py` exposes typed configuration models for every integration point (LLM, embeddings, chunking, vector stores, and prompt files). Override values via environment variables or a local `.env` file using Pydantic's nested syntax. Examples:

```bash
LLM__ENABLED=true
LLM__PROVIDER=openai
LLM__MODEL=gpt-4o-mini
CHUNKING__CHUNK_SIZE=768
VECTOR_STORE__PERSIST_DIR=artifacts/vector_store_dev
```

When `LLM__ENABLED=true`, the new `configure_llama_index()` bootstrapper wires these settings into `llama_index.core.Settings`, keeping framework imports confined to the adapters layer.

---

## Getting Started

### Install Dependencies

This project now targets **Python 3.10+** so we can rely on modern typing syntax (`str | None`, `list[str]`, etc.). Recreate your virtualenv with a 3.10 interpreter (or higher) before installing dependencies:

```bash
rm -rf .venv                   # optional: only if you are upgrading
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

If your system default `python3` already points to 3.10+, feel free to substitute it for `python3.10`.

### Run the API + Dashboard

```bash
PIPELINE_STAGE_LATENCY=0.05 uvicorn src.app.main:app --reload
```

- Visit `http://localhost:8000/docs` for the OpenAPI explorer.
- Visit `http://localhost:8000/dashboard` to run the manual QA workflow. Upload `tests/test_document.pdf` to see every stage artifact, chunk breakdown, and duration metadata.

### Run the Tests

```bash
pytest              # full suite
pytest tests/test_architecture.py  # enforce hexagonal import rules
```

- `tests/test_services.py` covers every pipeline stage plus immutability guarantees.
- `tests/test_dashboard.py` exercises the background-run workflow.
- `tests/test_pdf_parser.py` asserts that `pdfplumber` parsing works and errors are handled gracefully.

---

## Working Guidelines

- Keep the hexagonal boundaries intact: domain models never import adapters, services depend only on ports, and adapters hook into protocols defined under `application/interfaces.py`.
- Preserve immutability by returning new model instances (`model_copy`) from services, and mirror this in tests whenever new behavior is introduced.
- When adding new adapters or services, wire them through `container.py`, emit observability events, and update the relevant documentation under `docs/`.
- Architecture tests (`tests/test_architecture.py`) must stay green before merging any change.

---

## References

- `docs/ARCHITECTURE.md` – Hexagonal architecture guardrails and dependency flow
- `docs/Parsing_Service_Implementation_Guide.md` – Deep dive into the parsing stage and parser adapters
- `docs/LLM_Integration_Implementation_Guide.md` – How the `SummaryGenerator` port enables LLM-backed enrichment
- `AGENTS.md` – Specification-driven development workflow for research → planning → implementation
