# Extraction Service Implementation Guide

The extraction stage converts an uploaded binary into immutable `Page` models that downstream services can clean, chunk, and enrich. This guide documents the current implementation, explains how adapters are wired, and outlines the steps required to add or modify parsers while preserving our hexagonal architecture guarantees.

---

## Architectural Placement

```
FastAPI Routes (/upload) ──▶ UploadDocumentUseCase ──▶ PipelineRunner
                                                     ├─ IngestionService
                                                     ├─ ExtractionService  ◀─ DocumentParser port
                                                     └─ …
```

- `ExtractionService` lives under `src/app/services/extraction_service.py`.
- It depends on the domain (`Document`, `Page`), the `ObservabilityRecorder` port, and a sequence of `DocumentParser` implementations supplied via dependency injection.
- Concrete parsers reside in `src/app/adapters/`:
  - `PdfParserAdapter` (real implementation backed by `pdfplumber`)
  - `DocxParserAdapter` and `PptParserAdapter` (still lightweight placeholders)
- Dependency wiring happens exclusively inside `src/app/container.py`, which injects all available parsers when constructing the service.

---

## Current Implementation Details

### Service Responsibilities

`ExtractionService.extract(document, file_bytes=None)` performs the following steps:

1. **Guard rail** – If the document already has pages (e.g., re-run), return it unchanged.
2. **Resolve parser** – Pick the first parser whose `supports_type()` method matches the normalized file extension.
3. **Load payload** – Prefer the `file_bytes` argument, otherwise read from `document.metadata["raw_file_path"]` (written by `IngestionService`).
4. **Parse into pages** – Call `parser.parse(payload, document.filename)` and convert every string into a `Page` model via `Document.add_page(...)`.
5. **Fallback** – If no parser is available or parsing returns zero pages, create a single placeholder page that records filename + approximate size.
6. **Status + telemetry** – Return a new `Document` with `status="extracted"` and emit an `extraction` observability event that includes page count, per-page previews, and the parser name (or `"placeholder"` when falling back).

The service never mutates the original document. All updates use Pydantic’s `model_copy(update=...)` to keep the domain immutable and test-friendly.

### DocumentParser Port

Defined in `src/app/application/interfaces.py`:

```python
class DocumentParser(Protocol):
    supported_types: Sequence[str]
    def supports_type(self, file_type: str) -> bool: ...
    def parse(self, file_bytes: bytes, filename: str) -> list[str]: ...
```

Any new parser must implement that protocol. Services only interact with the port, so swapping parsers never requires changes to `ExtractionService`.

### PDF Parser Adapter

- File: `src/app/adapters/pdf_parser.py`
- Dependency: `pdfplumber`
- Behavior: Iterates over PDF pages and returns the extracted text per page. All errors (corrupt PDFs, password-protected files, empty payloads) are caught and result in `[]`, allowing the service to fall back gracefully.

Docx and PowerPoint adapters currently return simple placeholder strings. They satisfy the protocol today and can be upgraded independently using the same pattern shown in the PDF adapter.

### Container Wiring

`AppContainer` instantiates and injects every parser:

```python
self.document_parsers = [
    PdfParserAdapter(),
    DocxParserAdapter(),
    PptParserAdapter(),
]
self.extraction_service = ExtractionService(
    observability=self.observability,
    latency=stage_latency,
    parsers=self.document_parsers,
)
```

All environment-specific configuration (e.g., enabling/disabling parsers, swapping adapters) should happen in the container to keep the rest of the codebase unaware of infrastructure choices.

---

## Control Flow with Ingestion

1. `IngestionService` stores the raw upload (when an `IngestionRepository` is configured) and writes `raw_file_path` plus `raw_file_checksum` into `Document.metadata`.
2. `ExtractionService` prefers the in-memory `file_bytes` value because it avoids disk I/O during the same request. If unavailable, it follows the metadata pointer and reads the stored file via `Path(...).read_bytes()`.
3. After extraction, downstream stages (`CleaningService`, `ChunkingService`, etc.) operate purely on the `Document.pages` list—no services past extraction need to touch raw files.

This separation allows asynchronous runs kicked off from the dashboard to load the raw payload later, even if the original HTTP request terminated.

---

## Extending or Replacing Parsers

When adding a new parser or upgrading a stub:

1. **Implement the protocol** – Create a class under `src/app/adapters/` that implements `DocumentParser`. Keep third-party imports inside the adapter.
2. **Handle failure modes** – Catch parser/library-specific exceptions and return an empty list to signal “no pages extracted.” The service already handles that scenario.
3. **Write focused tests** – Mirror `tests/test_pdf_parser.py` with unit tests that exercise happy paths plus corrupted/empty payloads. Skip tests gracefully when fixture documents are missing.
4. **Add integration coverage** – Extend `tests/test_services.py` (or create a new test module) to run the real adapter through `ExtractionService` so we verify parser/service integration.
5. **Wire it in the container** – Append the adapter to `AppContainer.document_parsers`. Keep ordering deterministic so the preferred parser runs first for overlapping extensions.
6. **Update documentation** – Record the change here and in `docs/ARCHITECTURE.md` or the relevant requirements file so other agents understand the new behavior.

---

## Testing Strategy

| Test | Location | Focus |
| --- | --- | --- |
| `test_pdf_parser.py` | `tests/test_pdf_parser.py` | Validates the pdfplumber adapter, interface compliance, and error handling. |
| `test_services.py::test_extraction_*` | `tests/test_services.py` | Covers stub parser usage, real PDF parsing (with fixture PDF), reading from stored paths, and immutability expectations. |
| `test_end_to_end.py` | `tests/test_end_to_end.py` | Ensures FastAPI upload requests trigger extraction and return pages/chunks. |
| `test_dashboard.py` | `tests/test_dashboard.py` | Verifies dashboard uploads kick off pipeline runs that eventually surface extraction output in the UI. |
| `test_architecture.py` | `tests/test_architecture.py` | Guards against services importing adapters or infrastructure packages. |

Run the entire suite with `pytest` or focus on extraction-related tests:

```bash
pytest tests/test_pdf_parser.py tests/test_services.py -k extraction
```

---

## Observability and Metadata

- `ExtractionService` emits `stage="extraction"` events through the injected `ObservabilityRecorder`. In production the `LoggingObservabilityRecorder` prints JSON, while tests inject `NullObservabilityRecorder` or a stub to assert emitted payloads.
- Telemetry includes the parser name (`parser_used`), total page count, and a preview per page (first 500 characters). This data flows directly into the dashboard stage cards.
- When no parser is available, the service indicates `parser_used="placeholder"` so operators immediately understand why the output looks synthetic.

---

## Verification Checklist

- [ ] Parser implements `DocumentParser` and handles errors gracefully.
- [ ] `ExtractionService` changes (if any) keep the API and immutability guarantees intact.
- [ ] Container wiring instantiates the new adapter and passes it into the service.
- [ ] Unit tests (`tests/test_pdf_parser.py` or equivalent) cover success + failure modes.
- [ ] Service tests exercise the new parser in context.
- [ ] `tests/test_architecture.py` passes (no forbidden imports in services/domain).
- [ ] Documentation updated (`docs/Extraction_Service_Implementation_Guide.md`, `docs/ARCHITECTURE.md`, README if directory structure changed).

---

## Reference Files

- `src/app/services/extraction_service.py`
- `src/app/adapters/pdf_parser.py`
- `src/app/container.py`
- `tests/test_pdf_parser.py`
- `tests/test_services.py`
- `docs/ARCHITECTURE.md`
- `README.md`
