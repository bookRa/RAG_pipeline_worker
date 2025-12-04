from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH, override=False)


class LLMSettings(BaseModel):
    """Configuration for the primary LLM provider."""

    provider: Literal["openai", "bcai", "internal", "mock"] = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.1
    max_output_tokens: int = 256
    api_base: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    timeout_seconds: float = 120.0
    max_retries: int = 2
    use_structured_outputs: bool = True
    use_responses_api: bool = True
    use_streaming: bool = True
    
    # Streaming guardrails to prevent infinite loops
    streaming_max_chars: int = 50000  # Stop streaming after this many characters
    streaming_repetition_window: int = 200  # Check last N chars for repetition
    streaming_repetition_threshold: float = 0.8  # Stop if >X% same character
    streaming_max_consecutive_newlines: int = 100  # Stop if N+ consecutive \n
    
    # BCAI-specific settings (optional, only used when provider="bcai")
    conversation_mode: str = "non-rag"  # BCAI conversation mode ("non-rag" or a RAG name)
    conversation_source: str = "rag-pipeline-worker"  # System identifier for BCAI tracking


class EmbeddingSettings(BaseModel):
    """Configuration for embedding/vector generation."""

    provider: Literal["openai", "bcai", "internal", "mock"] = "openai"
    model: str = "text-embedding-3-small"
    batch_size: int = 32
    vector_dimension: int = 1536
    store_target: Literal["in_memory", "llama_index_local", "documentdb"] = "llama_index_local"
    cache_enabled: bool = True
    
    # Optional API credentials (can inherit from LLM settings for BCAI)
    api_key: str | None = Field(default=None, repr=False)
    api_base: str | None = None
    
    # BCAI-specific: Optional dimensions override (for text-embedding-3 models)
    dimensions: int | None = None


class ChunkingSettings(BaseModel):
    """Controls chunking/node parsing defaults."""

    splitter: Literal["sentence", "token", "semantic"] = "sentence"
    chunk_size: int = 512
    chunk_overlap: int = 50
    include_images: bool = False
    metadata_strategy: Literal["inherit", "custom"] = "inherit"
    pixmap_dpi: int = 300
    pixmap_storage_dir: Path = Path("artifacts/pixmaps")
    max_pixmap_bytes: int = 8_000_000
    pixmap_max_width: int = 1536
    pixmap_max_height: int = 1536
    pixmap_resize_quality: str = "LANCZOS"
    
    # NEW: Component-aware chunking settings
    strategy: Literal["component", "hybrid", "fixed"] = "component"
    component_merge_threshold: int = 100  # Merge components under this token count
    max_component_tokens: int = 500  # Split components over this token count


class VectorStoreSettings(BaseModel):
    """Defines where chunk vectors are persisted."""

    driver: Literal["in_memory", "llama_index_local", "documentdb"] = "llama_index_local"
    persist_dir: Path = Path("artifacts/vector_store")
    documentdb_uri: str | None = None
    documentdb_database: str | None = None
    documentdb_collection: str = "pipeline_vectors"
    recreate_on_start: bool = False


class PromptSettings(BaseModel):
    """File paths for system/user prompts used in parsing & cleaning."""

    parsing_system_prompt_path: Path = Path("docs/prompts/parsing/system.md")
    parsing_user_prompt_path: Path = Path("docs/prompts/parsing/user.md")
    cleaning_system_prompt_path: Path = Path("docs/prompts/cleaning/system.md")
    cleaning_user_prompt_path: Path = Path("docs/prompts/cleaning/user.md")
    summary_prompt_path: Path = Path("docs/prompts/summarization/system.md")


class BatchProcessingSettings(BaseModel):
    """Configuration for batch and parallel processing."""

    max_concurrent_documents: int = 5
    max_workers_per_document: int = 4
    enable_page_parallelism: bool = True
    enable_document_parallelism: bool = True
    rate_limit_requests_per_minute: int = 60
    batch_artifacts_dir: Path = Path("artifacts/batches")
    pixmap_parallel_workers: int | None = None  # Defaults to CPU count


class LangfuseSettings(BaseModel):
    """Configuration for Langfuse observability and tracing."""

    enabled: bool = False
    public_key: str = ""
    secret_key: str = ""
    host: str = "https://cloud.langfuse.com"


class Settings(BaseSettings):
    """Global application configuration."""

    app_name: str = "RAG Document Pipeline"
    llm: LLMSettings = LLMSettings()
    embeddings: EmbeddingSettings = EmbeddingSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    vector_store: VectorStoreSettings = VectorStoreSettings()
    prompts: PromptSettings = PromptSettings()
    batch: BatchProcessingSettings = BatchProcessingSettings()
    langfuse: LangfuseSettings = LangfuseSettings()
    
    # NEW: Pipeline improvement settings
    use_vision_cleaning: bool = False  # Enable vision-based cleaning (requires vision-capable LLM)
    use_llm_summarization: bool = True  # Enable LLM-based document/chunk summarization
    
    # Langfuse observability settings
    enable_langfuse: bool = Field(default=False)
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="", repr=False)
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="allow",
    )


settings = Settings()
