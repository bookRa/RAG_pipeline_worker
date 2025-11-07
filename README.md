# Document Extraction Pipeline for RAG – v0 Skeleton

Welcome to the first iteration (v0) of our document-processing pipeline for Retrieval Augmented Generation (RAG).  
This repository is specification driven—the code serves the specification, not the other way around.  
It provides a modular scaffold that team members can extend independently while maintaining a single source of truth for the data model and module interfaces.

---

## Overview

This pipeline ingests documents (PDFs, DOCX, PPT) and turns them into structured, chunked data suitable for downstream RAG applications.  
Although the current implementation contains only stub functions, the architecture follows hexagonal (ports and adapters) principles.  
Business logic lives in a clear domain layer, while technology-specific concerns (e.g., file parsing, LLM calls, or storage) are encapsulated in adapters.  
A FastAPI app exposes endpoints for uploading documents and inspecting intermediate results.  
A test harness with pytest and sample tests demonstrates how each module can be exercised in isolation and end-to-end.

---

## Why RAG Pipelines Need Structure

Retrieval-augmented generation systems perform better when the source material is broken into meaningful chunks, each enriched with metadata.  
Chunking improves retrieval accuracy and response quality by preserving context and avoiding information overload.  
After chunking the document, adding metadata—such as unique IDs, titles, summaries, and keywords—helps support filtering and full-text search.  
Cleaning text by normalizing case, removing stop words, and correcting spelling improves vector comparisons.  
Our skeleton implements these stages as separate services so that the team can experiment with different strategies without changing unrelated code.

---

## Repository Structure

```
RAG_pipeline_worker/
│
├── README.md
├── AGENTS.md
├── Round_1_Requirements.md
├── requirements.txt
├── .pre-commit-config.yaml
│
├── src/
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── domain/
│       │   ├── __init__.py
│       │   └── models.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── ingestion_service.py
│       │   ├── extraction_service.py
│       │   ├── cleaning_service.py
│       │   ├── chunking_service.py
│       │   ├── enrichment_service.py
│       │   └── vector_service.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── pdf_parser.py
│       │   ├── docx_parser.py
│       │   ├── ppt_parser.py
│       │   └── llm_client.py
│       ├── observability/
│       │   ├── __init__.py
│       │   └── logger.py
│       └── api/
│           ├── __init__.py
│           └── routers.py
│
└── tests/
    ├── __init__.py
    ├── test_services.py
    └── test_end_to_end.py
````

---

## Getting Started

### Install Dependencies

Use Python 3.11+ and create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
````

### Run the Application

The FastAPI app exposes minimal endpoints for uploading a document and retrieving processed results.
To start the development server on your local machine:

```bash
uvicorn src.app.main:app --reload
```

Navigate to `http://localhost:8000/docs` for auto-generated API documentation.

### Use the Developer Dashboard

The dashboard at `http://localhost:8000/dashboard` is designed for manual QA:

1. Upload `tests/test_document.pdf` (or any PDF/DOCX/PPT) via the form.
2. The pipeline runs end-to-end and streams its structured stage payloads into the dashboard.
3. Inspect the embedded document preview alongside the extraction, chunking, and enrichment cards. Each card shows the JSON output emitted by that service, including page/chunk counts and metadata offsets.
4. The last 10 runs are kept in memory for comparison. Restarting the server clears the history by design.

Stage cards are rendered vertically with numbered markers so you can follow the exact flow: **(1) ingestion → (2) extraction → (3) cleaning → (4) chunking → (5) enrichment → (6) vectorization**. Each card reflects whatever payload the corresponding service emits, so extending a service automatically enriches the dashboard. The dashboard uses a lightweight vanilla-JS `fetch` shim to update the run details asynchronously—no external libraries are required.

Uploads run asynchronously: the dashboard immediately shows the new run, then refreshes the stage cards every ~1.5s as each stage finishes. Duration metadata (in milliseconds) is captured inside the `PipelineRunner`, so you can see exactly how long each step took once it completes.

#### Simulated Stage Latency

The FastAPI routes instantiate each service with a configurable delay so that the UI can account for long-running stages. Set `PIPELINE_STAGE_LATENCY` (seconds) before starting `uvicorn` to tune this behavior:

```bash
PIPELINE_STAGE_LATENCY=0.05 uvicorn src.app.main:app --reload
```

Use `0` to disable the artificial delay when running benchmarks or production workloads.

See `docs/Dashboard_Requirements.md` for the specification that governs this view and guidance on how future services should publish data to it.

### Run the Tests

Execute the test suite with pytest:

```bash
pytest -q
```

Service behavior is covered in `tests/test_services.py`, while `tests/test_end_to_end.py` uploads a dummy document through the FastAPI stack to assert that pages and chunks are returned.

---

## Contribution Guidelines

This project is a starting point for a team to build a robust document-processing pipeline.
To keep the codebase maintainable and encourage parallel development:

* **Follow the domain-driven, hexagonal architecture:**
  Core domain models and use cases should not depend on the details of file parsing or LLM implementation.
  Adaptors implement those details and can be swapped without touching the domain logic.

* **Respect the data model:**
  The `models.py` definitions are the single source of truth for the structure of documents, pages, chunks, and metadata.
  When extending the models, update corresponding tests and ensure downstream services handle new fields.

* **Keep service interfaces stable:**
  Each service exposes a public API (e.g., `ingest()`, `extract_text()`, `chunk()`, `enrich()`).
  Team members can experiment with new algorithms internally as long as they preserve the interfaces.

* **Write tests before changing behavior:**
  The test harness demonstrates how to add unit and integration tests.
  New features should include tests to prevent regressions.
  Hexagonal architecture facilitates testability by isolating external dependencies.

* **Use pre-commit hooks:**
  A simple `.pre-commit-config.yaml` is included for linting and formatting (`black`, `isort`, `flake8`).
  Install with `pre-commit install` to run checks before committing.

* **Document your changes:**
  When adding new modules or adapting existing ones, update `Round_1_Requirements.md` or create a new specification file to reflect the changes.
  Specification drives implementation—code should align with evolving requirements.

---

## Next Steps

The current v0 skeleton contains placeholder implementations.
Future iterations will:

* Implement concrete adapters for PDF/DOCX/PPT parsing using libraries such as `pdfplumber` and `python-docx`.
* Integrate a language model for intelligent extraction of tables, images, and scanned text.
* Add configurable chunking strategies (fixed-length, semantic, hierarchical).
* Enrich chunks with metadata fields—ID, title, summary, keywords, entities, and questions—for filtering and retrieval.
* Provide observability and tracing dashboards via logging or OpenTelemetry instrumentation.
* Deploy the application to AWS environments (e.g., EC2 or Elastic Beanstalk) with secure configuration.

This repository is the foundation upon which those features will be built.
