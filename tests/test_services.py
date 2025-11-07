from __future__ import annotations

from pathlib import Path

from src.app.application.interfaces import NullObservabilityRecorder
from src.app.domain.models import Document
from src.app.persistence.adapters.ingestion_filesystem import FileSystemIngestionRepository
from src.app.services.chunking_service import ChunkingService
from src.app.services.cleaning_service import CleaningService
from src.app.services.enrichment_service import EnrichmentService
from src.app.services.extraction_service import ExtractionService
from src.app.services.ingestion_service import IngestionService
from src.app.services.pipeline_runner import PipelineRunner
from src.app.services.vector_service import VectorService


def build_document() -> Document:
    return Document(filename="sample.pdf", file_type="pdf", size_bytes=1024)


def build_null_observability() -> NullObservabilityRecorder:
    return NullObservabilityRecorder()


def test_ingestion_updates_status():
    service = IngestionService(observability=build_null_observability())
    document = build_document()
    updated = service.ingest(document)
    assert updated.status == "ingested"
    assert "ingested_at" in updated.metadata


def test_ingestion_persists_raw_file(tmp_path):
    repository = FileSystemIngestionRepository(tmp_path)
    service = IngestionService(repository=repository, observability=build_null_observability())
    document = build_document()
    raw_payload = b"Example PDF bytes"

    updated = service.ingest(document, file_bytes=raw_payload)

    stored_path = Path(updated.metadata["raw_file_path"])
    assert stored_path.exists()
    assert stored_path.read_bytes() == raw_payload
    assert updated.metadata["raw_file_checksum"]


def test_extraction_creates_pages():
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    document = extraction.extract(ingestion.ingest(build_document()))
    assert document.pages
    assert document.pages[0].text


def test_extraction_uses_parser_with_file_bytes():
    class StubParser:
        def supports_type(self, file_type: str) -> bool:
            return True

        def parse(self, file_bytes: bytes, filename: str) -> list[str]:
            return ["Page One", "Page Two"]

    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(parsers=[StubParser()], observability=observability)
    document = ingestion.ingest(build_document())

    result = extraction.extract(document, file_bytes=b"payload")
    assert len(result.pages) == 2
    assert result.pages[0].text == "Page One"


def test_extraction_reads_from_stored_path(tmp_path):
    class PathParser:
        def supports_type(self, file_type: str) -> bool:
            return True

        def parse(self, file_bytes: bytes, filename: str) -> list[str]:
            return [file_bytes.decode("utf-8")]

    parser = PathParser()
    extraction = ExtractionService(parsers=[parser], observability=build_null_observability())
    document = build_document()
    stored = tmp_path / "doc.pdf"
    stored.write_bytes(b"Stored bytes")
    document = document.model_copy(update={"metadata": {**document.metadata, "raw_file_path": str(stored)}})

    result = extraction.extract(document)
    assert result.pages[0].text == "Stored bytes"


def test_chunking_generates_chunks():
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    chunking = ChunkingService(observability=observability)

    document = chunking.chunk(extraction.extract(ingestion.ingest(build_document())), size=50, overlap=10)
    page = document.pages[0]
    assert page.chunks
    assert page.chunks[0].metadata is not None
    assert page.chunks[0].metadata.start_offset == 0


def test_enrichment_adds_summary_and_document_summary():
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    chunking = ChunkingService(observability=observability)
    enrichment = EnrichmentService(observability=observability)

    document = enrichment.enrich(
        chunking.chunk(extraction.extract(ingestion.ingest(build_document())), size=30, overlap=5)
    )

    chunk = document.pages[0].chunks[0]
    assert chunk.metadata is not None
    assert chunk.metadata.summary
    assert document.summary


def test_enrichment_uses_summary_generator():
    class StubSummaryGenerator:
        def summarize(self, text: str) -> str:
            return "stub-summary"

    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    chunking = ChunkingService(observability=observability)
    enrichment = EnrichmentService(summary_generator=StubSummaryGenerator(), observability=observability)

    document = enrichment.enrich(
        chunking.chunk(extraction.extract(ingestion.ingest(build_document())), size=30, overlap=5)
    )

    chunk = document.pages[0].chunks[0]
    assert chunk.metadata is not None
    assert chunk.metadata.summary == "stub-summary"


def test_cleaning_normalizes_text():
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    cleaning = CleaningService(observability=observability)

    document = extraction.extract(ingestion.ingest(build_document()))
    # Create a new document with updated page text
    updated_page = document.pages[0].model_copy(update={"text": "Hello   world"})
    document = document.model_copy(update={"pages": [updated_page]})
    document = cleaning.clean(document)
    page = document.pages[0]
    assert document.status == "cleaned"
    assert page.text == "Hello   world"
    assert page.cleaned_text == "Hello world"
    assert all("  " not in (p.cleaned_text or "") for p in document.pages)
    assert "cleaning_report" in document.metadata


def test_vectorization_attaches_vectors():
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    cleaning = CleaningService(observability=observability)
    chunking = ChunkingService(observability=observability)
    vectorization = VectorService(dimension=4, observability=observability)

    document = vectorization.vectorize(
        chunking.chunk(cleaning.clean(extraction.extract(ingestion.ingest(build_document()))))
    )

    chunk = document.pages[0].chunks[0]
    assert chunk.metadata is not None
    assert "vector" in chunk.metadata.extra
    assert len(chunk.metadata.extra["vector"]) == 4


class StubObservabilityRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def record_event(self, stage: str, details: dict | None = None) -> None:
        self.events.append((stage, details or {}))


def test_ingestion_emits_observability_event():
    recorder = StubObservabilityRecorder()
    service = IngestionService(observability=recorder)
    document = build_document()
    service.ingest(document)
    assert any(stage == "ingestion" for stage, _ in recorder.events)


def test_pipeline_runner_emits_completion_event():
    recorder = StubObservabilityRecorder()
    ingestion = IngestionService(observability=recorder)
    extraction = ExtractionService(observability=recorder)
    cleaning = CleaningService(observability=recorder)
    chunking = ChunkingService(observability=recorder)
    enrichment = EnrichmentService(observability=recorder)
    vectorization = VectorService(observability=recorder)
    runner = PipelineRunner(
        ingestion=ingestion,
        extraction=extraction,
        cleaning=cleaning,
        chunking=chunking,
        enrichment=enrichment,
        vectorization=vectorization,
        observability=recorder,
    )
    runner.run(build_document())
    assert any(stage == "pipeline_complete" for stage, _ in recorder.events)


# Dependency Injection Tests
def test_services_require_observability_parameter():
    """Test that services require observability parameter (no default)."""
    import pytest

    with pytest.raises(TypeError):
        IngestionService()  # Missing required observability parameter

    with pytest.raises(TypeError):
        ExtractionService()  # Missing required observability parameter

    with pytest.raises(TypeError):
        CleaningService()  # Missing required observability parameter

    with pytest.raises(TypeError):
        ChunkingService()  # Missing required observability parameter

    with pytest.raises(TypeError):
        EnrichmentService()  # Missing required observability parameter

    with pytest.raises(TypeError):
        VectorService()  # Missing required observability parameter


def test_services_accept_observability_interface():
    """Test that services accept any ObservabilityRecorder implementation."""
    recorder = StubObservabilityRecorder()
    service = IngestionService(observability=recorder)
    assert service.observability is recorder

    null_recorder = NullObservabilityRecorder()
    service2 = IngestionService(observability=null_recorder)
    assert service2.observability is null_recorder


# Immutability Tests
def test_ingestion_returns_new_instance():
    """Test that IngestionService returns a new Document instance."""
    service = IngestionService(observability=build_null_observability())
    original = build_document()
    result = service.ingest(original)
    assert result is not original
    assert original.status == "created"
    assert result.status == "ingested"


def test_cleaning_returns_new_instance():
    """Test that CleaningService returns a new Document instance."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    cleaning = CleaningService(observability=observability)

    document = extraction.extract(ingestion.ingest(build_document()))
    original = document
    result = cleaning.clean(document)
    assert result is not original
    assert original.pages[0].cleaned_text is None
    assert result.pages[0].cleaned_text is not None


def test_enrichment_returns_new_instance():
    """Test that EnrichmentService returns a new Document instance."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    chunking = ChunkingService(observability=observability)
    enrichment = EnrichmentService(observability=observability)

    document = chunking.chunk(extraction.extract(ingestion.ingest(build_document())), size=30, overlap=5)
    original = document
    result = enrichment.enrich(document)
    assert result is not original
    assert original.summary is None or original.summary != result.summary


def test_vectorization_returns_new_instance():
    """Test that VectorService returns a new Document instance."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    cleaning = CleaningService(observability=observability)
    chunking = ChunkingService(observability=observability)
    vectorization = VectorService(observability=observability)

    document = chunking.chunk(cleaning.clean(extraction.extract(ingestion.ingest(build_document()))))
    original = document
    result = vectorization.vectorize(document)
    assert result is not original
    assert original.status != "vectorized"
    assert result.status == "vectorized"


def test_extraction_returns_new_instance():
    """Test that ExtractionService returns a new Document instance."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)

    document = ingestion.ingest(build_document())
    original = document
    result = extraction.extract(document)
    assert result is not original
    assert len(original.pages) == 0
    assert len(result.pages) > 0


def test_chunking_returns_new_instance():
    """Test that ChunkingService returns a new Document instance."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    chunking = ChunkingService(observability=observability)

    document = extraction.extract(ingestion.ingest(build_document()))
    original = document
    result = chunking.chunk(document)
    assert result is not original
    assert len(original.pages[0].chunks) == 0
    assert len(result.pages[0].chunks) > 0


def test_document_add_page_returns_new_instance():
    """Test that Document.add_page() returns a new Document instance."""
    from src.app.domain.models import Page

    document = build_document()
    page = Page(document_id=document.id, page_number=1, text="Test")
    original = document
    result = document.add_page(page)
    assert result is not original
    assert len(original.pages) == 0
    assert len(result.pages) == 1


def test_document_add_chunk_returns_new_instance():
    """Test that Document.add_chunk() returns a new Document instance."""
    from src.app.domain.models import Chunk, Page

    document = build_document()
    page = Page(document_id=document.id, page_number=1, text="Test")
    document = document.add_page(page)
    chunk = Chunk(document_id=document.id, page_number=1, text="Chunk", start_offset=0, end_offset=5)
    original = document
    result = document.add_chunk(1, chunk)
    assert result is not original
    assert len(original.pages[0].chunks) == 0
    assert len(result.pages[0].chunks) == 1
