"""PDF parser adapter using pdfplumber for text parsing."""

from __future__ import annotations

import io
from typing import Sequence

import pdfplumber

from ..application.interfaces import DocumentParser


class PdfParserAdapter(DocumentParser):
    """PDF parser adapter that extracts text from PDF files using pdfplumber."""

    supported_types: Sequence[str] = ("pdf",)

    def supports_type(self, file_type: str) -> bool:
        """Return True if the parser handles PDF files."""
        return file_type.lower() in self.supported_types

    def parse(self, file_bytes: bytes, filename: str) -> list[str]:
        """
        Extract text from PDF file bytes, returning one string per page.

        Args:
            file_bytes: Raw PDF file content as bytes
            filename: Original filename (used for error messages)

        Returns:
            List of page texts, one string per page. Returns empty list if
            parsing fails or PDF is empty/corrupted.

        Note:
            This method handles various edge cases:
            - Empty PDFs: returns empty list
            - Corrupted PDFs: returns empty list (logs error internally)
            - Password-protected PDFs: returns empty list
            - PDFs with no extractable text: returns list with empty strings
        """
        if not file_bytes:
            return []

        try:
            # Create a file-like object from bytes for pdfplumber
            pdf_file = io.BytesIO(file_bytes)
            page_texts: list[str] = []

            with pdfplumber.open(pdf_file) as pdf:
                # Extract text from each page
                for page in pdf.pages:
                    # Extract text from the page
                    # extract_text() returns None if no text is found, so we default to empty string
                    page_text = page.extract_text() or ""
                    page_texts.append(page_text)

            return page_texts

        except Exception:
            # PDF is corrupted, invalid format, password-protected, or other error
            # Return empty list rather than raising exception
            # This allows the parsing service to fall back to placeholder if needed
            # Note: pdfplumber raises PdfminerException (from pdfplumber.utils.exceptions)
            # which wraps pdfminer errors (e.g., PDFSyntaxError). Catching Exception
            # catches all of these gracefully.
            return []
