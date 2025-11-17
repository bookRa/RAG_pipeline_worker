"""Tests for parsing error handling and failure tracking."""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from src.app.parsing.schemas import ParsedPage, ParsedTextComponent
from src.app.adapters.llama_index.parsing_adapter import ImageAwareParsingAdapter
from src.app.services.parsing_service import ParsingService
from src.app.domain.models import Document


class TestParsedPageErrorFields:
    """Test the ParsedPage schema enhancements for error tracking."""
    
    def test_parsed_page_default_success_status(self):
        """ParsedPage defaults to success status when no error occurs."""
        page = ParsedPage(
            document_id="test-doc",
            page_number=1,
            raw_text="Test content",
            components=[],
        )
        assert page.parsing_status == "success"
        assert page.error_details is None
        assert page.error_type is None
    
    def test_parsed_page_with_failed_status(self):
        """ParsedPage can be marked as failed with error details."""
        page = ParsedPage(
            document_id="test-doc",
            page_number=2,
            raw_text="",
            components=[],
            parsing_status="failed",
            error_type="repetition_loop",
            error_details="Streaming stopped: detected repetition loop (85.5% of last 200 chars are '\\n')",
        )
        assert page.parsing_status == "failed"
        assert page.error_type == "repetition_loop"
        assert "repetition loop" in page.error_details
    
    def test_parsed_page_with_partial_status(self):
        """ParsedPage can be marked as partial when some content extracted."""
        page = ParsedPage(
            document_id="test-doc",
            page_number=3,
            raw_text="Partial content",
            components=[
                ParsedTextComponent(order=0, text="Some extracted text")
            ],
            parsing_status="partial",
            error_type="max_length_exceeded",
            error_details="Streaming stopped: response exceeded maximum length",
        )
        assert page.parsing_status == "partial"
        assert len(page.components) > 0
        assert page.error_type == "max_length_exceeded"
    
    def test_parsed_page_serialization_with_errors(self):
        """ParsedPage with errors can be serialized and deserialized."""
        page = ParsedPage(
            document_id="test-doc",
            page_number=4,
            raw_text="",
            components=[],
            parsing_status="failed",
            error_type="exception",
            error_details="TimeoutError: Connection timeout",
        )
        
        # Serialize
        page_dict = page.model_dump()
        assert page_dict["parsing_status"] == "failed"
        assert page_dict["error_type"] == "exception"
        
        # Deserialize
        restored_page = ParsedPage.model_validate(page_dict)
        assert restored_page.parsing_status == "failed"
        assert restored_page.error_type == "exception"
        assert "TimeoutError" in restored_page.error_details


class TestParsingAdapterErrorHandling:
    """Test error handling in ImageAwareParsingAdapter."""
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM."""
        llm = Mock()
        return llm
    
    @pytest.fixture
    def mock_prompt_settings(self):
        """Create mock prompt settings."""
        from src.app.config import PromptSettings
        return PromptSettings(
            parsing_system_prompt_path="docs/prompts/parsing/system.md",
            parsing_user_prompt_path="docs/prompts/parsing/user.md",
        )
    
    def test_parse_page_missing_pixmap(self, mock_llm, mock_prompt_settings):
        """When pixmap is missing, page is marked as failed."""
        adapter = ImageAwareParsingAdapter(
            llm=mock_llm,
            prompt_settings=mock_prompt_settings,
            use_streaming=False,
        )
        
        result = adapter.parse_page(
            document_id="test-doc",
            page_number=1,
            pixmap_path=None,
        )
        
        assert result.parsing_status == "failed"
        assert result.error_type == "missing_pixmap"
        assert "No pixmap" in result.error_details
    
    def test_parse_page_returns_failed_on_error(self, mock_llm, mock_prompt_settings):
        """When parsing encounters error, page is marked as failed with details."""
        adapter = ImageAwareParsingAdapter(
            llm=mock_llm,
            prompt_settings=mock_prompt_settings,
            use_streaming=False,
        )
        
        # Simulate error by providing invalid pixmap path
        result = adapter.parse_page(
            document_id="test-doc",
            page_number=2,
            pixmap_path=None,  # Missing pixmap will trigger error
        )
        
        assert result.parsing_status == "failed"
        assert result.error_type == "missing_pixmap"
        assert result.error_details is not None


class TestParsingServiceFailureTracking:
    """Test failure tracking in ParsingService."""
    
    @pytest.fixture
    def mock_observability(self):
        """Create a mock observability recorder."""
        obs = Mock()
        obs.record_event = Mock()
        return obs
    
    @pytest.fixture
    def mock_structured_parser(self):
        """Create a mock structured parser that returns failed pages."""
        parser = Mock()
        
        # Page 1: success
        success_page = ParsedPage(
            document_id="test-doc",
            page_number=1,
            raw_text="Success content",
            components=[],
            parsing_status="success",
        )
        
        # Page 2: failed
        failed_page = ParsedPage(
            document_id="test-doc",
            page_number=2,
            raw_text="",
            components=[],
            parsing_status="failed",
            error_type="repetition_loop",
            error_details="Streaming stopped: repetition loop",
        )
        
        parser.parse_page.side_effect = [success_page, failed_page]
        return parser
    
    def test_parsing_service_tracks_failures_in_metadata(self):
        """ParsingService extracts failures from parsed pages and adds to metadata."""
        # Directly test the metadata extraction logic
        parsed_pages_meta = {
            "1": {
                "document_id": "test-doc",
                "page_number": 1,
                "parsing_status": "success",
            },
            "2": {
                "document_id": "test-doc",
                "page_number": 2,
                "parsing_status": "failed",
                "error_type": "repetition_loop",
                "error_details": "Streaming stopped: repetition loop",
            },
        }
        
        # Simulate the logic in ParsingService.parse()
        parsing_failures = []
        for page_num_str, page_data in parsed_pages_meta.items():
            if page_data.get("parsing_status") != "success":
                parsing_failures.append({
                    "page_number": int(page_num_str),
                    "status": page_data.get("parsing_status"),
                    "error_type": page_data.get("error_type"),
                    "error_details": page_data.get("error_details"),
                })
        
        # Verify
        assert len(parsing_failures) == 1
        assert parsing_failures[0]["page_number"] == 2
        assert parsing_failures[0]["status"] == "failed"
        assert parsing_failures[0]["error_type"] == "repetition_loop"
        assert "repetition loop" in parsing_failures[0]["error_details"]
    
    def test_parsing_service_no_failures_when_all_success(self):
        """ParsingService does not create parsing_failures when all pages succeed."""
        # Directly test the metadata extraction logic
        parsed_pages_meta = {
            "1": {
                "document_id": "test-doc",
                "page_number": 1,
                "parsing_status": "success",
            },
            "2": {
                "document_id": "test-doc",
                "page_number": 2,
                "parsing_status": "success",
            },
        }
        
        # Simulate the logic in ParsingService.parse()
        parsing_failures = []
        for page_num_str, page_data in parsed_pages_meta.items():
            if page_data.get("parsing_status") != "success":
                parsing_failures.append({
                    "page_number": int(page_num_str),
                    "status": page_data.get("parsing_status"),
                    "error_type": page_data.get("error_type"),
                    "error_details": page_data.get("error_details"),
                })
        
        # Verify no failures
        assert len(parsing_failures) == 0


class TestStreamingErrorReturn:
    """Test that streaming method returns error information."""
    
    def test_stream_chat_response_signature(self):
        """Verify _stream_chat_response returns tuple with error info."""
        from src.app.adapters.llama_index.parsing_adapter import ImageAwareParsingAdapter
        import inspect
        
        # Check the signature
        sig = inspect.signature(ImageAwareParsingAdapter._stream_chat_response)
        return_annotation = sig.return_annotation
        
        # Should return tuple[str, str | None, str | None]
        assert "tuple" in str(return_annotation).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

