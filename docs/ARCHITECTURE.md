# Architecture Guide

This document describes the hexagonal architecture patterns used in this codebase and provides guidance for developers.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Layer Structure](#layer-structure)
3. [Dependency Flow](#dependency-flow)
4. [Key Patterns](#key-patterns)
5. [Immutability](#immutability)
6. [Dependency Injection](#dependency-injection)
7. [Use Cases](#use-cases)
8. [Testing Strategy](#testing-strategy)

---

## Architecture Overview

This codebase follows **Hexagonal Architecture** (also known as Ports and Adapters), which separates business logic from infrastructure concerns. The architecture ensures:

- **Domain independence**: Business logic doesn't depend on external frameworks or libraries
- **Testability**: Each layer can be tested in isolation
- **Flexibility**: Adapters can be swapped without changing business logic
- **Maintainability**: Clear separation of concerns

---

## Layer Structure

```
src/app/
├── domain/              # Core business logic (innermost layer)
│   ├── models.py        # Domain entities (Document, Page, Chunk, Metadata)
│   └── run_models.py    # Pipeline execution models
│
├── application/         # Application interfaces and use cases
│   ├── interfaces.py    # Protocol definitions (ports)
│   └── use_cases/       # Use case implementations
│       ├── upload_document_use_case.py
│       ├── list_documents_use_case.py
│       └── get_document_use_case.py
│
├── services/            # Application services (orchestration)
│   ├── ingestion_service.py
│   ├── extraction_service.py
│   ├── cleaning_service.py
│   ├── chunking_service.py
│   ├── enrichment_service.py
│   ├── vector_service.py
│   ├── pipeline_runner.py
│   └── run_manager.py
│
├── adapters/            # Primary adapters (parsers, LLM clients)
│   ├── pdf_parser.py
│   ├── docx_parser.py
│   ├── ppt_parser.py
│   └── llm_client.py
│
├── persistence/         # Secondary adapters (repositories)
│   ├── ports.py         # Repository interfaces
│   └── adapters/        # Concrete implementations
│       ├── filesystem.py
│       ├── document_filesystem.py
│       └── ingestion_filesystem.py
│
├── observability/       # Observability adapters
│   └── logger.py        # LoggingObservabilityRecorder
│
├── api/                 # Web framework adapters (FastAPI)
│   ├── routers.py
│   ├── dashboard.py
│   ├── task_scheduler.py
│   └── templates/
│       ├── base.html
│       ├── dashboard.html
│       └── partials/run_details.html
│
└── container.py         # Composition root (dependency injection)
```

---

## Dependency Flow

The dependency direction follows this rule: **dependencies point inward**.

```
API Layer
    ↓
Use Cases
    ↓
Services
    ↓
Application Interfaces (Ports)
    ↓
Domain Models
```

**Key Rules:**

1. **Domain layer** must not import from any other layer
   - Only standard library and pydantic allowed
   - No infrastructure dependencies

2. **Services** can import from:
   - Domain models
   - Application interfaces (ports)
   - Persistence ports (repository interfaces)
   - Other services (for orchestration)

3. **Adapters** implement ports defined in `application/interfaces.py`
   - They can import domain models
   - They cannot be imported by services directly

4. **API layer** uses use cases, not services directly
   - Keeps HTTP concerns separate from business logic

---

## Pipeline Services at a Glance

| Stage | Class | Description | Status & Telemetry |
| --- | --- | --- | --- |
| Ingestion | `IngestionService` | Records the upload event, persists raw bytes through the `IngestionRepository`, computes checksum, and stamps `ingested_at`. | Sets `Document.status = "ingested"` and emits `stage="ingestion"` events containing filename, type, and size. |
| Extraction | `ExtractionService` | Resolves a `DocumentParser` for the requested file type (pdfplumber-backed PDF parser plus DOCX/PPT stubs) and creates immutable `Page` models; falls back to placeholder text if parsing yields no pages. | Sets status to `"extracted"` and reports parser name plus per-page previews. |
| Cleaning | `CleaningService` | Normalizes whitespace (or injected normalizer), records `cleaning_report`, and stores `cleaning_metadata_by_page` so chunking can attach metadata later. | Sets status to `"cleaned"` and logs profile + summary counts. |
| Chunking | `ChunkingService` | Splits each page into overlapping `Chunk` slices, preserves raw text, attaches cleaned slices if available, and adds cleaning metadata under `chunk.metadata.extra`. | Sets status to `"chunked"` and returns per-page chunk arrays, offsets, and chunk counts. |
| Enrichment | `EnrichmentService` | Ensures each chunk has a title/summary by delegating to the injected `SummaryGenerator` (default `LLMSummaryAdapter` stub). Builds a lightweight document summary when possible. | Sets status to `"enriched"` and emits summaries for dashboard display. |
| Vectorization | `VectorService` | Generates deterministic placeholder vectors (configurable dimension) for every chunk and stores sample vectors on document metadata to aid debugging. | Sets status to `"vectorized"` and records vector counts + sample vectors. |

`PipelineRunner` executes these services sequentially, captures duration/metadata per stage, and hands the `PipelineResult` to `PipelineRunManager`. The run manager snapshots stage output via `PipelineRunRepository`, allowing the dashboard to show incremental progress while background work runs via the `TaskScheduler` port.

---

## Ports and Adapters in this Release

- **DocumentParser** → Implemented by `PdfParserAdapter`, `DocxParserAdapter`, and `PptParserAdapter`. Only the PDF adapter talks to `pdfplumber`; the other two remain simple placeholders until real parsers are introduced.
- **SummaryGenerator** → `LLMSummaryAdapter` truncates chunk text today, but any real LLM-backed summarizer can be swapped in without touching `EnrichmentService`.
- **ObservabilityRecorder** → `LoggingObservabilityRecorder` bridges to Python logging and outputs JSON payloads per stage. Tests often rely on `NullObservabilityRecorder` or bespoke stubs to assert emitted events.
- **TaskScheduler** → `BackgroundTaskScheduler` wraps FastAPI's `BackgroundTasks` so `PipelineRunManager` can execute long-running work asynchronously from dashboard requests.
- **Repositories** → `FileSystemIngestionRepository`, `FileSystemDocumentRepository`, and `FileSystemPipelineRunRepository` implement the storage ports declared under `src/app/persistence/ports.py`. They insulate services/use cases from persistence concerns.

Every adapter is wired exclusively inside `src/app/container.py`, which becomes the single place to configure environment-driven overrides (custom storage paths, alternate observability adapters, new parsers, etc.).

---

## Persistence & Run Tracking

- Raw uploads land in `artifacts/ingestion/<document_id>/` with timestamped filenames and SHA-256 checksums. The ingestion stage stores the on-disk path inside `Document.metadata["raw_file_path"]` to support delayed parsing.
- Processed `Document` snapshots live under `artifacts/documents/` and are loaded by the `/documents` API endpoints. These files drive the public interface for clients/tests.
- Pipeline run metadata is written to `artifacts/runs/<run_id>/`, where `run.json` tracks status + stage order, `document.json` stores the latest document snapshot, and `stages/*.json` contains the payload for each service. The dashboard renders these files verbatim.
- Each directory can be overridden through environment variables (`INGESTION_STORAGE_DIR`, `DOCUMENT_STORAGE_DIR`, `RUN_ARTIFACTS_DIR`) so deployments can point at shared volumes or cloud buckets without code changes.

---

## FastAPI Entry Points & Background Work

- REST routes in `api/routers.py` depend only on use cases, keeping HTTP validation separate from business logic.
- The dashboard routes (`api/dashboard.py`) provide a manual QA harness: uploads kick off `PipelineRunManager.run_async`, and a lightweight polling loop fetches run fragments while background tasks finalize the pipeline.
- `api/task_scheduler.py` adapts FastAPI's `BackgroundTasks` to the `TaskScheduler` port so orchestration logic stays framework-agnostic.
- Static assets (document previews) are served from `static/uploads/`, and templates under `api/templates/` render run details, stage cards, and histories with zero frontend build tooling.

---

## Key Patterns

### Ports and Adapters

**Ports** are interfaces defined in `application/interfaces.py`:

```python
class DocumentParser(Protocol):
    """Port for file-type specific document parsers."""
    supported_types: Sequence[str]
    def supports_type(self, file_type: str) -> bool: ...
    def parse(self, file_bytes: bytes, filename: str) -> list[str]: ...
```

**Adapters** implement these ports:

```python
class PdfParserAdapter(DocumentParser):
    """Concrete adapter implementing PDF parsing."""
    supported_types: Sequence[str] = ("pdf",)
    def supports_type(self, file_type: str) -> bool: ...
    def parse(self, file_bytes: bytes, filename: str) -> list[str]: ...
```

### Composition Root

All dependencies are wired in `container.py`:

```python
class AppContainer:
    def __init__(self):
        # Wire adapters
        self.observability = LoggingObservabilityRecorder()
        
        # Wire services with dependencies
        self.ingestion_service = IngestionService(
            repository=self.ingestion_repository,
            observability=self.observability,
        )
        
        # Wire use cases
        self.upload_document_use_case = UploadDocumentUseCase(
            runner=self.pipeline_runner,
            repository=self.document_repository,
        )
```

---

## Immutability

All domain models and service methods follow **immutability patterns**:

### Domain Models

Domain models return new instances instead of mutating:

```python
# Before (mutation - WRONG)
def add_page(self, page: Page) -> Page:
    self.pages.append(page)  # Mutates self
    return page

# After (immutability - CORRECT)
def add_page(self, page: Page) -> Document:
    updated_pages = [*self.pages, page]
    return self.model_copy(update={"pages": updated_pages})
```

### Services

Services return new Document instances:

```python
# Before (mutation - WRONG)
def clean(self, document: Document) -> Document:
    document.status = "cleaned"  # Mutates input
    return document

# After (immutability - CORRECT)
def clean(self, document: Document) -> Document:
    return document.model_copy(update={"status": "cleaned"})
```

### Benefits

- **Predictable behavior**: Original objects remain unchanged
- **Easier testing**: Can verify original state is preserved
- **Thread safety**: No shared mutable state
- **Debugging**: Clear state transitions

---

## Dependency Injection

All services accept dependencies via constructor injection:

```python
class IngestionService:
    def __init__(
        self,
        latency: float = 0.0,
        repository: IngestionRepository | None = None,
        observability: ObservabilityRecorder,  # Required, no default
    ) -> None:
        self.repository = repository
        self.observability = observability
```

**Key Principles:**

1. **No concrete imports in services**: Services only import interfaces
2. **Required dependencies**: No `None` defaults for critical dependencies
3. **Container provides defaults**: `AppContainer` wires all dependencies
4. **Testability**: Easy to inject mocks/stubs in tests

### Example: Testing with Mocks

```python
def test_service_uses_injected_dependency():
    mock_recorder = StubObservabilityRecorder()
    service = IngestionService(observability=mock_recorder)
    # Service uses mock_recorder, not a concrete implementation
```

---

## Use Cases

Use cases encapsulate business logic and orchestration:

```python
class UploadDocumentUseCase:
    def __init__(self, runner: PipelineRunner, repository: DocumentRepository):
        self.runner = runner
        self.repository = repository
    
    def execute(self, filename: str, file_type: str, file_bytes: bytes) -> Document:
        # Validation
        if not filename:
            raise HTTPException(status_code=400, detail="Filename is required")
        
        # Business logic
        document = Document(...)
        result = self.runner.run(document, file_bytes=file_bytes)
        
        # Persistence
        self.repository.save(result.document)
        return result.document
```

**Benefits:**

- **Separation of concerns**: API layer doesn't contain business logic
- **Reusability**: Use cases can be called from different entry points
- **Testability**: Easy to test business logic in isolation
- **Single responsibility**: Each use case handles one operation

---

## Testing Strategy

### Unit Tests

Test each service in isolation with mocked dependencies:

```python
def test_ingestion_returns_new_instance():
    service = IngestionService(observability=NullObservabilityRecorder())
    original = build_document()
    result = service.ingest(original)
    assert result is not original  # Immutability check
```

### Integration Tests

Test use cases with real adapters:

```python
def test_upload_use_case_processes_document(tmp_path):
    repository = FileSystemDocumentRepository(tmp_path)
    use_case = UploadDocumentUseCase(runner=runner, repository=repository)
    document = use_case.execute("test.pdf", "pdf", b"content")
    assert document.status == "vectorized"
```

### Architecture Tests

Verify dependency flow and import rules:

```python
def test_domain_layer_has_no_infrastructure_imports():
    # Verifies domain only imports stdlib + pydantic
    ...

def test_services_dont_import_concrete_adapters():
    # Verifies services only import interfaces
    ...
```

---

## Best Practices

### When Adding a New Service

1. Define the port in `application/interfaces.py` if it needs an adapter
2. Create the service in `services/` with dependency injection
3. Make it return new instances (immutability)
4. Wire it in `container.py`
5. Write tests with mocked dependencies

### When Adding a New Adapter

1. Implement the port from `application/interfaces.py`
2. Place it in the appropriate adapter directory
3. Wire it in `container.py`
4. Write adapter-specific tests

### When Adding a New Use Case

1. Create the use case in `application/use_cases/`
2. Inject required services/repositories
3. Handle validation and error cases
4. Wire it in `container.py`
5. Write use case tests

### When Modifying Domain Models

1. Keep models immutable (use `model_copy()`)
2. Don't add infrastructure dependencies
3. Update all services that use the model
4. Update tests

---

## Common Pitfalls to Avoid

1. **Importing concrete adapters in services**
   - ❌ `from ..adapters.pdf_parser import PdfParserAdapter`
   - ✅ `from ..application.interfaces import DocumentParser`

2. **Mutating domain models**
   - ❌ `document.status = "cleaned"`
   - ✅ `return document.model_copy(update={"status": "cleaned"})`

3. **Business logic in API layer**
   - ❌ Validation and orchestration in route handlers
   - ✅ Use cases handle business logic

4. **Domain depending on infrastructure**
   - ❌ Domain models importing FastAPI, databases, etc.
   - ✅ Domain only imports stdlib + pydantic

---

## Further Reading

- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- [Ports and Adapters Pattern](https://herbertograca.com/2017/11/16/explicit-architecture-01-ddd-hexagonal-onion-clean-cqrs-how-i-put-it-all-together/)
- [Dependency Inversion Principle](https://en.wikipedia.org/wiki/Dependency_inversion_principle)
