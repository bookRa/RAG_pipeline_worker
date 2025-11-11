# LlamaIndex Integration Plan

## Decision Summary
- **Vector store target** – Default to LlamaIndex’s built-in in-memory/vector-store implementations during development, but make the storage adapter configurable so we can swap in AWS DocumentDB (or any managed store) without touching services. Provide a filesystem-backed fallback for CI and a configuration surface for future DocumentDB credentials.
- **Chunking scope** – Deprecate the current `ChunkingService` stub in favor of LlamaIndex node parsers (`SentenceSplitter`, `TokenTextSplitter`, etc.). Expose tuning knobs (chunk size, overlap, semantic splitters, metadata propagation) via config and code comments since we expect rapid iteration.
- **Internal LLM contract** – Because we do not control the internal LLM endpoint, wrap it with an adapter that conforms to LlamaIndex’s `LLM` interface. The adapter will translate our HTTP contract into the `.complete`/`.chat` API expected by LlamaIndex and our ports.
- **Dashboard UX** – Keep the dashboard focused on pipeline visibility and manual smoke tests. We will add a single-turn query experience later if needed, but multi-turn chat belongs in the separate chatbot repo.
- **Terminology** – Rename every “Extraction” reference to “Parsing” (code, tests, docs, observability) to reflect the PDF page ➝ pixmap ➝ LLM parsing flow described below.

## Context & Goals
- Introduce production-ready Large Language Model (LLM) capabilities (parsing, cleaning, chunking, summarizing, embedding, ad-hoc querying) without violating hexagonal boundaries.
- Use LlamaIndex abstractions (Documents, Nodes, ingestion pipelines, indexes, query engines, `Settings`) to centralize LLM/embedding configuration while keeping services free of third-party imports.
- Support two execution modes:
  1. **Development** – use OpenAI `gpt-4o-mini` via the public API so `/dashboard` can exercise real LLM calls.
  2. **Production** – route LLM traffic to the internal endpoint through a LlamaIndex-compatible adapter with the same prompts/structured output expectations.
- Maintain offline CI by relying on stubs/mocks; only the manual dashboard path should ever hit a real LLM.

## Architectural Alignment
### Ports & Boundaries
- Extend `application/interfaces.py` with dedicated ports for `EmbeddingGenerator`, `ParsingLLM` (or reuse `DocumentParser` after renaming it to `ParsingAdapter`), and `CleaningLLM` so services stay decoupled from LlamaIndex-specific logic.
- Keep `SummaryGenerator` as the enrichment entry point; `LlamaIndexSummaryAdapter` implements the port and hides prompt templates + retries.
- Introduce `VectorStoreTarget` and `QueryEnginePort` ports so vectorization and manual queries can swap between in-memory, filesystem, and hosted stores.
- All LlamaIndex imports live under `src/app/adapters/llama_index/` (bootstrap, mappers, adapters). Services only depend on ports.

### Configuration Surface
- Expand `src/app/config.py` with nested models:
  - `LLMSettings` – provider (`openai`, `internal`, `mock`), model, temperature, max tokens, API base, API key, timeout, retry policy.
  - `EmbeddingSettings` – embed model, batch size, vector dimension, store target, cache toggles.
  - `ChunkingSettings` – splitter type (`sentence`, `token`, `semantic`), chunk size, overlap, include_images flag, metadata propagation rules.
  - `VectorStoreSettings` – driver (`in_memory`, `llama_index_built_in`, `documentdb`), connection params, persistence paths.
  - `PromptSettings` – directories or filenames for parsing, cleaning, and summary prompts (see below).
- Provide a helper (`LlamaIndexSettingsFactory`) that installs these values into `llama_index.core.Settings` once per process (respecting FastAPI multi-worker deployment).

### Pipeline Stage Updates
1. **Parsing (formerly Extraction)** – Replace PDF parser stubs with a pipeline:
   - Convert PDF pages to pixmaps/images.
   - Invoke a parsing LLM prompt that accepts both raw text (from pdfplumber fallback) and the pixmap to produce structured JSON with fields for paragraphs, tables (with rows/columns), figures/images (including descriptions), and per-element bounding boxes when available.
   - Store prompts/templates under `docs/prompts/parsing/` and load them via config so we can iterate quickly.
   - Keep structured-output schemas in a dedicated module (e.g., `src/app/parsing/schemas.py` powered by Pydantic) so both dev and prod LLMs must satisfy the same contract.
2. **Cleaning** – Run a second LLM prompt that receives the parsing JSON (and optionally pixmap references) to normalize text, fix OCR artifacts, and produce final clean text plus rationale. Provide deterministic fallbacks for empty responses. Store cleaning prompts/structured schemas alongside parsing assets.
3. **Chunking** – Feed cleaned text segments into LlamaIndex node parsers. The chunking service becomes a thin orchestrator that:
   - Chooses a splitter strategy based on `ChunkingSettings`.
   - Logs rules-of-thumb (e.g., “start with 512 tokens w/ 50 overlap for spreadsheet-heavy docs”).
   - Stores chunk metadata (page number, bounding boxes, original paragraph ID).
4. **Enrichment & Vectorization** – Continue to use ports; swap adapters to LlamaIndex for summaries and embeddings. Add hooks so chunk metadata includes LLM latency, token counts, and prompt version IDs.

### Vector Store Strategy
- Default: use `llama_index.core.VectorStoreIndex` with the built-in `SimpleVectorStore` persisted under `artifacts/vector_store/`.
- Provide `VectorStoreAdapter` implementations for:
  - `InMemoryVectorStoreAdapter` – used in tests/CI.
  - `LlamaIndexLocalStoreAdapter` – uses built-in vector store + ingestion cache.
  - `DocumentDBVectorStoreAdapter` (stub initially) – defines the contract and configuration needed to push vectors to AWS DocumentDB once credentials are ready.
- Vectorization stage writes via the adapter port; swapping the runtime target requires only config changes.

## Parsing & Cleaning via LLMs
1. **Prompt Organization**
   - Store system/user prompts under `docs/prompts/parsing/` and `docs/prompts/cleaning/`. Include README files that document tuning levers and iteration history.
   - Provide a small prompt loader utility (`src/app/prompts/loader.py`) that reads prompts at startup and injects them into adapters; include inline comments with “rules of thumb” for chunk sizes, JSON schema expectations, and fallback heuristics.
2. **Structured Output Schemas**
   - Define Pydantic models for parsing (e.g., `ParsedPage`, `ParsedTable`, `ParsedFigure`, `ParsedParagraph`) and cleaning outputs (clean text, confidence, detected issues).
   - LlamaIndex supports structured outputs via Pydantic programs or JSON mode. Adapters should validate responses against these schemas and raise recoverable errors that services can log without crashing the pipeline.
3. **LLM Adapter Layer**
   - `ImageAwareParsingAdapter` – wraps pixmap creation, builds the multi-modal prompt, and calls either OpenAI Vision (dev) or the internal endpoint (prod) via a `LLM` interface wrapper.
   - `CleaningAdapter` – uses a text-only LLM call to normalize content; optionally reuses parsed image metadata.
   - Both adapters expose metrics (latency, token counts, retry count) through `ObservabilityRecorder`.
4. **Fallback Paths**
   - If the LLM parsing call fails, fall back to pdfplumber text with minimal structuring so downstream stages still work.
   - If cleaning fails, propagate the raw parsed text and flag the chunk for manual QA (metadata field `cleaning_status="fallback"`).

## Implementation Plan
1. **Rename Extraction ➝ Parsing**
   - Update module names (`extraction_service.py` ➝ `parsing_service.py`, `PdfParserAdapter` ➝ `PdfParsingAdapter`, etc.), tests, documentation, and observability events (`stage="parsing"`).
   - Adjust architecture diagrams and README references accordingly.
2. **Configuration Foundation**
   - Implement the expanded `Settings` models and document new env vars in `README.md` + `docs/LLM_Integration_Implementation_Guide.md`.
   - Add `.env.example` entries for LLM/provider/vector store settings.
3. **LlamaIndex Bootstrap**
   - Build `src/app/adapters/llama_index/bootstrap.py` with helpers to configure `llama_index.core.Settings`, instantiate provider-specific `LLM` objects (OpenAI, internal HTTP adapter, mock), and construct ingestion pipelines.
   - Ensure bootstrap is idempotent and thread-safe.
4. **Parsing & Cleaning Adapters**
   - Create `ImageAwareParsingAdapter` and `CleaningAdapter` under `adapters/llama_index/`.
   - Implement pixmap-to-LLM bridging and schema validation.
   - Write unit tests using fake LLM clients that return canned JSON.
5. **Chunking Overhaul**
   - Replace the `ChunkingService` internals with LlamaIndex node parsers.
   - Surface chunking configuration via dependency injection and document experimentation tips in code comments.
   - Add regression tests verifying metadata propagation and configurability.
6. **Summary & Embedding Adapters**
   - Implement `LlamaIndexSummaryAdapter` and `LlamaIndexEmbeddingAdapter` using the bootstrap-provided LLM/embedding clients.
   - Add batching, retry, observability, and deterministic stubs for tests.
7. **Vector Store Adapter Layer**
   - Define the `VectorStoreAdapter` port and initial adapters (in-memory + local LlamaIndex).
   - Implement `DocumentDBVectorStoreAdapter` scaffold with TODOs for credentials so the interface is ready when we integrate AWS.
8. **Query & Dashboard Integration**
   - Add a `QueryEngineAdapter` that can be manually invoked via the dashboard *in the future*. For now, expose configuration hooks and routes that return “not enabled” until requirements change.
   - Document how a single-turn query workflow would plug in once prioritized.
9. **Documentation & Prompts**
   - Add prompt files, schema docs, and iteration guidelines under `docs/prompts/`.
   - Update `docs/ARCHITECTURE.md`, `docs/LLM_Integration_Implementation_Guide.md`, and any service-specific guides to describe the new parsing/cleaning/chunking flow and naming.
10. **Testing & Observability**
    - Extend `tests/test_services.py` (and new parsing tests) with fakes for every adapter.
    - Ensure `tests/test_architecture.py` remains green by keeping LlamaIndex imports inside adapters.
    - Add observability assertions for new fields (prompt version, token counts, vector store target).

## Testing & Deployment Considerations
- CI runs in `LLM_PROVIDER=mock` mode with no network calls. Provide deterministic fixtures for parsing/cleaning outputs and embeddings.
- Local developers can opt into real LLMs by exporting `LLM_PROVIDER=openai` and the relevant API key; guard these code paths with clear logging to prevent accidental spend.
- Provide a smoke-test script (or README section) demonstrating how to run a sample document through the new parsing ➝ cleaning ➝ chunking ➝ vectorization flow.

## Future Work
- Implement the DocumentDB adapter once infrastructure credentials are ready; this should be a configuration change thanks to the new port.
- Add a dashboard “single-turn query” panel when required, powered by the `QueryEngineAdapter`.
- Explore advanced chunking strategies (semantic splitters, hybrid rule-based chunkers) by swapping the LlamaIndex splitter configuration—document experimentation steps in `docs/prompts/README.md`.
