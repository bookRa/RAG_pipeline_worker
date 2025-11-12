from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def configure_mock_llm_env():
    """Force mock providers in tests unless contract tests are requested."""

    if os.getenv("RUN_CONTRACT_TESTS"):
        return

    os.environ.setdefault("LLM__PROVIDER", "mock")
    os.environ.setdefault("EMBEDDINGS__PROVIDER", "mock")
    os.environ.setdefault("CHUNKING__INCLUDE_IMAGES", "false")
