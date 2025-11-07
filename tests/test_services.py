from pathlib import Path

from src.app.domain.models import Document
from src.app.persistence.adapters.ingestion_filesystem import FileSystemIngestionRepository
from src.app.services.chunking_service import ChunkingService
from src.app.services.cleaning_service import CleaningService
from src.app.services.enrichment_service import EnrichmentService
from src.app.services.extraction_service import ExtractionService
from src.app.services.ingestion_service import IngestionService
from src.app.services.vector_service import VectorService


def build_document() -> Document:
    return Document(filename="sample.pdf", file_type="pdf", size_bytes=1024)


def test_ingestion_updates_status():
    service = IngestionService()
    document = build_document()
    updated = service.ingest(document)
    assert updated.status == "ingested"
    assert "ingested_at" in updated.metadata


def test_ingestion_persists_raw_file(tmp_path):
    repository = FileSystemIngestionRepository(tmp_path)
    service = IngestionService(repository=repository)
    document = build_document()
    raw_payload = b"Example PDF bytes"

    updated = service.ingest(document, file_bytes=raw_payload)

    stored_path = Path(updated.metadata["raw_file_path"])
    assert stored_path.exists()
    assert stored_path.read_bytes() == raw_payload
    assert updated.metadata["raw_file_checksum"]


def test_extraction_creates_pages():
    ingestion = IngestionService()
    extraction = ExtractionService()
    document = extraction.extract(ingestion.ingest(build_document()))
    assert document.pages
    assert document.pages[0].text


def test_chunking_generates_chunks():
    ingestion = IngestionService()
    extraction = ExtractionService()
    chunking = ChunkingService()

    document = chunking.chunk(extraction.extract(ingestion.ingest(build_document())), size=50, overlap=10)
    page = document.pages[0]
    assert page.chunks
    assert page.chunks[0].metadata is not None
    assert page.chunks[0].metadata.start_offset == 0


def test_enrichment_adds_summary_and_document_summary():
    ingestion = IngestionService()
    extraction = ExtractionService()
    chunking = ChunkingService()
    enrichment = EnrichmentService()

    document = enrichment.enrich(
        chunking.chunk(extraction.extract(ingestion.ingest(build_document())), size=30, overlap=5)
    )

    chunk = document.pages[0].chunks[0]
    assert chunk.metadata is not None
    assert chunk.metadata.summary
    assert document.summary


def test_cleaning_normalizes_text():
    ingestion = IngestionService()
    extraction = ExtractionService()
    cleaning = CleaningService()

    document = extraction.extract(ingestion.ingest(build_document()))
    document.pages[0].text = "Hello   world"
    document = cleaning.clean(document)
    page = document.pages[0]
    assert document.status == "cleaned"
    assert page.text == "Hello   world"
    assert page.cleaned_text == "Hello world"
    assert all("  " not in (p.cleaned_text or "") for p in document.pages)
    assert "cleaning_report" in document.metadata


def test_vectorization_attaches_vectors():
    ingestion = IngestionService()
    extraction = ExtractionService()
    cleaning = CleaningService()
    chunking = ChunkingService()
    vectorization = VectorService(dimension=4)

    document = vectorization.vectorize(
        chunking.chunk(cleaning.clean(extraction.extract(ingestion.ingest(build_document()))))
    )

    chunk = document.pages[0].chunks[0]
    assert chunk.metadata is not None
    assert "vector" in chunk.metadata.extra
    assert len(chunk.metadata.extra["vector"]) == 4
