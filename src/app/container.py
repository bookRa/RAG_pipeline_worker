from __future__ import annotations

import os
import logging
from functools import lru_cache
from pathlib import Path

from .config import settings
from .adapters.docx_parser import DocxParserAdapter
from .adapters.llm_client import LLMSummaryAdapter
from .adapters.pdf_parser import PdfParserAdapter
from .adapters.ppt_parser import PptParserAdapter
from .adapters.llama_index.bootstrap import (
    LlamaIndexBootstrapError,
    configure_llama_index,
    get_llama_llm,
    get_llama_text_splitter,
    get_llama_embedding_model,
)
from .adapters.llama_index.cleaning_adapter import CleaningAdapter
from .adapters.llama_index.parsing_adapter import ImageAwareParsingAdapter
from .adapters.llama_index.summary_adapter import LlamaIndexSummaryAdapter
from .adapters.llama_index.embedding_adapter import LlamaIndexEmbeddingAdapter
from .persistence.adapters.document_filesystem import FileSystemDocumentRepository
from .persistence.adapters.filesystem import FileSystemPipelineRunRepository
from .persistence.adapters.ingestion_filesystem import FileSystemIngestionRepository
from .observability.logger import LoggingObservabilityRecorder
from .application.use_cases import GetDocumentUseCase, ListDocumentsUseCase, UploadDocumentUseCase
from .services.chunking_service import ChunkingService
from .services.cleaning_service import CleaningService
from .services.enrichment_service import EnrichmentService
from .services.parsing_service import ParsingService
from .services.ingestion_service import IngestionService
from .services.pipeline_runner import PipelineRunner
from .services.run_manager import PipelineRunManager
from .services.vector_service import VectorService
from .vector_store import InMemoryVectorStore


logger = logging.getLogger(__name__)


class AppContainer:
    """Application composition root wiring services, repositories, and adapters."""

    def __init__(self) -> None:
        stage_latency = float(os.getenv("PIPELINE_STAGE_LATENCY", "0.05"))
        self.settings = settings
        base_dir = Path(__file__).resolve().parents[2]
        ingestion_storage_dir = Path(
            os.getenv("INGESTION_STORAGE_DIR", base_dir / "artifacts" / "ingestion")
        ).resolve()
        self.ingestion_repository = FileSystemIngestionRepository(ingestion_storage_dir)
        documents_dir = Path(os.getenv("DOCUMENT_STORAGE_DIR", base_dir / "artifacts" / "documents")).resolve()
        self.document_repository = FileSystemDocumentRepository(documents_dir)
        self.document_parsers = [
            PdfParserAdapter(),
            DocxParserAdapter(),
            PptParserAdapter(),
        ]
        self.summary_generator = LLMSummaryAdapter()
        self.embedding_generator = None
        self.structured_parser = None
        self.structured_cleaner = None
        self.text_splitter = None

        self.observability = LoggingObservabilityRecorder()

        self.ingestion_service = IngestionService(
            observability=self.observability,
            latency=stage_latency,
            repository=self.ingestion_repository,
        )
        try:
            configure_llama_index(self.settings)
            llm_client = get_llama_llm()
            embed_model = get_llama_embedding_model()
            self.text_splitter = get_llama_text_splitter()
            self.structured_parser = ImageAwareParsingAdapter(llm=llm_client, prompt_settings=self.settings.prompts)
            self.structured_cleaner = CleaningAdapter(llm=llm_client, prompt_settings=self.settings.prompts)
            self.summary_generator = LlamaIndexSummaryAdapter(llm=llm_client, prompt_settings=self.settings.prompts)
            self.embedding_generator = LlamaIndexEmbeddingAdapter(
                embed_model=embed_model,
                dimension=self.settings.embeddings.vector_dimension,
            )
        except LlamaIndexBootstrapError as exc:
            logger.warning("LlamaIndex not configured, falling back to stubbed pipeline: %s", exc)
            self.embedding_generator = None

        self.parsing_service = ParsingService(
            observability=self.observability,
            latency=stage_latency,
            parsers=self.document_parsers,
            structured_parser=self.structured_parser,
        )
        self.cleaning_service = CleaningService(
            observability=self.observability,
            latency=stage_latency,
            structured_cleaner=self.structured_cleaner,
        )
        self.chunking_service = ChunkingService(
            observability=self.observability,
            latency=stage_latency,
            chunk_size=self.settings.chunking.chunk_size,
            chunk_overlap=self.settings.chunking.chunk_overlap,
            text_splitter=self.text_splitter,
        )
        self.enrichment_service = EnrichmentService(
            observability=self.observability,
            latency=stage_latency,
            summary_generator=self.summary_generator,
        )
        self.vector_store = InMemoryVectorStore()
        self.vector_service = VectorService(
            observability=self.observability,
            latency=stage_latency,
            embedding_generator=self.embedding_generator,
            vector_store=self.vector_store,
        )

        artifacts_dir = Path(
            os.getenv("RUN_ARTIFACTS_DIR", base_dir / "artifacts" / "runs")
        ).resolve()
        self.run_repository = FileSystemPipelineRunRepository(artifacts_dir)

        self.pipeline_runner = PipelineRunner(
            ingestion=self.ingestion_service,
            parsing=self.parsing_service,
            cleaning=self.cleaning_service,
            chunking=self.chunking_service,
            enrichment=self.enrichment_service,
            vectorization=self.vector_service,
            observability=self.observability,
        )
        self.pipeline_run_manager = PipelineRunManager(
            self.run_repository,
            self.pipeline_runner,
            document_repository=self.document_repository,
        )

        # Use cases
        self.upload_document_use_case = UploadDocumentUseCase(
            runner=self.pipeline_runner,
            repository=self.document_repository,
        )
        self.list_documents_use_case = ListDocumentsUseCase(repository=self.document_repository)
        self.get_document_use_case = GetDocumentUseCase(repository=self.document_repository)


@lru_cache
def get_app_container() -> AppContainer:
    """Return a cached container instance so FastAPI dependencies share services."""

    return AppContainer()
