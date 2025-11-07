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

document_rag_pipeline_v0/
│
├── README.md               # Project overview and setup instructions
├── AGENTS.md               # Definition of the AI agents and their responsibilities
├── Round_1_Requirements.md # High-level product and engineering requirements for v0
├── requirements.txt        # Minimal package dependencies for running the skeleton
│
├── src/
│   └── app/
│       ├── **init**.py
│       ├── main.py                # FastAPI application with basic endpoints
│       ├── config.py              # Configuration defaults
│       ├── domain/
│       │   ├── **init**.py
│       │   └── models.py          # Core data models (Document, Page, Chunk, Metadata)
│       ├── services/
│       │   ├── **init**.py
│       │   ├── ingestion_service.py   # Handles file upload and storage
│       │   ├── extraction_service.py  # Stub for text and structure extraction
│       │   ├── chunking_service.py    # Stub for chunking strategies
│       │   └── enrichment_service.py  # Stub for metadata enrichment
│       ├── adapters/
│       │   ├── **init**.py
│       │   ├── pdf_parser.py      # Placeholder adapter for PDF parsing
│       │   ├── docx_parser.py     # Placeholder adapter for DOCX parsing
│       │   ├── ppt_parser.py      # Placeholder adapter for PPT parsing
│       │   └── llm_client.py      # Placeholder adapter for LLM-based enrichment
│       ├── observability/
│       │   ├── **init**.py
│       │   └── logger.py          # Simple logging/tracing utilities
│       └── api/
│           ├── **init**.py
│           └── routers.py         # API routes and dependency wiring
│
└── tests/
├── **init**.py
├── test_models.py             # Unit tests for data models
├── test_services.py           # Unit tests for service stubs
└── test_end_to_end.py         # Example end-to-end test using FastAPI TestClient

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

### Run the Tests

Execute the test suite with pytest:

```bash
pytest -q
```

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