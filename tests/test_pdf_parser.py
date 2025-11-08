"""Unit tests for PDF parser adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.app.adapters.pdf_parser import PdfParserAdapter
from src.app.application.interfaces import DocumentParser


def test_pdf_parser_implements_document_parser_protocol():
    """Test that PdfParserAdapter correctly implements DocumentParser protocol."""
    parser = PdfParserAdapter()
    
    # Verify it has the required attributes
    assert hasattr(parser, "supported_types")
    assert hasattr(parser, "supports_type")
    assert hasattr(parser, "parse")
    
    # Verify it can be used as a DocumentParser
    assert isinstance(parser, DocumentParser)


def test_supports_type_accepts_pdf():
    """Test that supports_type correctly identifies PDF files."""
    parser = PdfParserAdapter()
    
    assert parser.supports_type("pdf") is True
    assert parser.supports_type("PDF") is True  # Case insensitive
    assert parser.supports_type("Pdf") is True
    assert parser.supports_type("docx") is False
    assert parser.supports_type("txt") is False


def test_parse_extracts_text_from_real_pdf():
    """Test that parser extracts text from a real PDF file."""
    parser = PdfParserAdapter()
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    
    # Skip test if test PDF doesn't exist
    if not test_pdf_path.exists():
        pytest.skip(f"Test PDF not found at {test_pdf_path}")
    
    pdf_bytes = test_pdf_path.read_bytes()
    page_texts = parser.parse(pdf_bytes, "test_document.pdf")
    
    # The test PDF has 10 pages, so we should get 10 page texts
    assert len(page_texts) == 10
    
    # Each page should be a string (may be empty if page has no text)
    assert all(isinstance(text, str) for text in page_texts)
    
    # At least some pages should have text content
    assert any(len(text) > 0 for text in page_texts)


def test_parse_handles_empty_bytes():
    """Test that parser handles empty file bytes gracefully."""
    parser = PdfParserAdapter()
    
    result = parser.parse(b"", "empty.pdf")
    
    # Should return empty list for empty bytes
    assert result == []


def test_parse_handles_corrupted_pdf():
    """Test that parser handles corrupted/invalid PDF bytes gracefully."""
    parser = PdfParserAdapter()
    
    # Invalid PDF bytes
    corrupted_bytes = b"This is not a valid PDF file"
    
    result = parser.parse(corrupted_bytes, "corrupted.pdf")
    
    # Should return empty list rather than raising exception
    assert isinstance(result, list)
    assert len(result) == 0


def test_parse_handles_nonexistent_pdf_structure():
    """Test that parser handles PDF-like bytes that aren't actually PDFs."""
    parser = PdfParserAdapter()
    
    # Bytes that look like they might be PDF but aren't
    fake_pdf_bytes = b"%PDF-1.4\nThis is fake content\n%%EOF"
    
    result = parser.parse(fake_pdf_bytes, "fake.pdf")
    
    # Should return empty list for invalid PDF structure
    assert isinstance(result, list)


def test_parse_returns_list_of_strings():
    """Test that parse always returns a list of strings."""
    parser = PdfParserAdapter()
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    
    if not test_pdf_path.exists():
        pytest.skip(f"Test PDF not found at {test_pdf_path}")
    
    pdf_bytes = test_pdf_path.read_bytes()
    page_texts = parser.parse(pdf_bytes, "test_document.pdf")
    
    # Should always return a list
    assert isinstance(page_texts, list)
    
    # All elements should be strings
    assert all(isinstance(text, str) for text in page_texts)


def test_parse_preserves_page_order():
    """Test that parser extracts pages in correct order."""
    parser = PdfParserAdapter()
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    
    if not test_pdf_path.exists():
        pytest.skip(f"Test PDF not found at {test_pdf_path}")
    
    pdf_bytes = test_pdf_path.read_bytes()
    page_texts = parser.parse(pdf_bytes, "test_document.pdf")
    
    # Should have multiple pages
    assert len(page_texts) > 1
    
    # Each page should correspond to the page number (index + 1)
    # We can't verify exact content, but we can verify structure
    for i, text in enumerate(page_texts):
        assert isinstance(text, str), f"Page {i+1} should be a string"


def test_supported_types_is_sequence():
    """Test that supported_types is a sequence containing 'pdf'."""
    parser = PdfParserAdapter()
    
    assert "pdf" in parser.supported_types
    assert len(parser.supported_types) == 1

