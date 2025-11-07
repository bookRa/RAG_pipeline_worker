from src.app.domain.models import Document
from src.app.services.chunking_service import ChunkingService
from src.app.services.enrichment_service import EnrichmentService
from src.app.services.extraction_service import ExtractionService
from src.app.services.ingestion_service import IngestionService


def build_document() -> Document:
    return Document(filename="sample.pdf", file_type="pdf", size_bytes=1024)


def test_ingestion_updates_status():
    service = IngestionService()
    document = build_document()
    updated = service.ingest(document)
    assert updated.status == "ingested"
    assert "ingested_at" in updated.metadata


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
