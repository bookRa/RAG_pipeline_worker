from __future__ import annotations

import os

import pytest
from pathlib import Path
import sys
import json
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env", override=False)

from src.app.adapters.llama_index.utils import extract_response_text  # noqa: E402

pytestmark = pytest.mark.contract


@pytest.mark.skipif(os.getenv("RUN_CONTRACT_TESTS") != "1", reason="Contract tests require RUN_CONTRACT_TESTS=1")
def test_openai_completion_contract():
    api_key = os.getenv("LLM__API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("No OpenAI API key available for contract test.")

    from llama_index.llms.openai import OpenAI

    llm = OpenAI(model=os.getenv("LLM__MODEL", "gpt-4o-mini"), api_key=api_key)
    response = llm.complete(
        "You MUST respond with valid JSON only, without markdown fences. "
        "Return {\"foo\": string, \"bar\": integer}. Example: {\"foo\": \"hello\", \"bar\": 3}."
    )
    text = extract_response_text(response)
    print("Contract raw response:", text)
    data = json.loads(text)
    assert isinstance(data["foo"], str)
    assert isinstance(data["bar"], int)
