# Round-1 Requirements for Document Extraction Pipeline (v0)

This document captures the **product and engineering requirements** for the initial version of our document-processing pipeline.  
The objective of v0 is to build a minimal yet extensible skeleton that ingests documents, extracts text/structure, chunks the content, enriches it with metadata, and exposes the results via a web API.  
Future iterations will add sophisticated logic, but the interfaces defined here should remain stable.

---

## Product Requirements

### 1. Supported File Types
- The pipeline must accept uploads of **PDF**, **DOCX**, and **PowerPoint (PPT)** files.  
- Other formats may be rejected.  
- Document ingestion should normalize filenames and store files in a designated input directory.

---

### 2. Text Extraction and Structuring
- After ingestion, each document must be fully processed so that all textual content—body text, table data, captions, and scanned images—is available for downstream consumption.  
- Placeholder implementations may simply return dummy text but must preserve the API.  
- When extended, the extraction layer should use appropriate libraries (e.g., `pdfplumber` or `python-docx`) to handle different formats.  
- The extraction process should produce a structured representation: a **Document** composed of one or more **Page** objects containing segments of text.  
  This structure will later enable chunking at page or paragraph level.  
- Extracted text should be cleaned by:
  - Removing extra whitespace  
  - Correcting obvious spelling errors  
  - Normalizing case  
  - Optionally removing stop words  
- The original text must still be preserved for traceability.

---

### 3. Chunking Strategy
- The extraction output must be chunked into smaller, semantically meaningful units.  
- Standard strategies include fixed-size tokens, sentence-based, paragraph-based, and semantic splits.  
- The v0 implementation may use a naive fixed-size splitter but must expose a `chunk()` method that accepts content and returns a list of **Chunk** objects.  
- Overlapping chunks should be supported to maintain context.  
- The chunking service should accept parameters such as `size`, `overlap`, and `strategy`.

---

### 4. Metadata Enrichment
- Each chunk must be enriched with metadata that facilitates retrieval and grounding in responses.  
- At minimum, metadata should include:
  - A unique ID  
  - Document ID  
  - Page number  
  - Start/end offsets  
  - Optionally, a title or summary  
- Future enrichments may add keywords, named entities, language, and sample questions.  
- Cleaning operations (e.g., lowercasing, stop-word removal, spelling correction) should **not overwrite** the original chunk.  
  Instead, store the cleaned version separately and maintain a pointer to the original.

---

### 5. Observability and Tracing
- The pipeline must record the inputs and outputs of each stage (ingestion, extraction, chunking, enrichment).  
- In the v0 skeleton, logging statements or simple in-memory stores suffice.  
- Future versions should integrate structured logging or tracing frameworks.  
- Observability data should be linked to document and chunk identifiers so that downstream consumers can trace results back to the source.

---

### 6. Frontend / Inspection
- A minimal web interface or API endpoints should allow users to upload documents and retrieve the processed structure and metadata.  
- The initial FastAPI application can serve as this interface, exposing routes such as:
  - `/upload`
  - `/documents`
  - `/documents/{id}`

---

## Engineering Requirements

### 1. Modular Architecture
- The codebase shall follow **hexagonal (ports and adapters) architecture**.  
- The **domain layer** defines data models and core business logic.  
- **Ports** expose interfaces for operations such as extraction or chunking.  
- **Adapters** implement those interfaces using specific libraries or services (e.g., PDF parsers, LLMs).  
- This separation allows team members to swap implementations without changing the core logic and fosters testability.  
- The data model is the **first-class citizen**. All modules accept and return these models.  
  Changing the data model requires updating the specification and tests.  
- Each service (ingestion, extraction, chunking, enrichment) must expose a **stable API** with clearly documented input and output types.  
  Internal details may evolve, but the signature should remain consistent.

---

### 2. FastAPI Foundation
- Use **FastAPI** to implement a RESTful API.  
- Define **Pydantic models** for request and response bodies.  
- Auto-generated OpenAPI docs should reflect the data model and endpoints.  
- Provide dependency injection points for services, enabling easy substitution of implementations in tests or future deployments.

---

### 3. Testing Harness
- Use **pytest** as the test framework.  
- Write unit tests for each service and adapter to validate behavior.  
- Provide an end-to-end test that uploads a dummy file and asserts that the pipeline returns chunked and enriched output.  
- Tests should not depend on external services—use mocks or fakes for file parsers and LLM calls.  
- Achieve high test coverage early; hexagonal architecture facilitates this by isolating external dependencies.

---

### 4. Development Tooling and Guardrails
- Include a `requirements.txt` with only the minimal dependencies needed for the skeleton (e.g., `fastapi`, `uvicorn[standard]`, `pydantic`, `pytest`).  
  Additional packages may be added as new features are implemented.  
- Provide a `.pre-commit-config.yaml` with basic hooks (`black`, `flake8`, `isort`).  
- Contributors should install **pre-commit** to ensure formatting and linting before committing.  
- Document setup steps in the README.  
- Avoid storing IDE-specific configuration files; ensure the repo works in VSCode, PyCharm, or any editor.  
- Use environment variables or `.env` files for configuration, defaulting to sensible values for localhost and leaving hooks for future AWS deployment.

---

### 5. Extensibility and Future Work
The v0 skeleton should be flexible enough to accommodate future enhancements:
- Integration with LLMs for table extraction, OCR, and summarization.  
- Support for alternative chunking strategies (semantic, hierarchical) and dynamic sizing.  
- Storage adapters for vector databases or search indices.  
- Observability frameworks such as OpenTelemetry and dashboards.  
- Secure deployment to AWS, with environment-specific configuration separated from local defaults.

---

### 6. Acceptance Criteria for v0
A developer can:
1. Clone the repository, install dependencies, run the FastAPI server, and upload a sample file via the `/upload` endpoint.  
   The server responds with a JSON object representing the **Document** and its **Chunks** (even if stubbed).  
2. `src/app/domain/models.py` defines Pydantic models for **Document**, **Page**, **Chunk**, and **Metadata**, and these models are used throughout the services and API.  
3. Each service module (`ingestion_service.py`, `extraction_service.py`, `chunking_service.py`, `enrichment_service.py`) contains a class or function with a stable public API and a placeholder implementation.  
4. Tests run via **pytest** without external network access and cover at least one function in each service, as well as an end-to-end upload test.  
5. The repository includes `README.md`, `AGENTS.md`, this `Round_1_Requirements.md`, `requirements.txt`, and `.pre-commit-config.yaml`.

---

By fulfilling these requirements, the team will have a **robust foundation** on which to build a fully featured RAG document extraction pipeline.
