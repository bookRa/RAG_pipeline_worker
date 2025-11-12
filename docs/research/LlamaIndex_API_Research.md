# LlamaIndex API Research

## Why LlamaIndex fits the pipeline
- LlamaIndex’s core abstractions (Documents, Nodes, ingestion pipelines, indexes, query engines) are modular and align with a hexagonal architecture because each concern (loading, transforming, storing, querying) is expressed via composable interfaces rather than framework-specific globals.[1][2][3][4][5]
- The framework already assumes LLM and embedding providers are swappable, exposing OpenAI, local, and custom back-ends behind a consistent `LLM` interface plus a `Settings` singleton that centralizes configuration knobs such as model IDs, chunk sizes, tokenizers, and callback managers.[6][7]
- Native ingestion caching, vector store adapters (e.g., Qdrant), and streaming query APIs give us a way to plug deterministic pipeline stages into LlamaIndex for development while still exercising real LLM calls in manual QA.

## Core abstractions to reuse
### Documents, Nodes, and metadata
- `Document` objects wrap any raw data source (PDFs, API payloads, DB rows) and keep metadata + relationships alongside the text.[1]
- `Node` objects represent individual chunks and inherit metadata from their parent `Document`, letting us attach pipeline-specific annotations (chunk/page IDs, cleaning metadata) that can follow the chunk through embeddings or retrieval.[1]

### Node parsers and transformations
- Node parsers (e.g., `SentenceSplitter`, `TokenTextSplitter`) convert documents into nodes either standalone or as part of an `IngestionPipeline`. They accept chunk size/overlap arguments and can run as “transformations” chained with other steps (e.g., metadata extractors, embedding generators).[2][3]
- `IngestionPipeline` composes ordered transformations, optionally writing nodes straight into a vector store; every node+transformation pair can be cached via `IngestionCache`, which is useful for cost control when re-running enrichment during development.[3]

### VectorStoreIndex and QueryEngine
- `VectorStoreIndex.from_documents` handles loading data with a `SimpleDirectoryReader`, splitting docs into nodes, and persisting vectors (in-memory by default) with a configurable batch size (`insert_batch_size`).[4]
- Advanced pipelines can build nodes manually, run ingestion pipelines, then instantiate `VectorStoreIndex(nodes)` or `VectorStoreIndex.from_vector_store(vector_store)` to reuse remote stores such as Qdrant.[4]
- Query execution is mediated by `index.as_query_engine()`, which returns a generic interface for synchronous or streaming queries; it composes indexes and retrievers under the hood while returning rich responses suitable for our dashboard.[5]

## LLM/embedding configuration patterns
- Installing `llama-index-llms-openai` and importing `OpenAI` gives immediate access to completion and chat APIs; `.complete`, `.acomplete`, `.stream_complete`, and `.chat` cover sync, async, streaming, and chat-style workflows, and `model="gpt-4o-mini"` selects the dev-time model. These calls rely on the `OPENAI_API_KEY` environment variable, mirroring the way we already swap adapters by env.[7]
- Multi-modal chat is supported via `ChatMessage` blocks (text, images, audio), so we can eventually capture screenshot previews or PDF thumbnails without changing higher layers.[7]
- The `Settings` singleton is the global configuration source when a component-specific dependency is not provided. We can set:
  - `Settings.llm = OpenAI(model="gpt-4o-mini", temperature=0.1)` (or our internal LLM implementation when running in production).[6]
  - `Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small", embed_batch_size=100)` to align with whichever embedding service we standardize on.[6]
  - `Settings.text_splitter` or the lighter `Settings.chunk_size`/`Settings.chunk_overlap` fields to keep chunking rules consistent with our `ChunkingService` defaults.[6]
  - `Settings.transformations` to register ingestion-time transformers such as `SentenceSplitter` + metadata extractors so the ingestion pipeline mirrors our services while remaining overrideable per run.[6]
  - `Settings.tokenizer` to ensure token accounting matches the active LLM, critical for cost-aware observability.[6]
  - `Settings.callback_manager = CallbackManager([TokenCountingHandler()])` to capture token usage or latency metrics for observability without polluting domain code.[6]
  - Prompt context knobs such as `Settings.context_window` and `Settings.num_output`, ensuring we stay within the internal model’s limits when we switch away from OpenAI.[6]

## Data ingestion and storage hooks
- Ingestion pipelines can incorporate `SentenceSplitter`, `TitleExtractor`, and `OpenAIEmbedding` before writing to vector stores like Qdrant via `QdrantVectorStore`. This mirrors our pipeline stages (clean → chunk → enrich → vectorize) and lets us choose between in-memory nodes or pushing directly into the retrieval index, depending on the environment.[3]
- Because embeddings can be computed inside the pipeline, we can decide whether our `VectorService` remains deterministic (tests) or defers to LlamaIndex embeddings (production), while still reusing the same node representation.[3]

## Multi-modal parsing + pixmaps
- The multi-modal models guide shows how to instantiate `OpenAIMultiModal`, load `image_documents` either from URLs or a local directory via `SimpleDirectoryReader`, and call `.complete(prompt=..., image_documents=...)` so GPT-4V-style models consume both text and images in a single request.[8]
- The same guide demonstrates pairing `OpenAIMultiModal` with `SimpleMultiModalQueryEngine` and retrievers that accept `image_similarity_top_k`, which confirms we can attach the pixmap to parsing prompts while keeping downstream retrieval aware of associated image assets.[8]
- PyMuPDF’s `Page.get_pixmap(dpi=...)` API lets us render each PDF page to a raster image at an explicit resolution; when `dpi` is provided the underlying matrix is ignored, so we can request 300 DPI consistently before handing paths to LlamaIndex.[9]

## Query/runtime surfaces for the dashboard
- `QueryEngine` provides a lightweight adapter boundary: `query_engine.query("prompt")` returns structured responses and supports streaming via `.print_response_stream()`. We can wrap this inside a new adapter that powers `/dashboard` manual tests without leaking query-engine specifics into services.[5]

## Observability and cost controls
- Global callback managers and token counters (`TokenCountingHandler`) give us centralized hooks for telemetry; combining this with our existing `ObservabilityRecorder` keeps LLM spend visible during dev while our production adapter points at the internal LLM endpoint.[6]
- Caching inside `IngestionPipeline` ensures repeated manual runs do not re-embed identical nodes, further containing spend during dashboard demo sessions.[3]

## Key considerations and risks
1. **Settings singleton scope** – Because `Settings` is process-wide, we need a deterministic bootstrapping story (e.g., configure it inside `AppContainer` once per process) and avoid mutating it mid-request to keep the architecture deterministic.[6]
2. **Dual-provider configuration** – We should codify a configuration layer that selects between OpenAI dev settings and our internal LLM adapter per environment; LlamaIndex supports both by swapping `Settings.llm` or passing an explicit `llm` argument into adapters.[6][7]
3. **Vector store choice** – The default in-memory store is fine for tests, but production should push nodes into a persistent store (or our existing artifacts) so manual dashboard queries and downstream retrieval share the same source of truth.[4]
4. **Cost and rate limits** – Streaming and token accounting APIs make it easy to surface usage, but we should still enforce max chunk sizes and per-run budgets when calling remote providers, especially when manual testers exercise `/dashboard` frequently.[2][3][6]

## References
1. LlamaIndex Docs – Documents / Nodes: <https://developers.llamaindex.ai/python/framework/module_guides/loading/documents_and_nodes/>
2. LlamaIndex Docs – Node Parser Usage Pattern: <https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/>
3. LlamaIndex Docs – Ingestion Pipeline: <https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/>
4. LlamaIndex Docs – Using VectorStoreIndex: <https://developers.llamaindex.ai/python/framework/module_guides/indexing/vector_store_index/>
5. LlamaIndex Docs – Query Engine: <https://developers.llamaindex.ai/python/framework/module_guides/deploying/query_engine/>
6. LlamaIndex Docs – Configuring Settings: <https://developers.llamaindex.ai/python/framework/module_guides/supporting_modules/settings/>
7. LlamaIndex Docs – Using LLMs: <https://developers.llamaindex.ai/python/framework/understanding/using_llms/>
8. LlamaIndex Docs – Multi-modal models: <https://developers.llamaindex.ai/python/framework/module_guides/models/multi_modal/>
9. PyMuPDF Docs – `Page.get_pixmap`: <https://pymupdf.readthedocs.io/en/latest/page.html#Page.get_pixmap>
