You are the coding agent responsible for implementing the v0 skeleton of our RAG document‑processing pipeline.

Goal: Create a modular, FastAPI-based repository that adheres to the Round_1_Requirements.md specification and follows the architecture outlined in the AGENTS.md planning phase.

Tasks:
1. **Set up the repository**  
   - Create the directory structure exactly as described in the README (src/app with domain, services, adapters, observability and api packages; tests folder; documentation files).  
   - Write a minimal `requirements.txt` with FastAPI, uvicorn, pydantic, pydantic-settings, python-multipart, pytest and requests.  
   - Include a `.pre-commit-config.yaml` using black, flake8 and isort.

2. **Implement the domain models**  
   - In `src/app/domain/models.py`, define Pydantic v2 models: `Document`, `Page`, `Chunk` and `Metadata`.  
   - Ensure each model contains fields described in the requirements (e.g. unique IDs, page numbers, start/end offsets, title and summary).  
   - Provide helper methods `add_page()` and `add_chunk()` on `Document`.

3. **Create service stubs**  
   - In `src/app/services`, implement classes for ingestion, extraction, chunking and enrichment with stable public methods (`ingest()`, `extract()`, `chunk()`, `enrich()`).  
   - For v0, the implementations can return placeholder data but must log their actions and attach metadata appropriately.  
   - Each service must accept and return domain models only—no direct file parsing or LLM calls here.

4. **Add adapter placeholders**  
   - Provide stub modules in `src/app/adapters` for `pdf_parser`, `docx_parser`, `ppt_parser`, and `llm_client`.  
   - Each adapter should expose functions (e.g. `parse()`, `summarize()`) but return empty strings or simple outputs for now.  
   - These stubs allow future team members to experiment with different libraries without changing the service interfaces.

5. **Implement observability utilities**  
   - Use Python’s `logging` module in `src/app/observability/logger.py` to log pipeline stage events.  
   - Include a `log_event(stage: str, details: dict)` function that other modules can call.

6. **Build the FastAPI layer**  
   - In `src/app/api/routers.py`, create endpoints:
     - `POST /upload` for uploading documents; validate file types (PDF, DOCX or PPT), run the pipeline (ingestion → extraction → chunking → enrichment) and return the structured document as JSON.  
     - `GET /documents` to list processed documents.  
     - `GET /documents/{doc_id}` to retrieve a single document by ID.
   - Use an in-memory store to hold processed documents for now.
   - In `src/app/main.py`, assemble the FastAPI app and include the routers.

7. **Write tests**  
   - Use pytest to create unit tests for each service module (ingestion, extraction, chunking and enrichment) under `tests/test_services.py`.  
   - Include a simple end‑to‑end test using FastAPI’s TestClient to upload a dummy file and assert that the server returns a document with pages and chunks (`tests/test_end_to_end.py`).  
   - Ensure tests run without network access and rely only on stubbed adapters.

8. **Documentation**  
   - Ensure `README.md`, `AGENTS.md` and `Round_1_Requirements.md` remain up‑to‑date with your implementation.  
   - Follow the contribution guidelines: respect the data model, keep service interfaces stable and write tests for new features.

All code should be properly formatted and lint‑free according to the pre-commit hooks. Push your changes once all tests pass locally.

