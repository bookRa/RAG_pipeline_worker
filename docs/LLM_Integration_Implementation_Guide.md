# LLM Integration Implementation Guide

## Introduction

This guide demonstrates how to integrate Large Language Model (LLM) calls into the document extraction pipeline while maintaining strict adherence to hexagonal architecture principles. Specifically, we'll implement an LLM-based PDF parser that processes page screenshots instead of extracting text directly.

**Use Case**: Replace traditional PDF text extraction with LLM-powered visual analysis of PDF pages, enabling:
- Better handling of scanned documents
- Extraction of structured data from complex layouts
- Understanding of visual elements (tables, diagrams, charts)
- Multi-modal document understanding

**Purpose**: This guide demonstrates how to:
- Integrate external LLM APIs into the architecture
- Handle multi-modal inputs (images + text)
- Structure LLM calls as adapters following dependency inversion
- Write testable code with mockable LLM dependencies
- Handle costs, rate limiting, and error scenarios gracefully

---

## Architectural Context

### Where Do LLM Calls Fit?

LLM integration follows the same adapter pattern as other external dependencies:

```
┌─────────────────────────────────────────┐
│         API Layer (FastAPI)             │
│  ┌───────────────────────────────────┐  │
│  │      Use Cases                    │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │   Services                   │  │  │
│  │  │   (ExtractionService)        │  │  │
│  │  │   ┌──────────────────────┐  │  │  │
│  │  │   │  Ports/Interfaces     │  │  │  │
│  │  │   │  (DocumentParser)     │  │  │  │
│  │  │   └──────────────────────┘  │  │  │
│  │  └─────────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │   Adapters                       │  │
│  │   ┌───────────────────────────┐  │  │
│  │   │ LLMImageParserAdapter     │  │  │
│  │   │   ┌─────────────────────┐│  │  │
│  │   │   │ LLMClient (Port)    ││  │  │
│  │   │   │ ImageConverter       ││  │  │
│  │   │   └─────────────────────┘│  │  │
│  │   └───────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**Key Architectural Points**:

1. **LLM calls are adapters**: They live in `adapters/` and implement protocols
2. **Services don't know about LLMs**: Services depend on `DocumentParser`, not `LLMImageParserAdapter`
3. **Multiple adapters can coexist**: Traditional PDF parser and LLM parser can both exist
4. **LLM client is a separate port**: Can be reused across different adapters
5. **Composition over inheritance**: Adapters compose LLM clients, image converters, etc.

### Why This Architecture?

**Separation of Concerns**: 
- PDF-to-image conversion is separate from LLM calling
- LLM client is separate from document parsing logic
- Services orchestrate, adapters handle infrastructure

**Testability**:
- Can test PDF-to-image conversion without LLM calls
- Can test LLM client without document parsing
- Can test services with mock LLM clients

**Flexibility**:
- Can swap LLM providers (OpenAI, Anthropic, local models) without changing services
- Can add caching, rate limiting, retry logic in adapters
- Can A/B test different extraction strategies

---

## Step-by-Step Implementation

### Step 1: Define LLM Client Protocol

**What we do**: Create a protocol for LLM clients that can handle images and structured outputs.

**Why**: Services and adapters need a consistent interface for LLM calls, regardless of the underlying provider (OpenAI, Anthropic, etc.).

**Architectural Note**: This protocol lives in `application/interfaces.py` alongside other ports. It defines the contract, not the implementation.

**File to Modify**: `src/app/application/interfaces.py`

**Protocol Definition**:
```python
class LLMClient(Protocol):
    """Port for LLM clients that can process images and return structured text."""
    
    def process_image(
        self,
        image_bytes: bytes,
        prompt: str,
        model: str | None = None,
    ) -> str:
        """
        Process an image with an LLM using the provided prompt.
        
        Args:
            image_bytes: Image data as bytes (PNG, JPEG, etc.)
            prompt: Text prompt describing what to extract from the image
            model: Optional model identifier (provider-specific)
        
        Returns:
            Extracted text content from the image
        
        Raises:
            LLMError: If the LLM call fails (rate limits, API errors, etc.)
        """
        ...
```

**Rationale**:
- **Protocol, not class**: Services depend on the protocol, not concrete implementations
- **Image-first**: Designed for visual document processing
- **Structured prompt**: Prompt is a parameter, allowing different extraction strategies
- **Model parameter**: Allows provider-specific model selection
- **Returns string**: Matches `DocumentParser.parse()` return type expectations

**Alternative Considered**: Returning structured JSON. We return string to match existing `DocumentParser` protocol, and can parse JSON in the adapter if needed.

---

### Step 2: Add Dependencies

**What we do**: Add libraries for PDF-to-image conversion and LLM API calls.

**Dependencies Needed**:
- `pdf2image`: Convert PDF pages to images
- `pillow`: Image processing (usually comes with pdf2image)
- `openai` or `anthropic`: LLM API clients (choose based on provider)

**Why**: 
- `pdf2image` uses `poppler` under the hood for reliable PDF rendering
- LLM libraries provide official API clients with retry logic, error handling

**Architectural Note**: These are infrastructure dependencies. They belong in adapters, never in services or domain.

**File to Modify**: `requirements.txt`

```python
pdf2image
pillow
openai  # or anthropic, depending on provider choice
```

**System Dependencies**: `pdf2image` requires `poppler` system library:
- macOS: `brew install poppler`
- Ubuntu/Debian: `apt-get install poppler-utils`
- Document this in README or setup instructions

---

### Step 3: Implement LLM Client Adapter

**What we do**: Create a concrete implementation of `LLMClient` protocol.

**Why**: This adapter handles the actual API calls, error handling, rate limiting, and response parsing. It's provider-specific (OpenAI, Anthropic, etc.) but implements a common protocol.

**Architectural Decisions**:

1. **Adapter lives in `adapters/`**: Infrastructure concern
2. **Implements protocol**: Can be swapped with other implementations
3. **Handles errors gracefully**: Converts API errors to domain exceptions
4. **Configurable**: Accepts API keys, model names, etc. via constructor

**File to Create**: `src/app/adapters/llm_image_client.py`

**Implementation**:
```python
"""OpenAI-based LLM client for image processing."""

from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image

from ..application.interfaces import LLMClient


class OpenAIImageClient(LLMClient):
    """OpenAI GPT-4 Vision client for processing document images."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4-vision-preview",
        max_tokens: int = 4000,
    ) -> None:
        """
        Initialize OpenAI image client.
        
        Args:
            api_key: OpenAI API key
            model: Model identifier (default: gpt-4-vision-preview)
            max_tokens: Maximum tokens in response
        """
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        # Lazy import to avoid dependency if not used
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "openai package required. Install with: pip install openai"
            )
        self.client = OpenAI(api_key=api_key)
    
    def process_image(
        self,
        image_bytes: bytes,
        prompt: str,
        model: str | None = None,
    ) -> str:
        """
        Process image with OpenAI Vision API.
        
        Args:
            image_bytes: Image data as bytes
            prompt: Extraction prompt
            model: Override default model (optional)
        
        Returns:
            Extracted text content
        
        Raises:
            LLMError: If API call fails
        """
        try:
            # Convert image bytes to base64 for API
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # Prepare API call
            response = self.client.chat.completions.create(
                model=model or self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=self.max_tokens,
            )
            
            # Extract text from response
            return response.choices[0].message.content or ""
            
        except Exception as e:
            # Convert API errors to domain exceptions
            raise LLMError(f"OpenAI API call failed: {e}") from e
```

**Key Design Decisions**:

1. **Lazy import**: Only imports `openai` when adapter is instantiated
   - **Why**: Avoids dependency if adapter isn't used
   - **Benefit**: Faster startup, optional dependency

2. **Base64 encoding**: Converts image bytes to base64 for API
   - **Why**: OpenAI API expects base64-encoded images
   - **Benefit**: Standard format, works with any image type

3. **Error conversion**: Converts API exceptions to `LLMError`
   - **Why**: Keeps domain layer clean of API-specific errors
   - **Benefit**: Services can handle errors uniformly

4. **Configurable model**: Allows model override per call
   - **Why**: Different pages might need different models
   - **Benefit**: Flexibility without changing adapter code

**Exception Definition**: Add to `src/app/application/interfaces.py` or `src/app/domain/exceptions.py`:
```python
class LLMError(Exception):
    """Raised when LLM operations fail."""
    pass
```

---

### Step 4: Create PDF-to-Image Converter

**What we do**: Create a utility adapter that converts PDF pages to images.

**Why**: This is a separate concern from LLM calling. We can:
- Test image conversion independently
- Reuse converter for other purposes (thumbnails, previews)
- Swap conversion libraries without changing LLM code

**Architectural Note**: This could be a simple utility class or a protocol if we want multiple implementations. For simplicity, we'll make it a concrete class that can be injected.

**File to Create**: `src/app/adapters/pdf_image_converter.py`

**Implementation**:
```python
"""PDF to image conversion utility."""

from __future__ import annotations

import io
from typing import Sequence

from PIL import Image

try:
    from pdf2image import convert_from_bytes
except ImportError:
    convert_from_bytes = None


class PDFImageConverter:
    """Converts PDF pages to images."""
    
    def __init__(self, dpi: int = 200) -> None:
        """
        Initialize PDF image converter.
        
        Args:
            dpi: Resolution for image conversion (default: 200)
        """
        if convert_from_bytes is None:
            raise ImportError(
                "pdf2image required. Install with: pip install pdf2image"
            )
        self.dpi = dpi
    
    def convert_page_to_image(
        self,
        pdf_bytes: bytes,
        page_number: int,
    ) -> bytes:
        """
        Convert a single PDF page to PNG image bytes.
        
        Args:
            pdf_bytes: Full PDF file bytes
            page_number: 1-indexed page number
        
        Returns:
            PNG image bytes
        
        Raises:
            ValueError: If page_number is invalid
        """
        try:
            # Convert PDF to images (only the page we need)
            images = convert_from_bytes(
                pdf_bytes,
                dpi=self.dpi,
                first_page=page_number,
                last_page=page_number,
            )
            
            if not images:
                raise ValueError(f"Page {page_number} not found in PDF")
            
            # Convert PIL Image to PNG bytes
            image = images[0]
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
            
        except Exception as e:
            raise ValueError(f"Failed to convert PDF page to image: {e}") from e
    
    def convert_all_pages(self, pdf_bytes: bytes) -> Sequence[bytes]:
        """
        Convert all PDF pages to images.
        
        Args:
            pdf_bytes: Full PDF file bytes
        
        Returns:
            List of PNG image bytes, one per page
        """
        try:
            images = convert_from_bytes(pdf_bytes, dpi=self.dpi)
            result = []
            for image in images:
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                result.append(buffer.getvalue())
            return result
        except Exception as e:
            raise ValueError(f"Failed to convert PDF to images: {e}") from e
```

**Rationale**:
- **Separate class**: Can be tested independently
- **Configurable DPI**: Allows quality vs. size trade-offs
- **Page-by-page or all pages**: Flexibility for different use cases
- **Returns bytes**: Easy to pass to LLM client
- **Error handling**: Converts library errors to domain exceptions

---

### Step 5: Implement LLM-Based PDF Parser Adapter

**What we do**: Create a `DocumentParser` adapter that uses LLM to extract text from PDF page images.

**Why**: This adapter implements the `DocumentParser` protocol, so it can be used as a drop-in replacement for traditional PDF parsers. The service doesn't know or care that it's using an LLM.

**Architectural Decisions**:

1. **Implements `DocumentParser`**: Same protocol as `PdfParserAdapter`
2. **Composes dependencies**: Uses `LLMClient` and `PDFImageConverter`
3. **Handles errors gracefully**: Returns empty list on failures
4. **Configurable prompt**: Allows different extraction strategies

**File to Create**: `src/app/adapters/llm_pdf_parser.py`

**Implementation**:
```python
"""LLM-based PDF parser that processes page images."""

from __future__ import annotations

from typing import Sequence

from ..application.interfaces import DocumentParser, LLMClient
from .pdf_image_converter import PDFImageConverter


class LLMImageParserAdapter(DocumentParser):
    """PDF parser that uses LLM to extract text from page images."""
    
    supported_types: Sequence[str] = ("pdf",)
    
    # Default prompt for text extraction
    DEFAULT_EXTRACTION_PROMPT = """Extract all text content from this PDF page image.
    
Return the text exactly as it appears, preserving:
- Line breaks and paragraph structure
- Table structures (use markdown tables if helpful)
- Headers and section titles
- Any visible text content

If the page contains no text, return an empty string."""

    def __init__(
        self,
        llm_client: LLMClient,
        image_converter: PDFImageConverter | None = None,
        extraction_prompt: str | None = None,
    ) -> None:
        """
        Initialize LLM-based PDF parser.
        
        Args:
            llm_client: LLM client for processing images
            image_converter: PDF to image converter (creates default if None)
            extraction_prompt: Custom prompt for text extraction
        """
        self.llm_client = llm_client
        self.image_converter = image_converter or PDFImageConverter()
        self.extraction_prompt = extraction_prompt or self.DEFAULT_EXTRACTION_PROMPT
    
    def supports_type(self, file_type: str) -> bool:
        """Return True if parser handles PDF files."""
        return file_type.lower() in self.supported_types
    
    def parse(self, file_bytes: bytes, filename: str) -> list[str]:
        """
        Extract text from PDF using LLM image processing.
        
        Args:
            file_bytes: PDF file bytes
            filename: Original filename (for error messages)
        
        Returns:
            List of page texts, one string per page
        """
        if not file_bytes:
            return []
        
        try:
            # Convert PDF pages to images
            page_images = self.image_converter.convert_all_pages(file_bytes)
            
            # Process each page image with LLM
            page_texts: list[str] = []
            for page_num, image_bytes in enumerate(page_images, start=1):
                try:
                    # Call LLM to extract text from image
                    extracted_text = self.llm_client.process_image(
                        image_bytes=image_bytes,
                        prompt=self.extraction_prompt,
                    )
                    page_texts.append(extracted_text)
                except Exception as e:
                    # If LLM call fails for a page, add empty string
                    # This allows other pages to still be processed
                    page_texts.append("")
            
            return page_texts
            
        except Exception:
            # If conversion or processing fails entirely, return empty list
            # This allows extraction service to fall back to placeholder
            return []
```

**Key Design Decisions**:

1. **Dependency Injection**: `LLMClient` and `PDFImageConverter` are injected
   - **Why**: Enables testing with mocks
   - **Benefit**: Can swap implementations without changing code

2. **Default prompt**: Provides sensible default, allows override
   - **Why**: Most use cases need similar extraction
   - **Benefit**: Easy to use, flexible for customization

3. **Page-by-page processing**: Processes each page separately
   - **Why**: Matches `DocumentParser` protocol (returns list per page)
   - **Benefit**: Can handle failures per page, preserves page boundaries

4. **Graceful degradation**: Returns empty string for failed pages
   - **Why**: Allows partial success (some pages extracted, others not)
   - **Benefit**: More resilient than failing entirely

5. **Error handling**: Catches all exceptions, returns empty list
   - **Why**: Matches pattern from `PdfParserAdapter`
   - **Benefit**: Extraction service can fall back to placeholder

---

### Step 6: Wire Adapters in Container

**What we do**: Update `container.py` to wire the new LLM-based parser.

**Why**: The container is the composition root. It decides which adapters to use and wires them together.

**Architectural Note**: We can wire multiple parsers. The extraction service will use the first one that `supports_type()` returns True. This allows A/B testing or fallback strategies.

**File to Modify**: `src/app/container.py`

**Changes**:
```python
from .adapters.llm_pdf_parser import LLMImageParserAdapter
from .adapters.llm_image_client import OpenAIImageClient
from .adapters.pdf_image_converter import PDFImageConverter

class AppContainer:
    def __init__(self) -> None:
        # ... existing code ...
        
        # LLM client setup (if API key is configured)
        llm_api_key = os.getenv("OPENAI_API_KEY")
        if llm_api_key:
            llm_client = OpenAIImageClient(api_key=llm_api_key)
            image_converter = PDFImageConverter(dpi=200)
            llm_pdf_parser = LLMImageParserAdapter(
                llm_client=llm_client,
                image_converter=image_converter,
            )
            # Add LLM parser first so it's tried before traditional parser
            self.document_parsers.insert(0, llm_pdf_parser)
        else:
            # Fall back to traditional parsers if no LLM key configured
            pass
        
        # ... rest of existing code ...
```

**Rationale**:
- **Environment-based**: Only uses LLM if API key is configured
- **Fallback**: Falls back to traditional parsers if LLM unavailable
- **Order matters**: LLM parser is tried first (inserted at index 0)
- **No service changes**: Extraction service doesn't know which parser is used

---

### Step 7: Add Unit Tests for LLM Client

**What we do**: Create comprehensive unit tests for the LLM client adapter.

**Why**: LLM clients are critical infrastructure. We need to test:
- API call formatting
- Error handling
- Response parsing
- Configuration

**Test Strategy**: Mock the OpenAI API client to avoid real API calls in tests.

**File to Create**: `tests/test_llm_image_client.py`

**Implementation**:
```python
"""Unit tests for LLM image client adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.app.adapters.llm_image_client import OpenAIImageClient


def test_llm_client_processes_image(mock_openai_response):
    """Test that LLM client correctly processes an image."""
    # Mock OpenAI API response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Extracted text from image"
    
    client = OpenAIImageClient(api_key="test-key")
    
    with patch.object(client.client.chat.completions, "create", return_value=mock_response):
        image_bytes = b"fake image bytes"
        prompt = "Extract text from this image"
        
        result = client.process_image(image_bytes, prompt)
        
        assert result == "Extracted text from image"


def test_llm_client_handles_api_errors():
    """Test that LLM client handles API errors gracefully."""
    client = OpenAIImageClient(api_key="test-key")
    
    # Mock API to raise exception
    with patch.object(
        client.client.chat.completions,
        "create",
        side_effect=Exception("API Error"),
    ):
        with pytest.raises(LLMError) as exc_info:
            client.process_image(b"image", "prompt")
        
        assert "OpenAI API call failed" in str(exc_info.value)


def test_llm_client_uses_custom_model():
    """Test that LLM client can use custom model per call."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Result"
    
    client = OpenAIImageClient(api_key="test-key", model="default-model")
    
    with patch.object(client.client.chat.completions, "create", return_value=mock_response) as mock_create:
        client.process_image(b"image", "prompt", model="custom-model")
        
        # Verify custom model was used
        call_args = mock_create.call_args
        assert call_args.kwargs["model"] == "custom-model"
```

**Rationale**:
- **Mock external APIs**: Don't make real API calls in unit tests
- **Test error paths**: Verify error handling works
- **Test configuration**: Verify model selection works
- **Fast execution**: No network calls, tests run quickly

---

### Step 8: Add Unit Tests for PDF Image Converter

**What we do**: Test PDF-to-image conversion independently.

**Why**: Image conversion is a separate concern. We need to verify it works correctly before integrating with LLM.

**File to Create**: `tests/test_pdf_image_converter.py`

**Implementation**:
```python
"""Unit tests for PDF image converter."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.app.adapters.pdf_image_converter import PDFImageConverter


def test_converter_converts_single_page(tmp_path):
    """Test that converter converts a single PDF page to image."""
    # Use test PDF file
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    if not test_pdf_path.exists():
        pytest.skip("Test PDF not found")
    
    pdf_bytes = test_pdf_path.read_bytes()
    converter = PDFImageConverter(dpi=150)
    
    # Convert first page
    image_bytes = converter.convert_page_to_image(pdf_bytes, page_number=1)
    
    # Verify we got image bytes
    assert isinstance(image_bytes, bytes)
    assert len(image_bytes) > 0
    # PNG files start with specific header
    assert image_bytes.startswith(b"\x89PNG")


def test_converter_converts_all_pages():
    """Test that converter converts all PDF pages."""
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    if not test_pdf_path.exists():
        pytest.skip("Test PDF not found")
    
    pdf_bytes = test_pdf_path.read_bytes()
    converter = PDFImageConverter()
    
    images = converter.convert_all_pages(pdf_bytes)
    
    # Verify we got images for all pages
    assert len(images) == 10  # test_document.pdf has 10 pages
    assert all(isinstance(img, bytes) for img in images)
    assert all(img.startswith(b"\x89PNG") for img in images)


def test_converter_handles_invalid_page_number():
    """Test that converter handles invalid page numbers."""
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    if not test_pdf_path.exists():
        pytest.skip("Test PDF not found")
    
    pdf_bytes = test_pdf_path.read_bytes()
    converter = PDFImageConverter()
    
    with pytest.raises(ValueError):
        converter.convert_page_to_image(pdf_bytes, page_number=999)
```

---

### Step 9: Add Integration Tests for LLM Parser

**What we do**: Test the LLM parser adapter with mocked LLM client.

**Why**: Verify the adapter correctly orchestrates image conversion and LLM calls.

**File to Create**: `tests/test_llm_pdf_parser.py`

**Implementation**:
```python
"""Integration tests for LLM-based PDF parser."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.app.adapters.llm_pdf_parser import LLMImageParserAdapter
from src.app.adapters.pdf_image_converter import PDFImageConverter


class MockLLMClient:
    """Mock LLM client for testing."""
    
    def __init__(self) -> None:
        self.call_count = 0
        self.called_with_images = []
    
    def process_image(self, image_bytes: bytes, prompt: str, model: str | None = None) -> str:
        self.call_count += 1
        self.called_with_images.append(image_bytes)
        return f"Extracted text from page {self.call_count}"


def test_llm_parser_extracts_text_from_pdf():
    """Test that LLM parser extracts text from PDF pages."""
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    if not test_pdf_path.exists():
        pytest.skip("Test PDF not found")
    
    pdf_bytes = test_pdf_path.read_bytes()
    mock_llm = MockLLMClient()
    converter = PDFImageConverter()
    
    parser = LLMImageParserAdapter(
        llm_client=mock_llm,
        image_converter=converter,
    )
    
    page_texts = parser.parse(pdf_bytes, "test.pdf")
    
    # Verify we got text for all pages
    assert len(page_texts) == 10
    assert all(isinstance(text, str) for text in page_texts)
    assert mock_llm.call_count == 10  # Called once per page


def test_llm_parser_handles_llm_failures_gracefully():
    """Test that parser handles LLM failures gracefully."""
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    if not test_pdf_path.exists():
        pytest.skip("Test PDF not found")
    
    pdf_bytes = test_pdf_path.read_bytes()
    
    # Mock LLM that fails on some pages
    class FailingLLMClient:
        def __init__(self) -> None:
            self.call_count = 0
        
        def process_image(self, image_bytes: bytes, prompt: str, model: str | None = None) -> str:
            self.call_count += 1
            if self.call_count == 2:  # Fail on second page
                raise Exception("LLM API error")
            return f"Page {self.call_count} text"
    
    mock_llm = FailingLLMClient()
    converter = PDFImageConverter()
    parser = LLMImageParserAdapter(llm_client=mock_llm, image_converter=converter)
    
    page_texts = parser.parse(pdf_bytes, "test.pdf")
    
    # Should still process all pages, with empty string for failed page
    assert len(page_texts) == 10
    assert page_texts[0] == "Page 1 text"
    assert page_texts[1] == ""  # Failed page
    assert page_texts[2] == "Page 3 text"  # Continues processing
```

---

### Step 10: Update Extraction Service Tests

**What we do**: Add tests that verify the extraction service works with the LLM parser.

**Why**: Integration tests verify the full flow: service → parser → LLM client.

**File to Modify**: `tests/test_services.py`

**Add Test**:
```python
def test_extraction_with_llm_parser():
    """Test that extraction service works with LLM-based parser."""
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    if not test_pdf_path.exists():
        pytest.skip("Test PDF not found")
    
    pdf_bytes = test_pdf_path.read_bytes()
    
    # Create mock LLM client
    mock_llm = MockLLMClient()
    converter = PDFImageConverter()
    llm_parser = LLMImageParserAdapter(
        llm_client=mock_llm,
        image_converter=converter,
    )
    
    observability = build_null_observability()
    extraction = ExtractionService(
        observability=observability,
        parsers=[llm_parser],
    )
    ingestion = IngestionService(observability=observability)
    
    document = build_document()
    document = ingestion.ingest(document, file_bytes=pdf_bytes)
    
    result = extraction.extract(document, file_bytes=pdf_bytes)
    
    assert result.status == "extracted"
    assert len(result.pages) == 10
    assert all(page.text for page in result.pages)
```

---

## Rationale: Why Things Are Done This Way

### Why LLM Calls Are Adapters, Not Services

**Separation of Concerns**: LLM calls are infrastructure - they interact with external APIs, handle network requests, manage API keys, etc. Services orchestrate business logic.

**Example**: `ExtractionService` doesn't know about:
- Which LLM provider is used
- How images are encoded for API calls
- API rate limits or retry logic
- API key management

It only knows:
- There are parsers that can parse documents
- Parsers return a list of page texts

**Benefit**: If we need to switch from OpenAI to Anthropic, or add caching, or implement retry logic, we only change the adapter. The service remains unchanged.

### Why LLM Client Is a Separate Protocol

**Reusability**: The same LLM client can be used by:
- PDF image parser (this guide)
- Document summarization (existing `SummaryGenerator`)
- Future use cases (table extraction, metadata extraction, etc.)

**Testability**: Can mock the LLM client once and reuse mocks across tests.

**Flexibility**: Can have multiple LLM client implementations:
- `OpenAIImageClient` for OpenAI
- `AnthropicImageClient` for Anthropic
- `LocalLLMClient` for local models
- `CachedLLMClient` wrapper for caching

All implement the same protocol, so adapters can use any of them.

### Why PDF-to-Image Is Separate from LLM Client

**Single Responsibility**: 
- Image converter: PDF → Images
- LLM client: Images → Text

**Testability**: Can test image conversion without LLM calls (faster, no API costs).

**Reusability**: Image converter can be used for:
- LLM-based extraction (this guide)
- Thumbnail generation
- Page previews
- OCR preprocessing

**Flexibility**: Can swap conversion libraries (`pdf2image` vs. `PyMuPDF`) without changing LLM code.

### Why Adapters Compose Dependencies

**Dependency Injection**: Adapters receive dependencies via constructor, not create them internally.

**Example**: `LLMImageParserAdapter` receives `LLMClient` and `PDFImageConverter`, doesn't create them.

**Benefit**:
- Testable: Can inject mocks
- Flexible: Can swap implementations
- Composable: Can wrap clients (caching, retry logic, etc.)

**Alternative (Bad)**: Adapter creates its own dependencies:
```python
# BAD - Don't do this
class LLMImageParserAdapter:
    def __init__(self):
        self.llm_client = OpenAIImageClient(api_key="hardcoded")  # BAD!
        self.converter = PDFImageConverter()
```

**Why This Is Bad**:
- Can't test without real API calls
- Can't swap implementations
- Hard-coded configuration
- Violates dependency inversion

### Why Error Handling Returns Empty Lists

**Graceful Degradation**: If LLM call fails for one page, other pages can still be processed.

**Example**: PDF has 10 pages, LLM fails on page 5. We get:
- Pages 1-4: Extracted text
- Page 5: Empty string (failed)
- Pages 6-10: Extracted text

**Benefit**: Partial success is better than total failure. Extraction service can fall back to placeholder for failed pages.

**Alternative (Bad)**: Raise exception on first failure:
```python
# BAD - Don't do this
def parse(self, file_bytes: bytes, filename: str) -> list[str]:
    for page in pages:
        text = self.llm_client.process_image(page_image, prompt)
        if not text:
            raise Exception("LLM failed")  # BAD - fails entire document
        page_texts.append(text)
```

**Why This Is Bad**:
- One failed page fails entire document
- No partial success
- Wastes successful extractions

---

## Testing Strategy: Why Each Test Was Added

### Unit Tests (`test_llm_image_client.py`)

**`test_llm_client_processes_image`**
- **Why**: Verifies basic LLM API call works
- **What it verifies**: API call formatting, response parsing
- **Benefit**: Confidence that client correctly calls API

**`test_llm_client_handles_api_errors`**
- **Why**: LLM APIs can fail (rate limits, network errors, etc.)
- **What it verifies**: Error handling converts API errors to domain exceptions
- **Benefit**: Services can handle errors uniformly

**`test_llm_client_uses_custom_model`**
- **Why**: Different pages might need different models
- **What it verifies**: Model parameter override works
- **Benefit**: Flexibility without changing adapter code

### Unit Tests (`test_pdf_image_converter.py`)

**`test_converter_converts_single_page`**
- **Why**: Verify basic conversion works
- **What it verifies**: PDF page → PNG image conversion
- **Benefit**: Confidence in image conversion before LLM calls

**`test_converter_converts_all_pages`**
- **Why**: Need to convert all pages for full document extraction
- **What it verifies**: Batch conversion works correctly
- **Benefit**: Efficient processing of multi-page documents

**`test_converter_handles_invalid_page_number`**
- **Why**: Edge case handling
- **What it verifies**: Error handling for invalid inputs
- **Benefit**: Prevents crashes on bad input

### Integration Tests (`test_llm_pdf_parser.py`)

**`test_llm_parser_extracts_text_from_pdf`**
- **Why**: Verify adapter orchestrates conversion and LLM calls correctly
- **What it verifies**: End-to-end flow: PDF → Images → LLM → Text
- **Benefit**: Confidence that adapter works as expected

**`test_llm_parser_handles_llm_failures_gracefully`**
- **Why**: LLM calls can fail (rate limits, API errors, etc.)
- **What it verifies**: Partial success handling
- **Benefit**: Resilient to failures

### Service Integration Tests (`test_services.py`)

**`test_extraction_with_llm_parser`**
- **Why**: Verify service works with LLM parser
- **What it verifies**: Service correctly uses injected parser
- **Benefit**: End-to-end confidence

---

## Common Pitfalls to Avoid

### Pitfall 1: Putting LLM Logic in Services

**❌ Wrong**:
```python
# In ExtractionService
from openai import OpenAI

class ExtractionService:
    def extract(self, document: Document) -> Document:
        client = OpenAI(api_key="hardcoded")
        # LLM logic in service - BAD!
```

**✅ Correct**:
```python
# In ExtractionService
from ..application.interfaces import DocumentParser

class ExtractionService:
    def __init__(self, parsers: Sequence[DocumentParser] | None = None):
        self.parsers = list(parsers or [])  # Service doesn't know about LLM
```

**Why**: Services should orchestrate, not implement infrastructure details.

### Pitfall 2: Not Handling API Failures

**❌ Wrong**:
```python
def parse(self, file_bytes: bytes, filename: str) -> list[str]:
    for page_image in page_images:
        text = self.llm_client.process_image(page_image, prompt)
        page_texts.append(text)  # Crashes if API fails
```

**✅ Correct**:
```python
def parse(self, file_bytes: bytes, filename: str) -> list[str]:
    for page_image in page_images:
        try:
            text = self.llm_client.process_image(page_image, prompt)
            page_texts.append(text)
        except Exception:
            page_texts.append("")  # Graceful degradation
```

**Why**: API calls can fail. Handle failures gracefully.

### Pitfall 3: Making Real API Calls in Tests

**❌ Wrong**:
```python
def test_llm_parser():
    client = OpenAIImageClient(api_key=os.getenv("OPENAI_API_KEY"))
    # Makes real API calls - BAD!
```

**✅ Correct**:
```python
def test_llm_parser():
    mock_llm = MockLLMClient()
    parser = LLMImageParserAdapter(llm_client=mock_llm)
    # Uses mock - GOOD!
```

**Why**: Tests should be fast, deterministic, and free.

### Pitfall 4: Hard-Coding API Keys

**❌ Wrong**:
```python
class OpenAIImageClient:
    def __init__(self):
        self.api_key = "sk-hardcoded-key"  # BAD!
```

**✅ Correct**:
```python
class OpenAIImageClient:
    def __init__(self, api_key: str):
        self.api_key = api_key  # GOOD - injected
```

**Why**: Security, flexibility, testability.

### Pitfall 5: Not Handling Rate Limits

**❌ Wrong**:
```python
def parse(self, file_bytes: bytes, filename: str) -> list[str]:
    for page_image in page_images:
        text = self.llm_client.process_image(page_image, prompt)
        # No rate limiting - BAD!
```

**✅ Correct**:
```python
import time

def parse(self, file_bytes: bytes, filename: str) -> list[str]:
    for page_image in page_images:
        text = self.llm_client.process_image(page_image, prompt)
        time.sleep(0.1)  # Rate limiting - GOOD!
        # Or use a rate limiter library
```

**Why**: API rate limits can cause failures. Handle them.

---

## Cost and Performance Considerations

### Cost Management

**LLM API Costs**: Image processing with vision models can be expensive. Consider:

1. **Caching**: Cache LLM responses for identical pages
2. **Selective Processing**: Only use LLM for pages that fail traditional extraction
3. **Batch Processing**: Process multiple pages in single API call (if supported)
4. **Model Selection**: Use cheaper models when possible

**Example Caching Adapter**:
```python
class CachedLLMClient(LLMClient):
    """LLM client wrapper that caches responses."""
    
    def __init__(self, client: LLMClient, cache: dict[str, str]) -> None:
        self.client = client
        self.cache = cache
    
    def process_image(self, image_bytes: bytes, prompt: str, model: str | None = None) -> str:
        # Create cache key from image hash
        import hashlib
        cache_key = hashlib.sha256(image_bytes).hexdigest()
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = self.client.process_image(image_bytes, prompt, model)
        self.cache[cache_key] = result
        return result
```

### Performance Optimization

1. **Parallel Processing**: Process multiple pages concurrently
2. **Image Compression**: Reduce image size before API calls (lower costs, faster)
3. **Selective Extraction**: Only extract pages that need LLM processing
4. **Async Calls**: Use async/await for non-blocking API calls

---

## Verification Checklist

Before considering the implementation complete, verify:

- [ ] **Protocols Defined**: `LLMClient` protocol defined in `application/interfaces.py`
- [ ] **Dependencies Added**: Required libraries in `requirements.txt`
- [ ] **LLM Client Implemented**: Concrete client adapter implements protocol
- [ ] **Image Converter Implemented**: PDF-to-image conversion works
- [ ] **Parser Adapter Implemented**: LLM parser implements `DocumentParser`
- [ ] **Error Handling**: All adapters handle errors gracefully
- [ ] **Unit Tests**: LLM client, image converter, parser all have unit tests
- [ ] **Integration Tests**: Service tests verify LLM parser works
- [ ] **Container Wiring**: Adapters wired in `container.py`
- [ ] **Architectural Compliance**: `test_architecture.py` passes
- [ ] **No Service Changes**: Services don't import LLM adapters directly
- [ ] **Documentation**: Implementation documented (this guide)
- [ ] **Cost Considerations**: Rate limiting, caching considered
- [ ] **Environment Variables**: API keys configured via environment

---

## Summary: Key Takeaways

1. **LLM calls are adapters**: They live in `adapters/` and implement protocols
2. **Services don't know about LLMs**: Services depend on `DocumentParser`, not `LLMImageParserAdapter`
3. **Compose dependencies**: Adapters receive dependencies via constructor injection
4. **Handle errors gracefully**: Return empty lists, allow partial success
5. **Test with mocks**: Don't make real API calls in tests
6. **Separate concerns**: Image conversion, LLM calling, parsing are separate
7. **Consider costs**: Implement caching, rate limiting, selective processing

---

## Next Steps

When implementing LLM integration for other use cases:

1. **Follow the same pattern**: Adapter → Protocol → Service
2. **Reuse LLM client**: Same `LLMClient` protocol can be used for different purposes
3. **Compose adapters**: Build complex adapters from simpler ones
4. **Handle costs**: Consider caching, rate limiting, model selection
5. **Test thoroughly**: Mock external APIs, test error paths
6. **Document decisions**: Explain why things are done this way

---

## References

- [Extraction Service Implementation Guide](./Extraction_Service_Implementation_Guide.md) - PDF extraction example
- [Architecture Guide](./ARCHITECTURE.md) - Overall architecture documentation
- [Hexagonal Refactor Plan](./Hexagonal_Refactor_Plan.md) - Previous refactoring work

---

**This guide demonstrates how to integrate external APIs (LLMs) into the pipeline while maintaining architectural integrity. Follow this pattern for other external service integrations.**

