from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.app.application.interfaces import NullObservabilityRecorder
from src.app.application.use_cases import GetDocumentUseCase, ListDocumentsUseCase, UploadDocumentUseCase
from src.app.domain.models import Document
from src.app.persistence.adapters.document_filesystem import FileSystemDocumentRepository
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


def build_pipeline_runner() -> PipelineRunner:
    observability = build_null_observability()
    ingestion = IngestionService(observability=observability)
    extraction = ExtractionService(observability=observability)
    cleaning = CleaningService(observability=observability)
    chunking = ChunkingService(observability=observability)
    enrichment = EnrichmentService(observability=observability)
    vectorization = VectorService(observability=observability)
    return PipelineRunner(
        ingestion=ingestion,
        extraction=extraction,
        cleaning=cleaning,
        chunking=chunking,
        enrichment=enrichment,
        vectorization=vectorization,
        observability=observability,
    )


class TestUploadDocumentUseCase:
    def test_execute_validates_filename(self):
        runner = build_pipeline_runner()
        repository = FileSystemDocumentRepository("/tmp/test_docs")
        use_case = UploadDocumentUseCase(runner=runner, repository=repository)

        with pytest.raises(HTTPException) as exc_info:
            use_case.execute(filename="", file_type="pdf", file_bytes=b"content")
        assert exc_info.value.status_code == 400
        assert "Filename is required" in str(exc_info.value.detail)

    def test_execute_validates_file_type(self):
        runner = build_pipeline_runner()
        repository = FileSystemDocumentRepository("/tmp/test_docs")
        use_case = UploadDocumentUseCase(runner=runner, repository=repository)

        with pytest.raises(HTTPException) as exc_info:
            use_case.execute(filename="test.txt", file_type="txt", file_bytes=b"content")
        assert exc_info.value.status_code == 400
        assert "Unsupported file type" in str(exc_info.value.detail)

    def test_execute_processes_and_saves_document(self, tmp_path):
        runner = build_pipeline_runner()
        repository = FileSystemDocumentRepository(tmp_path)
        use_case = UploadDocumentUseCase(runner=runner, repository=repository)

        document = use_case.execute(
            filename="test.pdf",
            file_type="pdf",
            file_bytes=b"test content",
            content_type="application/pdf",
        )

        assert document.filename == "test.pdf"
        assert document.file_type == "pdf"
        assert document.status == "vectorized"  # Pipeline completes all stages
        assert document.id

        # Verify document was saved
        saved = repository.get(document.id)
        assert saved is not None
        assert saved.id == document.id

    def test_execute_handles_extension_extraction(self, tmp_path):
        runner = build_pipeline_runner()
        repository = FileSystemDocumentRepository(tmp_path)
        use_case = UploadDocumentUseCase(runner=runner, repository=repository)

        document = use_case.execute(
            filename="test.docx",
            file_type="",  # Empty, should extract from filename
            file_bytes=b"content",
        )

        assert document.file_type == "docx"


class TestListDocumentsUseCase:
    def test_execute_returns_all_documents(self, tmp_path):
        repository = FileSystemDocumentRepository(tmp_path)
        use_case = ListDocumentsUseCase(repository=repository)

        # Create and save some documents
        doc1 = build_document()
        doc2 = build_document()
        repository.save(doc1)
        repository.save(doc2)

        documents = use_case.execute()
        assert len(documents) == 2
        assert any(d.id == doc1.id for d in documents)
        assert any(d.id == doc2.id for d in documents)

    def test_execute_returns_empty_list_when_no_documents(self, tmp_path):
        repository = FileSystemDocumentRepository(tmp_path)
        use_case = ListDocumentsUseCase(repository=repository)

        documents = use_case.execute()
        assert documents == []


class TestGetDocumentUseCase:
    def test_execute_returns_document_when_found(self, tmp_path):
        repository = FileSystemDocumentRepository(tmp_path)
        use_case = GetDocumentUseCase(repository=repository)

        document = build_document()
        repository.save(document)

        result = use_case.execute(document.id)
        assert result.id == document.id
        assert result.filename == document.filename

    def test_execute_raises_when_not_found(self, tmp_path):
        repository = FileSystemDocumentRepository(tmp_path)
        use_case = GetDocumentUseCase(repository=repository)

        with pytest.raises(HTTPException) as exc_info:
            use_case.execute("non-existent-id")
        assert exc_info.value.status_code == 404
        assert "Document not found" in str(exc_info.value.detail)

