from __future__ import annotations

from pathlib import Path

import pytest

from src.app.adapters.pdf_parser import PdfParserAdapter
from src.app.application.interfaces import NullObservabilityRecorder
from src.app.domain.models import Document
from src.app.persistence.adapters.ingestion_filesystem import FileSystemIngestionRepository
from src.app.services.chunking_service import ChunkingService
from src.app.services.cleaning_service import CleaningService
from src.app.services.enrichment_service import EnrichmentService
from src.app.services.parsing_service import ParsingService
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
    service = IngestionService(observability=build_null_observability(), repository=repository)
    document = build_document()
    raw_payload = b"Example PDF bytes"

    updated = service.ingest(document, file_bytes=raw_payload)

    stored_path = Path(updated.metadata["raw_file_path"])
    assert stored_path.exists()
    assert stored_path.read_bytes() == raw_payload
    assert updated.metadata["raw_file_checksum"]


def test_parsing_creates_pages():
    """Test that parsing creates pages (may use placeholder if no parser provided)."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    document = parsing.parse(ingestion.ingest(build_document()))
    assert document.pages
    assert document.pages[0].text


def test_parsing_uses_parser_with_file_bytes():
    class StubParser:
        def supports_type(self, file_type: str) -> bool:
            return True

        def parse(self, file_bytes: bytes, filename: str) -> list[str]:
            return ["Page One", "Page Two"]

    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability, parsers=[StubParser()])
    document = ingestion.ingest(build_document())

    result = parsing.parse(document, file_bytes=b"payload")
    assert len(result.pages) == 2
    assert result.pages[0].text == "Page One"


def test_parsing_reads_from_stored_path(tmp_path):
    """Test that parsing can read file bytes from stored path using a stub parser."""
    class PathParser:
        def supports_type(self, file_type: str) -> bool:
            return True

        def parse(self, file_bytes: bytes, filename: str) -> list[str]:
            return [file_bytes.decode("utf-8")]

    parser = PathParser()
    parsing = ParsingService(observability=build_null_observability(), parsers=[parser])
    document = build_document()
    stored = tmp_path / "doc.pdf"
    stored.write_bytes(b"Stored bytes")
    document = document.model_copy(update={"metadata": {**document.metadata, "raw_file_path": str(stored)}})

    result = parsing.parse(document)
    assert result.pages[0].text == "Stored bytes"


def test_parsing_with_real_pdf_parser():
    """Test that parsing service works with the real PDF parser adapter."""
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    
    # Skip test if test PDF doesn't exist
    if not test_pdf_path.exists():
        pytest.skip(f"Test PDF not found at {test_pdf_path}")
    
    pdf_bytes = test_pdf_path.read_bytes()
    observability = build_null_observability()
    pdf_parser = PdfParserAdapter()
    parsing = ParsingService(observability=observability, parsers=[pdf_parser])
    ingestion = IngestionService(observability=observability)
    
    # Create document and ingest it
    document = build_document()
    document = ingestion.ingest(document, file_bytes=pdf_bytes)
    
    # Extract using real PDF parser
    result = parsing.parse(document, file_bytes=pdf_bytes)
    
    # Verify parsing succeeded
    assert result.status == "parsed"
    assert len(result.pages) == 10  # test_document.pdf has 10 pages
    
    # Verify pages have text content
    assert all(page.text is not None for page in result.pages)
    assert any(len(page.text) > 0 for page in result.pages)  # At least some pages have text


def test_parsing_with_real_pdf_parser_from_stored_path(tmp_path):
    """Test that parsing can read PDF from stored path using real PDF parser."""
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    
    # Skip test if test PDF doesn't exist
    if not test_pdf_path.exists():
        pytest.skip(f"Test PDF not found at {test_pdf_path}")
    
    pdf_bytes = test_pdf_path.read_bytes()
    observability = build_null_observability()
    pdf_parser = PdfParserAdapter()
    parsing = ParsingService(observability=observability, parsers=[pdf_parser])
    ingestion = IngestionService(
        observability=observability,
        repository=FileSystemIngestionRepository(tmp_path),
    )
    
    # Create document and ingest it (this stores the file)
    document = build_document()
    document = ingestion.ingest(document, file_bytes=pdf_bytes)
    
    # Extract without providing file_bytes - should read from stored path
    result = parsing.parse(document)
    
    # Verify parsing succeeded
    assert result.status == "parsed"
    assert len(result.pages) == 10  # test_document.pdf has 10 pages
    
    # Verify pages have text content
    assert all(page.text is not None for page in result.pages)


def test_chunking_generates_chunks():
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    chunking = ChunkingService(observability=observability)

    document = chunking.chunk(parsing.parse(ingestion.ingest(build_document())), size=50, overlap=10)
    page = document.pages[0]
    assert page.chunks
    assert page.chunks[0].metadata is not None
    assert page.chunks[0].metadata.start_offset == 0


def test_enrichment_adds_summary_and_document_summary():
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    chunking = ChunkingService(observability=observability)
    enrichment = EnrichmentService(observability=observability)

    document = enrichment.enrich(
        chunking.chunk(parsing.parse(ingestion.ingest(build_document())), size=30, overlap=5)
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
    parsing = ParsingService(observability=observability)
    chunking = ChunkingService(observability=observability)
    enrichment = EnrichmentService(observability=observability, summary_generator=StubSummaryGenerator())

    document = enrichment.enrich(
        chunking.chunk(parsing.parse(ingestion.ingest(build_document())), size=30, overlap=5)
    )

    chunk = document.pages[0].chunks[0]
    assert chunk.metadata is not None
    assert chunk.metadata.summary == "stub-summary"


def test_cleaning_normalizes_text():
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    cleaning = CleaningService(observability=observability)

    document = parsing.parse(ingestion.ingest(build_document()))
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


def test_cleaning_generates_segment_metadata():
    """Test that cleaning service generates segment-level metadata."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    cleaning = CleaningService(observability=observability, profile="test_profile")

    document = parsing.parse(ingestion.ingest(build_document()))
    updated_page = document.pages[0].model_copy(update={"text": "Hello   world"})
    document = document.model_copy(update={"pages": [updated_page]})
    document = cleaning.clean(document)
    
    # Verify cleaning metadata is stored by page number
    assert "cleaning_metadata_by_page" in document.metadata
    assert 1 in document.metadata["cleaning_metadata_by_page"]
    
    page_meta = document.metadata["cleaning_metadata_by_page"][1]
    assert "cleaned_tokens_count" in page_meta
    assert "diff_hash" in page_meta
    assert "cleaning_ops" in page_meta
    assert "needs_review" in page_meta
    assert "profile" in page_meta
    assert page_meta["profile"] == "test_profile"
    assert "whitespace" in page_meta["cleaning_ops"]


def test_chunking_preserves_raw_text_after_cleaning():
    """Test that chunking preserves raw text even when cleaning has run."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    cleaning = CleaningService(observability=observability)
    chunking = ChunkingService(observability=observability)

    document = parsing.parse(ingestion.ingest(build_document()))
    # Create page with raw text containing extra whitespace
    raw_text = "This   is   a   test   with   extra   spaces"
    updated_page = document.pages[0].model_copy(update={"text": raw_text})
    document = document.model_copy(update={"pages": [updated_page]})
    
    # Run cleaning first (this normalizes whitespace)
    document = cleaning.clean(document)
    assert document.pages[0].text == raw_text  # Raw text preserved
    assert document.pages[0].cleaned_text == "This is a test with extra spaces"  # Cleaned version
    
    # Run chunking (should preserve raw text in chunks)
    document = chunking.chunk(document, size=20, overlap=5)
    
    # Verify chunks preserve raw text
    chunk = document.pages[0].chunks[0]
    assert chunk.text == raw_text[:20]  # Raw text slice
    assert chunk.cleaned_text == "This is a test with"  # Cleaned slice
    assert chunk.text != chunk.cleaned_text  # They should differ
    assert "  " in chunk.text  # Raw text has extra spaces
    assert "  " not in chunk.cleaned_text  # Cleaned text normalized


def test_chunking_preserves_raw_text_without_cleaning():
    """Test that chunking works correctly when cleaning hasn't run."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    chunking = ChunkingService(observability=observability)

    document = parsing.parse(ingestion.ingest(build_document()))
    raw_text = "This is a test without cleaning"
    updated_page = document.pages[0].model_copy(update={"text": raw_text})
    document = document.model_copy(update={"pages": [updated_page]})
    
    # Run chunking without cleaning
    document = chunking.chunk(document, size=20, overlap=5)
    
    # Verify chunks have raw text, but no cleaned text
    chunk = document.pages[0].chunks[0]
    assert chunk.text == raw_text[:20]  # Raw text slice
    assert chunk.cleaned_text is None  # No cleaned text when cleaning hasn't run


def test_chunking_attaches_cleaning_metadata_to_chunks():
    """Test that chunking attaches cleaning metadata to chunks."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    cleaning = CleaningService(observability=observability, profile="test_profile")
    chunking = ChunkingService(observability=observability)

    document = parsing.parse(ingestion.ingest(build_document()))
    updated_page = document.pages[0].model_copy(update={"text": "Hello   world"})
    document = document.model_copy(update={"pages": [updated_page]})
    
    # Run cleaning to generate metadata
    document = cleaning.clean(document)
    
    # Run chunking to attach metadata to chunks
    document = chunking.chunk(document, size=20, overlap=5)
    
    # Verify cleaning metadata is attached to chunks
    chunk = document.pages[0].chunks[0]
    assert chunk.metadata is not None
    assert "cleaning" in chunk.metadata.extra
    
    cleaning_meta = chunk.metadata.extra["cleaning"]
    assert "segment_id" in cleaning_meta
    assert cleaning_meta["segment_id"] == chunk.id
    assert "cleaned_tokens_count" in cleaning_meta
    assert "diff_hash" in cleaning_meta
    assert "cleaning_ops" in cleaning_meta
    assert "needs_review" in cleaning_meta
    assert "profile" in cleaning_meta
    assert cleaning_meta["profile"] == "test_profile"


def test_vectorization_attaches_vectors():
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    cleaning = CleaningService(observability=observability)
    chunking = ChunkingService(observability=observability)
    vectorization = VectorService(observability=observability, dimension=4)

    document = vectorization.vectorize(
        chunking.chunk(cleaning.clean(parsing.parse(ingestion.ingest(build_document()))))
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
    parsing = ParsingService(observability=recorder)
    cleaning = CleaningService(observability=recorder)
    chunking = ChunkingService(observability=recorder)
    enrichment = EnrichmentService(observability=recorder)
    vectorization = VectorService(observability=recorder)
    runner = PipelineRunner(
        ingestion=ingestion,
        parsing=parsing,
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
        ParsingService()  # Missing required observability parameter

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
    parsing = ParsingService(observability=observability)
    cleaning = CleaningService(observability=observability)

    document = parsing.parse(ingestion.ingest(build_document()))
    original = document
    result = cleaning.clean(document)
    assert result is not original
    assert original.pages[0].cleaned_text is None
    assert result.pages[0].cleaned_text is not None


def test_enrichment_returns_new_instance():
    """Test that EnrichmentService returns a new Document instance."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    chunking = ChunkingService(observability=observability)
    enrichment = EnrichmentService(observability=observability)

    document = chunking.chunk(parsing.parse(ingestion.ingest(build_document())), size=30, overlap=5)
    original = document
    result = enrichment.enrich(document)
    assert result is not original
    assert original.summary is None or original.summary != result.summary


def test_vectorization_returns_new_instance():
    """Test that VectorService returns a new Document instance."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    cleaning = CleaningService(observability=observability)
    chunking = ChunkingService(observability=observability)
    vectorization = VectorService(observability=observability)

    document = chunking.chunk(cleaning.clean(parsing.parse(ingestion.ingest(build_document()))))
    original = document
    result = vectorization.vectorize(document)
    assert result is not original
    assert original.status != "vectorized"
    assert result.status == "vectorized"


def test_parsing_returns_new_instance():
    """Test that ParsingService returns a new Document instance."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)

    document = ingestion.ingest(build_document())
    original = document
    result = parsing.parse(document)
    assert result is not original
    assert len(original.pages) == 0
    assert len(result.pages) > 0


def test_chunking_returns_new_instance():
    """Test that ChunkingService returns a new Document instance."""
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    parsing = ParsingService(observability=observability)
    chunking = ChunkingService(observability=observability)

    document = parsing.parse(ingestion.ingest(build_document()))
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
