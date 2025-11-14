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

    provider: Literal["openai", "internal", "mock"] = "openai"
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


class EmbeddingSettings(BaseModel):
    """Configuration for embedding/vector generation."""

    provider: Literal["openai", "internal", "mock"] = "openai"
    model: str = "text-embedding-3-small"
    batch_size: int = 32
    vector_dimension: int = 1536
    store_target: Literal["in_memory", "llama_index_local", "documentdb"] = "llama_index_local"
    cache_enabled: bool = True


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


class Settings(BaseSettings):
    """Global application configuration."""

    app_name: str = "RAG Document Pipeline"
    llm: LLMSettings = LLMSettings()
    embeddings: EmbeddingSettings = EmbeddingSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    vector_store: VectorStoreSettings = VectorStoreSettings()
    prompts: PromptSettings = PromptSettings()
    
    # NEW: Pipeline improvement settings
    use_vision_cleaning: bool = False  # Enable vision-based cleaning (requires vision-capable LLM)
    use_llm_summarization: bool = True  # Enable LLM-based document/chunk summarization

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="allow",
    )


settings = Settings()
