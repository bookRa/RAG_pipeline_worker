from __future__ import annotations

import os

import pytest
from llama_index.llms.openai import OpenAI

from src.app.adapters.llama_index.utils import extract_response_text

pytestmark = pytest.mark.contract


@pytest.mark.skipif(os.getenv("RUN_CONTRACT_TESTS") != "1", reason="Contract tests require RUN_CONTRACT_TESTS=1")
def test_openai_completion_contract():
    api_key = os.getenv("LLM__API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("No OpenAI API key available for contract test.")

    llm = OpenAI(model=os.getenv("LLM__MODEL", "gpt-4o-mini"), api_key=api_key)
    response = llm.complete("Say hello in one sentence.")
    text = extract_response_text(response)
    assert isinstance(text, str)
    assert text.strip()
