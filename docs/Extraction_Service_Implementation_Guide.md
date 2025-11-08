# Extraction Service Implementation Guide

## Introduction

This guide documents the implementation of real PDF text extraction for the extraction service, replacing the previous stub/placeholder implementation. This iteration serves as a **best-practice example** for implementing changes to services while maintaining strict adherence to hexagonal architecture principles.

**Purpose**: This guide demonstrates how to:
- Replace stub implementations with real functionality
- Maintain architectural boundaries and dependency flow
- Write comprehensive tests that verify both functionality and architecture
- Document decisions and rationale for future developers

---

## Architectural Context

### Where Does the Extraction Service Fit?

The extraction service is part of the **application services layer** in our hexagonal architecture:

```
┌─────────────────────────────────────────┐
│         API Layer (FastAPI)             │
│  ┌───────────────────────────────────┐  │
│  │      Use Cases                    │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │   Services                  │  │  │
│  │  │   (ExtractionService)       │  │  │
│  │  │   ┌──────────────────────┐ │  │  │
│  │  │   │  Ports/Interfaces    │ │  │  │
│  │  │   │  (DocumentParser)    │ │  │  │
│  │  │   └──────────────────────┘ │  │  │
│  │  └─────────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │   Adapters                       │  │
│  │   (PdfParserAdapter)            │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**Key Architectural Points**:

1. **ExtractionService** (in `services/`) orchestrates the extraction process
2. **DocumentParser** (in `application/interfaces.py`) is the **port** (protocol/interface)
3. **PdfParserAdapter** (in `adapters/`) is the **adapter** (concrete implementation)
4. The service depends on the **port**, not the adapter (dependency inversion)
5. The adapter implements the port and lives in the infrastructure layer

### Why This Architecture?

**Separation of Concerns**: The service doesn't know or care about PDF parsing libraries. It only knows about the `DocumentParser` protocol. This means:
- We can swap PDF libraries without changing the service
- We can add new file type parsers (DOCX, PPT) without modifying the service
- The service remains testable with stub parsers

**Dependency Inversion**: The service depends on abstractions (protocols), not concrete implementations. This enables:
- Easy testing with mock parsers
- Flexible composition of parsers
- Clear boundaries between layers

---

## Step-by-Step Implementation

### Step 1: Add External Dependency

**What we did**: Added `pdfplumber` to `requirements.txt`

**Why**: We need a Python library to extract text from PDF files. `pdfplumber` was chosen because:
- It's modern and actively maintained
- Handles tables and structured content well
- Has good error handling
- More robust than alternatives like PyPDF2

**Architectural Note**: External libraries belong in adapters, not services. The service never imports `pdfplumber` directly.

**File Changed**: `requirements.txt`

```python
pdfplumber
```

---

### Step 2: Implement Real PDF Parser Adapter

**What we did**: Replaced the stub implementation in `src/app/adapters/pdf_parser.py` with real PDF extraction logic.

**Key Implementation Details**:

1. **Protocol Compliance**: The adapter implements `DocumentParser` protocol
   ```python
   class PdfParserAdapter(DocumentParser):
       supported_types: Sequence[str] = ("pdf",)
       
       def supports_type(self, file_type: str) -> bool: ...
       def parse(self, file_bytes: bytes, filename: str) -> list[str]: ...
   ```

2. **Error Handling**: Returns empty list on errors rather than raising exceptions
   - **Rationale**: Allows the extraction service to fall back to placeholder text
   - **Benefit**: Graceful degradation instead of crashes

3. **Page-by-Page Extraction**: Extracts text from each page separately
   - **Rationale**: Matches the domain model (Document contains Pages)
   - **Benefit**: Preserves page boundaries for downstream processing

**Architectural Decisions Explained**:

**Why is the adapter in `adapters/` directory?**
- Adapters are infrastructure concerns - they interact with external systems (PDF files, libraries)
- Keeping them separate from services maintains clear boundaries
- Services can be tested without real adapters

**Why does it implement a protocol?**
- The protocol (`DocumentParser`) defines the contract
- The service depends on the protocol, not the concrete adapter
- This enables dependency inversion - high-level code (service) doesn't depend on low-level code (adapter)

**Why doesn't the service know about pdfplumber?**
- The service should be framework/library agnostic
- If we need to change PDF libraries, we only modify the adapter
- The service remains testable with stub parsers

**File Changed**: `src/app/adapters/pdf_parser.py`

**Key Code**:
```python
def parse(self, file_bytes: bytes, filename: str) -> list[str]:
    """Extract text from PDF file bytes, returning one string per page."""
    if not file_bytes:
        return []
    
    try:
        pdf_file = io.BytesIO(file_bytes)
        page_texts: list[str] = []
        
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                page_texts.append(page_text)
        
        return page_texts
    except Exception:
        # Graceful degradation - catches all PDF parsing errors
        # pdfplumber raises PdfminerException (from pdfplumber.utils.exceptions)
        # which wraps pdfminer errors. Catching Exception catches all of these.
        return []
```

---

### Step 3: Add Unit Tests for PDF Parser Adapter

**What we did**: Created `tests/test_pdf_parser.py` with comprehensive unit tests.

**Test Strategy**:

1. **Protocol Compliance Tests**: Verify the adapter correctly implements `DocumentParser`
   - **Why**: Ensures the adapter can be used wherever a `DocumentParser` is expected
   - **Benefit**: Catches interface violations early

2. **Functional Tests**: Test extraction from real PDF files
   - **Why**: Verifies the adapter actually works with real data
   - **Benefit**: Confidence that the implementation is correct

3. **Edge Case Tests**: Test error handling (empty bytes, corrupted PDFs)
   - **Why**: Ensures graceful degradation
   - **Benefit**: Prevents crashes in production

4. **Isolation**: Tests run independently without services
   - **Why**: Fast execution, clear failure points
   - **Benefit**: Easy to debug when tests fail

**Rationale for Test Structure**:

**Why unit tests for the adapter?**
- Test the adapter in isolation
- Verify it correctly implements the protocol
- Test edge cases specific to PDF parsing
- Fast execution (no service dependencies)

**Why not test the service here?**
- Service tests belong in `test_services.py`
- Separation of concerns: adapter tests vs. service tests
- Each layer tested independently

**File Created**: `tests/test_pdf_parser.py`

**Example Test**:
```python
def test_parse_extracts_text_from_real_pdf():
    """Test that parser extracts text from a real PDF file."""
    parser = PdfParserAdapter()
    test_pdf_path = Path(__file__).parent / "test_document.pdf"
    pdf_bytes = test_pdf_path.read_bytes()
    page_texts = parser.parse(pdf_bytes, "test_document.pdf")
    
    assert len(page_texts) == 10  # Verify page count (test_document.pdf has 10 pages)
    assert all(isinstance(text, str) for text in page_texts)
```

---

### Step 4: Update Extraction Service Tests

**What we did**: Added integration tests in `tests/test_services.py` that verify the service works with the real PDF parser.

**Test Strategy**:

1. **Kept Existing Stub Parser Tests**: Tests that use stub parsers remain unchanged
   - **Why**: Fast, isolated unit tests for service logic
   - **Benefit**: Quick feedback during development

2. **Added Real Parser Integration Tests**: New tests use `PdfParserAdapter`
   - **Why**: Verify end-to-end behavior with real adapters
   - **Benefit**: Confidence that the full system works

3. **Test Both Code Paths**: Test with `file_bytes` parameter and with stored file path
   - **Why**: Verify both ways of providing PDF data work
   - **Benefit**: Comprehensive coverage

**Rationale for Test Structure**:

**Why keep stub parser tests?**
- Fast execution (no file I/O)
- Test service logic independently of adapter implementation
- Easy to understand what the service does vs. what the adapter does

**Why add real parser tests?**
- Verify the integration actually works
- Catch issues with real PDF files
- Ensure the service correctly uses the injected parser

**File Modified**: `tests/test_services.py`

**Example Test**:
```python
def test_extraction_with_real_pdf_parser():
    """Test that extraction service works with the real PDF parser adapter."""
    pdf_bytes = test_pdf_path.read_bytes()
    pdf_parser = PdfParserAdapter()
    extraction = ExtractionService(observability=observability, parsers=[pdf_parser])
    
    result = extraction.extract(document, file_bytes=pdf_bytes)
    
    assert result.status == "extracted"
    assert len(result.pages) == 10  # test_document.pdf has 10 pages
```

---

### Step 5: Verify Architectural Compliance

**What we did**: Verified that no architectural violations were introduced.

**Verification Steps**:

1. **Services Don't Import Adapters**: Verified services don't import `PdfParserAdapter` directly
   - **Check**: `grep -r "from.*pdf_parser" src/app/services/`
   - **Result**: No matches ✓

2. **Domain Doesn't Import Infrastructure**: Verified domain layer remains pure
   - **Check**: `grep -r "pdfplumber\|pdf_parser" src/app/domain/`
   - **Result**: No matches ✓

3. **Adapter Implements Protocol**: Verified adapter correctly implements `DocumentParser`
   - **Check**: Code review of `PdfParserAdapter`
   - **Result**: Implements all required methods ✓

4. **Dependency Flow**: Verified dependencies point inward
   - **Service** → **Protocol** → **Adapter** ✓
   - **Adapter** → **Protocol** ✓
   - **Service** ↛ **Adapter** ✓

**Why This Matters**:

**Architectural tests catch violations automatically**:
- `test_architecture.py` verifies import rules
- Prevents accidental coupling between layers
- Ensures maintainability over time

**File Verified**: `tests/test_architecture.py` (should pass without modification)

---

## Rationale: Why Things Are Done This Way

### Why Adapters Are Separate from Services

**Separation of Concerns**: Adapters handle infrastructure details (file formats, external libraries), while services handle business logic (orchestration, state management).

**Example**: The `ExtractionService` doesn't know about PDF files, PDF libraries, or how to parse PDFs. It only knows:
- There are parsers that can parse documents
- Parsers have a `parse()` method
- Parsers return a list of page texts

**Benefit**: If we need to support a new file format (e.g., EPUB), we:
1. Create a new adapter (`EpubParserAdapter`)
2. Wire it in the container
3. No changes to the service needed

### Why Protocols/Interfaces Enable Testability

**Dependency Inversion**: Services depend on abstractions (protocols), not concrete implementations.

**Example**: `ExtractionService` accepts `Sequence[DocumentParser]`, not `list[PdfParserAdapter]`.

**Benefit**: In tests, we can inject stub parsers:
```python
class StubParser:
    def parse(self, file_bytes: bytes, filename: str) -> list[str]:
        return ["Page One", "Page Two"]

extraction = ExtractionService(parsers=[StubParser()])
```

**Why This Matters**: 
- Tests run fast (no file I/O)
- Tests are deterministic (stub returns known values)
- Tests isolate service logic from adapter implementation

### Why Dependency Injection Is Used

**Inversion of Control**: Dependencies are provided to services, not created by them.

**Example**: `ExtractionService.__init__()` accepts `parsers` as a parameter:
```python
def __init__(self, parsers: Sequence[DocumentParser] | None = None):
    self.parsers = list(parsers or [])
```

**Benefit**:
- Services are testable (inject mocks)
- Services are flexible (different parsers for different scenarios)
- Services are composable (container wires dependencies)

**Alternative (Bad)**: Service creates its own parser:
```python
# BAD - Don't do this
def __init__(self):
    self.parser = PdfParserAdapter()  # Hard-coded dependency
```

**Why This Is Bad**:
- Can't test without real PDF parser
- Can't swap implementations
- Violates dependency inversion principle

### Why Tests Are Structured This Way

**Unit Tests (Adapter)**: Test the adapter in isolation
- **Location**: `tests/test_pdf_parser.py`
- **Purpose**: Verify adapter works correctly
- **Dependencies**: Only the adapter and test PDF file

**Integration Tests (Service)**: Test service with real adapters
- **Location**: `tests/test_services.py`
- **Purpose**: Verify end-to-end behavior
- **Dependencies**: Service, adapter, test PDF file

**Architectural Tests**: Verify architectural rules
- **Location**: `tests/test_architecture.py`
- **Purpose**: Prevent architectural violations
- **Dependencies**: AST parsing of source code

**Why This Structure**:
- **Fast feedback**: Unit tests run quickly
- **Confidence**: Integration tests verify real behavior
- **Maintainability**: Architectural tests prevent technical debt

---

## Testing Strategy: Why Each Test Was Added

### Unit Tests (`test_pdf_parser.py`)

**`test_pdf_parser_implements_document_parser_protocol`**
- **Why**: Ensures the adapter can be used wherever a `DocumentParser` is expected
- **What it verifies**: Protocol compliance
- **Benefit**: Catches interface violations at test time

**`test_supports_type_accepts_pdf`**
- **Why**: Verifies file type detection works correctly
- **What it verifies**: `supports_type()` method behavior
- **Benefit**: Ensures correct parser selection

**`test_parse_extracts_text_from_real_pdf`**
- **Why**: Verifies the adapter actually extracts text from PDFs
- **What it verifies**: Functional correctness with real data
- **Benefit**: Confidence that the implementation works

**`test_parse_handles_empty_bytes`**
- **Why**: Ensures graceful handling of edge cases
- **What it verifies**: Error handling for empty input
- **Benefit**: Prevents crashes on invalid input

**`test_parse_handles_corrupted_pdf`**
- **Why**: Ensures graceful degradation on corrupted files
- **What it verifies**: Error handling for invalid PDFs
- **Benefit**: System doesn't crash on bad input

### Integration Tests (`test_services.py`)

**`test_extraction_with_real_pdf_parser`**
- **Why**: Verifies the service correctly uses the real PDF parser
- **What it verifies**: End-to-end extraction flow
- **Benefit**: Confidence that service and adapter work together

**`test_extraction_with_real_pdf_parser_from_stored_path`**
- **Why**: Verifies extraction works when reading from stored file path
- **What it verifies**: Both code paths (file_bytes vs. stored path)
- **Benefit**: Comprehensive coverage of service behavior

**Existing stub parser tests (kept unchanged)**
- **Why**: Fast, isolated tests for service logic
- **What they verify**: Service behavior independent of adapter
- **Benefit**: Quick feedback during development

---

## Common Pitfalls to Avoid

### Pitfall 1: Importing Concrete Adapters in Services

**❌ Wrong**:
```python
# In ExtractionService
from ..adapters.pdf_parser import PdfParserAdapter

def __init__(self):
    self.parser = PdfParserAdapter()  # BAD!
```

**✅ Correct**:
```python
# In ExtractionService
from ..application.interfaces import DocumentParser

def __init__(self, parsers: Sequence[DocumentParser] | None = None):
    self.parsers = list(parsers or [])  # GOOD!
```

**Why**: Services should depend on protocols, not concrete implementations.

### Pitfall 2: Raising Exceptions Instead of Graceful Degradation

**❌ Wrong**:
```python
def parse(self, file_bytes: bytes, filename: str) -> list[str]:
    pdf = pdfplumber.open(io.BytesIO(file_bytes))
    # Raises exception on corrupted PDF - BAD!
```

**✅ Correct**:
```python
def parse(self, file_bytes: bytes, filename: str) -> list[str]:
    try:
        pdf = pdfplumber.open(io.BytesIO(file_bytes))
        # ...
    except Exception:
        return []  # Graceful degradation - catches all PDF errors
```

**Why**: Allows the service to fall back to placeholder text instead of crashing.

### Pitfall 3: Testing Only with Stub Parsers

**❌ Wrong**:
```python
# Only test with stub parser
def test_extraction():
    parser = StubParser()
    # Never test with real parser
```

**✅ Correct**:
```python
# Test with both stub and real parser
def test_extraction_with_stub():
    parser = StubParser()
    # Fast, isolated test

def test_extraction_with_real_pdf_parser():
    parser = PdfParserAdapter()
    # Integration test with real adapter
```

**Why**: Stub tests verify service logic, real parser tests verify integration.

### Pitfall 4: Modifying Service When Adding Adapters

**❌ Wrong**:
```python
# Adding new parser requires service changes
class ExtractionService:
    def __init__(self):
        self.pdf_parser = PdfParserAdapter()
        self.docx_parser = DocxParserAdapter()  # Service knows about adapters
```

**✅ Correct**:
```python
# Service doesn't change when adding parsers
class ExtractionService:
    def __init__(self, parsers: Sequence[DocumentParser] | None = None):
        self.parsers = list(parsers or [])  # Service doesn't know about adapters
```

**Why**: Service should be adapter-agnostic. Container wires adapters.

### Pitfall 5: Skipping Architectural Verification

**❌ Wrong**:
```python
# Implement feature, skip architecture tests
# Hope everything is okay
```

**✅ Correct**:
```python
# Run architecture tests after implementation
pytest tests/test_architecture.py
# Verify no violations introduced
```

**Why**: Architectural tests catch violations automatically. Don't skip them.

---

## Verification Checklist

Before considering the implementation complete, verify:

- [ ] **Dependency Added**: External library added to `requirements.txt`
- [ ] **Adapter Implemented**: Adapter implements the protocol correctly
- [ ] **Error Handling**: Adapter handles errors gracefully (returns empty list, doesn't crash)
- [ ] **Unit Tests**: Adapter has comprehensive unit tests
- [ ] **Integration Tests**: Service has tests with real adapter
- [ ] **Architectural Compliance**: `test_architecture.py` passes
- [ ] **No Service Changes**: Service doesn't import concrete adapters
- [ ] **Container Wiring**: Adapter is wired in `container.py` (if not already done)
- [ ] **Documentation**: Implementation is documented (this guide)

---

## Summary: Key Takeaways

1. **Adapters belong in `adapters/`**: Infrastructure concerns are separate from business logic
2. **Services depend on protocols**: Use dependency inversion, not concrete imports
3. **Test in layers**: Unit tests for adapters, integration tests for services
4. **Verify architecture**: Run architectural tests to prevent violations
5. **Graceful degradation**: Handle errors gracefully, don't crash
6. **Document decisions**: Explain why things are done this way

---

## Next Steps for Other Services

When implementing similar changes for other services (e.g., cleaning, chunking, enrichment):

1. **Follow the same pattern**: Adapter → Protocol → Service
2. **Write tests at each layer**: Unit tests for adapters, integration tests for services
3. **Verify architecture**: Run `test_architecture.py` after changes
4. **Document rationale**: Explain architectural decisions
5. **Keep services adapter-agnostic**: Services shouldn't know about concrete adapters

---

## References

- [Architecture Guide](./ARCHITECTURE.md) - Overall architecture documentation
- [Hexagonal Refactor Plan](./Hexagonal_Refactor_Plan.md) - Previous refactoring work
- [Round 1 Requirements](./Round_1_Requirements.md) - Product requirements

---

**This guide serves as a template for future service iterations. Follow this pattern to maintain architectural integrity while adding new functionality.**

