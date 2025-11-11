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
    timeout_seconds: float = 60.0
    max_retries: int = 2
    use_structured_outputs: bool = True


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

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="allow",
    )


settings = Settings()
