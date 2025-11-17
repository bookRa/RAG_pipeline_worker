# LLM Integration Implementation Guide

This guide tracks how LLM-powered stages are wired into the pipeline, where the current implementation diverges from the LlamaIndex integration plan, and what needs to happen next (with emphasis on the 300 DPI pixmap requirement).

---

## End-to-End Touchpoints (Today)

- **Parsing (`src/app/services/parsing_service.py`)** – renders 300 DPI pixmaps via `PixmapFactory` whenever `ChunkingSettings.include_images` is enabled, attaches the resulting PNG paths/byte sizes to `ParsedPage`, and feeds both text + image into the multi-modal `ImageAwareParsingAdapter`.
- **Cleaning (`src/app/services/cleaning_service.py`)** – invokes `CleaningAdapter` to normalize parsed pages against the schema in `src/app/parsing/schemas.py`.
- **Chunking (`src/app/services/chunking_service.py`)** – still orchestrates slicing but now prefers the LlamaIndex splitter returned by `get_llama_text_splitter()` with the `chunk_size`/`chunk_overlap` set in `config.py`.
- **Enrichment and Summaries (`src/app/services/enrichment_service.py`)** – continue to depend on the `SummaryGenerator` port, which is fulfilled by `LlamaIndexSummaryAdapter` whenever the OpenAI LLM is configured.
- **Vectorization (`src/app/services/vector_service.py`)** – drives embeddings through `LlamaIndexEmbeddingAdapter` and writes to the `VectorStoreAdapter` (currently the in-memory implementation).

---

## Alignment vs. Plan

What’s done:
- Ports for `ParsingLLM`, `CleaningLLM`, `EmbeddingGenerator`, and `VectorStoreAdapter` exist, keeping services decoupled from LlamaIndex internals.
- `ImageAwareParsingAdapter` already loads prompts from `PromptSettings` and validates against `ParsedPage`.
- `config.py` exposes nested LLM/embedding/chunking/vector-store/prompt models, and `bootstrap.configure_llama_index()` wires them into `llama_index.core.Settings`.
- Contract tests plus prompt assets live under `docs/prompts/**`.

What’s still missing (highest priority first):
1. **Pixmap retention + reuse** – rendered assets accumulate under `artifacts/pixmaps/{document_id}` with no GC or checksum-based cache, so long-running nodes will eventually leak disk space.
2. **Downstream image awareness** – cleaning, chunking, and enrichment metadata still ignore `pixmap_path`; we need to propagate figure/table references into cleaned segments and chunk metadata for traceability.
3. **Dashboard + contract visibility** – the dashboard/test harness do not yet surface the new observability metrics (`attached/skipped counts`, `avg vision latency`), making regressions hard to detect.
4. **Oversize fallback** – pages whose pixmaps exceed `max_pixmap_bytes` simply fall back to text-only parsing; we should add automatic downscaling or tiling so visually dense PDFs still benefit from the multi-modal path.

---

## Immediate Next Steps

1. **Add pixmap retention + reuse.**
   - Track the PDF checksum from ingestion and reuse existing pixmaps when the checksum matches to avoid needless rendering.
   - Provide a cleanup command (or background job) that trims stale pixmap directories after N days or once the directory exceeds a size budget.
2. **Make cleaning/chunking image-aware.**
   - Extend `ParsedPage` ➝ `CleanedPage` transformations to carry `pixmap_path`/`figure` references so chunk metadata can cite the original asset.
   - Update chunk metadata (and eventual vector payloads) with the associated `pixmap_path` so QA tooling can open the exact image that informed a chunk.
3. **Expose observability + dashboard views.**
   - Feed `ParsingService`’s new metrics (`attached`, `skipped`, `total_size_bytes`, `avg_latency_ms`) into dashboard cards/logs and ensure contract tests assert their presence.
   - Emit token + image credit stats from the callback manager so spend can be tracked per document.
4. **Handle oversize pixmaps gracefully.**
   - Downscale or tile PNGs that exceed `max_pixmap_bytes` instead of skipping them entirely, and add tests to ensure the fallback logic is deterministic.
5. **Testing.**
   - Complement the new unit tests with an end-to-end opt-in test that renders a PDF, confirms pixmap reuse, and asserts the multi-modal adapter is invoked exactly once per page.

---

## Implementation Notes

### Parsing & Cleaning Flow
- `ParsingService.parse()` now renders pixmaps (via `PixmapFactory`) before `_run_structured_parser` executes, records per-page latency, and stores `pixmap_path` + `pixmap_size_bytes` inside `document.metadata["parsed_pages"]` and `["pixmap_assets"]`.
- `ImageAwareParsingAdapter` takes both a text `llm` and an optional `vision_llm` (`OpenAIMultiModal`); when a pixmap path is provided it sends the PNG via `image_documents` while still requesting JSON-structured output.
- `CleaningService` continues to reconstruct `ParsedPage` objects from metadata, so the schema additions (`pixmap_path`, `pixmap_size_bytes`) are already available for future cleaning logic (e.g., highlighting when an OCR fix references an image).

### Summaries & Embeddings
- `EnrichmentService` only depends on `SummaryGenerator`; `LlamaIndexSummaryAdapter` can continue to use text-only prompts.
- `VectorService` wires `LlamaIndexEmbeddingAdapter` and persists vectors through `VectorStoreAdapter`. No change is required for pixmaps, but we should confirm chunk metadata carries the associated `parsed_paragraph_id` so downstream retrieval can point back to the originating image when needed.

### Configuration & Prompts
- `src/app/config.py` now exposes `ChunkingSettings.include_images`, `pixmap_dpi`, `pixmap_storage_dir`, and `max_pixmap_bytes`, plus the usual `PromptSettings`. `AppContainer` reads these knobs (with env overrides such as `PIXMAP_STORAGE_DIR`) before instantiating `PixmapFactory`.
- `configure_llama_index()` instantiates both the textual `llama_index.llms.openai.OpenAI` client and an `OpenAIMultiModal` instance using the same `LLMSettings` values (default `gpt-4o-mini`), so adapters can pick the right transport without re-reading env vars.
- Prompts still live under `docs/prompts/parsing/` and `docs/prompts/cleaning/`; they should now mention that an image attachment is available whenever `pixmap_path` is provided, so prompt authors know how to reference visual context.

### File Handling & Storage Hygiene
- Keep pixmaps outside of the FastAPI process memory. Persist them under `artifacts/pixmaps/` with deterministic names and clean them up when a pipeline run completes or expires.
- Include the pixmap path (or a hashed reference) inside `document.metadata["parsed_pages"][page]["assets"]` so QA tooling can display the exact image that fed the LLM.

---

## Testing Strategy (Expanded)

| Layer | What to Cover | Notes |
| --- | --- | --- |
| Pixmap helper | Page-to-PNG conversion at 300 DPI, disk layout, error handling | Use a single-page fixture PDF to assert the helper emits deterministic filenames and honors `include_images`. |
| Parsing adapter | Prompt assembly, multi-modal payload construction, fallback to text-only | Mock the LlamaIndex client (`OpenAIMultiModal`) so CI stays offline. Assert that `image_documents` is populated when `pixmap_path` is provided. |
| Parsing service | Ensures pixmap generation + `parsed_pages` metadata | Inject fake parsers and structured parser to assert metadata wiring without hitting the filesystem. |
| Cleaning/adapters | Existing normalization behavior plus any new `image_reference` fields | Continue using deterministic fakes. |
| Summary/embedding/vector tests | No change other than ensuring pixmap metadata does not break serialization | Existing tests in `tests/test_services.py` already mock adapters; extend fixtures if new metadata appears. |
| End-to-end smoke tests | Optional dev-only test hitting real LLMs (guarded by `RUN_CONTRACT_TESTS`) | Useful once multi-modal calls are plumbed through. |

---

## Observability, Cost, and Safeguards

- `ParsingService` now emits per-document metrics (`generated`, `attached`, `skipped`, `total_size_bytes`, `avg_latency_ms`) so logs clearly show when the multi-modal path was exercised. Surface these fields in dashboards/tests next.
- Multi-modal OpenAI calls still flow through `CallbackManager(TokenCountingHandler())`; plumb those token/image counts into the same parsing event so cost regressions are visible.
- Pixmap rendering currently produces a directory per document; add checksum-based caches and retention policies so repeated uploads don’t blow up disk usage.
- Oversize pixmaps (> `max_pixmap_bytes`) log a warning and fall back to text. Replace this with automatic downscaling/retries so we do not silently lose visual context on large schematics.

---

## Checklist

- [x] 300 DPI pixmap helper emits PNGs under `artifacts/pixmaps/{document}/{page}.png`.
- [x] `ParsingService` stores pixmap metadata and passes it to `ParsingLLM.parse_page`.
- [x] `ImageAwareParsingAdapter` builds multi-modal payloads (with graceful fallback to current text-only mode).
- [x] `ChunkingSettings.include_images` + new configuration knobs govern the feature flag.
- [x] Tests cover pixmap creation, adapter payloads, and metadata propagation (unit scope).
- [x] Observability events surface pixmap usage and model details.
- [ ] Contract tests remain opt-in and no CI path performs real network calls.

---

## References

- `src/app/services/parsing_service.py`
- `src/app/adapters/llama_index/parsing_adapter.py`
- `src/app/parsing/schemas.py`
- `src/app/config.py`
- `docs/prompts/parsing/*`
- `docs/ARCHITECTURE.md` § "LlamaIndex Integration"
- `docs/prompts/README.md`
