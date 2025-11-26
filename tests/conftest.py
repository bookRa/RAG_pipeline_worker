from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env file if it exists (needed to check RUN_RAG_TESTS and RUN_CONTRACT_TESTS)
# This ensures environment variables from .env are available before we decide whether to use mocks
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=False)

RUN_CONTRACT_TESTS = os.getenv("RUN_CONTRACT_TESTS") == "1"
RUN_RAG_TESTS = os.getenv("RUN_RAG_TESTS") == "1"

# Only use mocks if neither contract tests nor RAG tests are enabled
USE_MOCKS = not RUN_CONTRACT_TESTS and not RUN_RAG_TESTS

if USE_MOCKS:
    # Force mock providers *before* any application modules are imported so the
    # container never wires real LLMs during unit tests.
    os.environ["LLM__PROVIDER"] = "mock"
    os.environ["EMBEDDINGS__PROVIDER"] = "mock"
    os.environ.setdefault("CHUNKING__INCLUDE_IMAGES", "false")
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("LLM__API_KEY", None)


@pytest.fixture(autouse=True, scope="session")
def configure_mock_llm_env():
    """Force mock providers in tests unless contract tests or RAG tests are requested."""

    if not USE_MOCKS:
        return

    os.environ.setdefault("LLM__PROVIDER", "mock")
    os.environ.setdefault("EMBEDDINGS__PROVIDER", "mock")
    os.environ.setdefault("CHUNKING__INCLUDE_IMAGES", "false")
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("LLM__API_KEY", None)
