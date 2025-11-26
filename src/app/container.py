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
    get_llama_multi_modal_llm,
)
from .adapters.llama_index.cleaning_adapter import CleaningAdapter
from .adapters.llama_index.parsing_adapter import ImageAwareParsingAdapter
from .adapters.llama_index.summary_adapter import LlamaIndexSummaryAdapter
from .adapters.llama_index.embedding_adapter import LlamaIndexEmbeddingAdapter
from .persistence.adapters.document_filesystem import FileSystemDocumentRepository
from .persistence.adapters.filesystem import FileSystemPipelineRunRepository
from .persistence.adapters.ingestion_filesystem import FileSystemIngestionRepository
from .observability.logger import LoggingObservabilityRecorder
from .observability.langfuse_handler import PipelineLangfuseHandler
from .application.use_cases import GetDocumentUseCase, ListDocumentsUseCase, UploadDocumentUseCase
from .services.chunking_service import ChunkingService
from .services.cleaning_service import CleaningService
from .services.enrichment_service import EnrichmentService
from .services.parsing_service import ParsingService
from .services.ingestion_service import IngestionService
from .services.pipeline_runner import PipelineRunner
from .services.run_manager import PipelineRunManager
from .services.vector_service import VectorService
from .vector_store import DocumentDBVectorStore, InMemoryVectorStore


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
        pixmap_dir = Path(
            os.getenv("PIXMAP_STORAGE_DIR", self.settings.chunking.pixmap_storage_dir)
        ).resolve()
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
        self.langfuse_handler = None  # Will be set if Langfuse is enabled

        self.ingestion_service = IngestionService(
            observability=self.observability,
            latency=stage_latency,
            repository=self.ingestion_repository,
        )
        try:
            configure_llama_index(self.settings)
            
            # Setup Langfuse callback handler if enabled
            if self.settings.enable_langfuse:
                try:
                    from llama_index.core import Settings as LlamaIndexSettings
                    from llama_index.core.callbacks import CallbackManager
                    
                    langfuse_handler = PipelineLangfuseHandler(
                        public_key=self.settings.langfuse_public_key,
                        secret_key=self.settings.langfuse_secret_key,
                        host=self.settings.langfuse_host,
                    )
                    
                    # Get existing callback manager or create new one
                    existing_manager = LlamaIndexSettings.callback_manager
                    handlers = []
                    if existing_manager and existing_manager.handlers:
                        handlers.extend(existing_manager.handlers)
                    handlers.append(langfuse_handler)
                    
                    # Set global callback manager with Langfuse handler
                    LlamaIndexSettings.callback_manager = CallbackManager(handlers)
                    
                    # Store handler reference for custom traces
                    self.langfuse_handler = langfuse_handler
                    logger.info("Langfuse callback handler initialized")
                except ImportError as exc:
                    logger.warning("Langfuse packages not installed. Install 'langfuse' and 'llama-index-callbacks-langfuse' to enable tracing: %s", exc)
                except Exception as exc:
                    logger.warning("Failed to initialize Langfuse callback handler: %s", exc)
            
            llm_client = get_llama_llm()
            embed_model = get_llama_embedding_model()
            self.text_splitter = get_llama_text_splitter()
            # Use the same OpenAI LLM (GPT-4o-mini) for both text and vision
            # GPT-4o-mini supports vision through ChatMessage with image content
            self.structured_parser = ImageAwareParsingAdapter(
                llm=llm_client,
                prompt_settings=self.settings.prompts,
                vision_llm=None,  # Use same LLM for vision
                use_structured_outputs=self.settings.llm.use_structured_outputs,
                use_streaming=self.settings.llm.use_streaming,
                streaming_max_chars=self.settings.llm.streaming_max_chars,
                streaming_repetition_window=self.settings.llm.streaming_repetition_window,
                streaming_repetition_threshold=self.settings.llm.streaming_repetition_threshold,
                streaming_max_consecutive_newlines=self.settings.llm.streaming_max_consecutive_newlines,
            )
            self.structured_cleaner = CleaningAdapter(
                llm=llm_client,
                prompt_settings=self.settings.prompts,
                use_structured_outputs=self.settings.llm.use_structured_outputs,
                use_vision=self.settings.use_vision_cleaning,  # NEW: Vision-based cleaning
            )
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
            include_images=self.settings.chunking.include_images,
            pixmap_dir=pixmap_dir,
            pixmap_dpi=self.settings.chunking.pixmap_dpi,
            max_pixmap_bytes=self.settings.chunking.max_pixmap_bytes,
            pixmap_max_width=self.settings.chunking.pixmap_max_width,
            pixmap_max_height=self.settings.chunking.pixmap_max_height,
            pixmap_resize_quality=self.settings.chunking.pixmap_resize_quality,
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
            strategy=self.settings.chunking.strategy,  # NEW: Component-aware chunking
            component_merge_threshold=self.settings.chunking.component_merge_threshold,
            max_component_tokens=self.settings.chunking.max_component_tokens,
        )
        self.enrichment_service = EnrichmentService(
            observability=self.observability,
            latency=stage_latency,
            summary_generator=self.summary_generator,
            use_llm_summarization=self.settings.use_llm_summarization,  # NEW: LLM-based summarization
        )
        
        # Initialize vector store based on configuration
        self.vector_store = self._create_vector_store()
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
            langfuse_handler=self.langfuse_handler,
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

    def _create_vector_store(self):
        """
        Factory method to create vector store adapter based on configuration.
        
        Returns:
            VectorStoreAdapter instance (InMemoryVectorStore or DocumentDBVectorStore)
        """
        driver = self.settings.vector_store.driver
        
        if driver == "documentdb":
            logger.info("Initializing DocumentDB vector store")
            try:
                return DocumentDBVectorStore(
                    uri=self.settings.vector_store.documentdb_uri,
                    database_name=self.settings.vector_store.documentdb_database,
                    collection_name=self.settings.vector_store.documentdb_collection,
                    vector_dimension=self.settings.embeddings.vector_dimension,
                )
            except ValueError as exc:
                logger.error(
                    "Failed to initialize DocumentDB vector store: %s. Falling back to in-memory store.",
                    exc,
                )
                return InMemoryVectorStore()
        elif driver == "in_memory":
            logger.info("Using in-memory vector store")
            return InMemoryVectorStore()
        else:
            logger.warning(
                "Unknown vector store driver '%s', falling back to in-memory store",
                driver,
            )
            return InMemoryVectorStore()


@lru_cache
def get_app_container() -> AppContainer:
    """Return a cached container instance so FastAPI dependencies share services."""

    return AppContainer()
