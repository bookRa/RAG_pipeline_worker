"""Tests for BCAI LLM and Embedding adapters.

These tests verify the BCAI adapter integrates correctly with the pipeline.
Actual API calls are mocked to avoid network dependencies in CI.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_bcai_response():
    """Mock BCAI API response for chat completion."""
    return {
        "id": "chatcmpl-test123",
        "model": "gpt-4o-mini",
        "created": 1234567890,
        "object": "chat.completion",
        "choices": [
            {
                "finish_reason": "stop",
                "messages": [
                    {
                        "role": "assistant",
                        "content": "This is a test response from BCAI."
                    }
                ]
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 8,
            "total_tokens": 18
        }
    }


@pytest.fixture
def mock_bcai_embedding_response():
    """Mock BCAI API response for embeddings."""
    return {
        "data": [
            {
                "embedding": [0.1, 0.2, 0.3, 0.4, 0.5] * 307 + [0.1],  # 1536 dimensions
                "index": 0,
                "object": "embedding"
            }
        ],
        "model": "text-embedding-3-small",
        "object": "list",
        "usage": {
            "prompt_tokens": 5,
            "total_tokens": 5
        }
    }


class TestBCAILLM:
    """Test the BCAI LLM adapter."""

    def test_bcai_llm_initialization(self):
        """Test that BCAI LLM can be initialized with required parameters."""
        from src.app.adapters.llama_index.bcai_llm import BCAILLM
        
        llm = BCAILLM(
            api_base="https://bcai-test.web.boeing.com",
            api_key="test-pat-key",
            model="gpt-4o-mini",
            temperature=0.1,
        )
        
        assert llm.metadata.model_name == "gpt-4o-mini"
        assert llm.metadata.is_chat_model is True
        assert llm._temperature == 0.1

    @patch('src.app.adapters.llama_index.bcai_llm.requests.Session')
    def test_bcai_llm_complete(self, mock_session_class, mock_bcai_response):
        """Test BCAI LLM completion."""
        from src.app.adapters.llama_index.bcai_llm import BCAILLM
        
        # Setup mock
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_bcai_response
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        # Create LLM and call
        llm = BCAILLM(
            api_base="https://bcai-test.web.boeing.com",
            api_key="test-pat-key",
            model="gpt-4o-mini",
        )
        
        result = llm.complete("Test prompt")
        
        assert result.text == "This is a test response from BCAI."
        assert mock_session.post.called
        
        # Verify request payload
        call_args = mock_session.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["model"] == "gpt-4o-mini"
        assert payload["messages"][0]["content"] == "Test prompt"
        assert payload["conversation_mode"] == ["non-rag"]
        assert payload["skip_db_save"] is True
        assert "conversation_guid" in payload  # Required by BCAI

    @patch('src.app.adapters.llama_index.bcai_llm.requests.Session')
    def test_bcai_llm_chat(self, mock_session_class, mock_bcai_response):
        """Test BCAI LLM chat interface."""
        from src.app.adapters.llama_index.bcai_llm import BCAILLM
        from llama_index.core.base.llms.base import ChatMessage
        from llama_index.core.base.llms.types import MessageRole
        
        # Setup mock
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_bcai_response
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        # Create LLM and call
        llm = BCAILLM(
            api_base="https://bcai-test.web.boeing.com",
            api_key="test-pat-key",
            model="gpt-4o-mini",
        )
        
        messages = [
            ChatMessage(role=MessageRole.USER, content="Hello BCAI")
        ]
        
        result = llm.chat(messages)
        
        assert result.message.content == "This is a test response from BCAI."
        assert result.message.role == MessageRole.ASSISTANT

    @patch('src.app.adapters.llama_index.bcai_llm.requests.Session')
    def test_bcai_llm_with_structured_output(self, mock_session_class, mock_bcai_response):
        """Test BCAI LLM with structured output schema."""
        from src.app.adapters.llama_index.bcai_llm import BCAILLM
        from llama_index.core.base.llms.base import ChatMessage
        from llama_index.core.base.llms.types import MessageRole
        
        # Setup mock
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_bcai_response
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        # Create LLM
        llm = BCAILLM(
            api_base="https://bcai-test.web.boeing.com",
            api_key="test-pat-key",
            model="gpt-4o-mini",
        )
        
        messages = [ChatMessage(role=MessageRole.USER, content="Parse this")]
        schema = {
            "type": "object",
            "properties": {
                "result": {"type": "string"}
            }
        }
        
        result = llm.chat(messages, structured_output_schema=schema)
        
        # Verify structured output was requested
        call_args = mock_session.post.call_args
        payload = call_args.kwargs["json"]
        assert "response_format" in payload
        assert payload["response_format"]["type"] == "json_schema"


class TestBCAIEmbedding:
    """Test the BCAI Embedding adapter."""

    def test_bcai_embedding_initialization(self):
        """Test that BCAI Embedding can be initialized."""
        from src.app.adapters.llama_index.bcai_embedding import BCAIEmbedding
        
        embedding = BCAIEmbedding(
            api_base="https://bcai-test.web.boeing.com",
            api_key="test-pat-key",
            model="text-embedding-3-small",
        )
        
        assert embedding.model_name == "text-embedding-3-small"
        assert embedding.dimension == 1536

    def test_bcai_embedding_dimension_detection(self):
        """Test that BCAI Embedding correctly detects dimensions."""
        from src.app.adapters.llama_index.bcai_embedding import BCAIEmbedding
        
        # Test with explicit dimensions
        embedding = BCAIEmbedding(
            api_base="https://bcai-test.web.boeing.com",
            api_key="test-pat-key",
            model="text-embedding-3-small",
            dimensions=512,
        )
        assert embedding.dimension == 512
        
        # Test with text-embedding-3-large
        embedding = BCAIEmbedding(
            api_base="https://bcai-test.web.boeing.com",
            api_key="test-pat-key",
            model="text-embedding-3-large",
        )
        assert embedding.dimension == 3072

    @patch('src.app.adapters.llama_index.bcai_embedding.requests.Session')
    def test_bcai_embedding_single_text(self, mock_session_class, mock_bcai_embedding_response):
        """Test embedding a single text."""
        from src.app.adapters.llama_index.bcai_embedding import BCAIEmbedding
        
        # Setup mock
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_bcai_embedding_response
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        # Create embedding adapter
        embedding = BCAIEmbedding(
            api_base="https://bcai-test.web.boeing.com",
            api_key="test-pat-key",
            model="text-embedding-3-small",
        )
        
        result = embedding._get_text_embedding("Test text")
        
        assert isinstance(result, list)
        assert len(result) == 1536
        assert mock_session.post.called

    @patch('src.app.adapters.llama_index.bcai_embedding.requests.Session')
    def test_bcai_embedding_batch(self, mock_session_class):
        """Test embedding multiple texts."""
        from src.app.adapters.llama_index.bcai_embedding import BCAIEmbedding
        
        # Setup mock for batch response
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        batch_response = {
            "data": [
                {"embedding": [0.1] * 1536, "index": 0},
                {"embedding": [0.2] * 1536, "index": 1},
            ]
        }
        mock_response.json.return_value = batch_response
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        # Create embedding adapter
        embedding = BCAIEmbedding(
            api_base="https://bcai-test.web.boeing.com",
            api_key="test-pat-key",
            model="text-embedding-3-small",
        )
        
        texts = ["Text 1", "Text 2"]
        results = embedding._get_text_embeddings(texts)
        
        assert len(results) == 2
        assert all(len(emb) == 1536 for emb in results)


class TestBCAIIntegration:
    """Test BCAI integration with bootstrap configuration."""

    def test_bcai_provider_in_bootstrap(self):
        """Test that BCAI provider can be configured through bootstrap."""
        from src.app.config import Settings, LLMSettings
        from src.app.adapters.llama_index.bootstrap import _build_llm
        
        settings = Settings(
            llm=LLMSettings(
                provider="bcai",
                model="gpt-4o-mini",
                api_base="https://bcai-test.web.boeing.com",
                api_key="test-pat-key",
            )
        )
        
        llm = _build_llm(
            settings,
            api_key="test-pat-key",
            api_base="https://bcai-test.web.boeing.com"
        )
        
        assert llm is not None
        assert llm.metadata.model_name == "gpt-4o-mini"

    def test_bcai_embedding_provider_in_bootstrap(self):
        """Test that BCAI embedding provider can be configured through bootstrap."""
        from src.app.config import Settings, EmbeddingSettings, LLMSettings
        from src.app.adapters.llama_index.bootstrap import _build_embedding
        
        settings = Settings(
            llm=LLMSettings(
                api_base="https://bcai-test.web.boeing.com",
                api_key="test-pat-key",
            ),
            embeddings=EmbeddingSettings(
                provider="bcai",
                model="text-embedding-3-small",
                api_base="https://bcai-test.web.boeing.com",
                api_key="test-pat-key",
            )
        )
        
        embedding = _build_embedding(settings)
        
        assert embedding is not None
        assert embedding.model_name == "text-embedding-3-small"

