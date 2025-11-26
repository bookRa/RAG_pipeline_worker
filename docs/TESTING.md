# Testing Guide

This document provides comprehensive information about the test suite, how to run different test categories, and how to skip tests based on their requirements.

## Test Suite Overview

The test suite is designed to run **fast by default** using mock LLM providers. All unit tests complete in seconds. Only explicitly enabled integration tests require real API keys and may take longer.

### Test Categories

| Category | Description | Default Behavior | Runtime |
|----------|-------------|------------------|---------|
| **Unit Tests** | Fast tests using mock providers | ✅ Always runs | < 10 seconds |
| **Contract Tests** | Live API integration tests | ❌ Skipped unless `RUN_CONTRACT_TESTS=1` | ~30-60 seconds |
| **RAG Quality Tests** | Ragas evaluation tests | ❌ Skipped unless `RUN_RAG_TESTS=1` | ~2-5 minutes |
| **Slow Tests** | End-to-end tests marked as slow | ✅ Runs but uses mocks | < 5 seconds |

## Quick Start

### Run All Fast Tests (Default)

```bash
pytest
```

This runs all unit tests using mock providers. **No API keys required.** Completes in seconds.

### Run Specific Test Files

```bash
# Architecture compliance tests
pytest tests/test_architecture.py

# Service layer tests
pytest tests/test_services.py

# Dashboard tests
pytest tests/test_dashboard.py

# End-to-end API tests
pytest tests/test_end_to_end.py
```

### Skip Slow Tests

```bash
pytest -m "not slow"
```

## Test Configuration

### Environment Variables

The test suite uses environment variables to control behavior:

| Variable | Purpose | Default | Required For |
|----------|---------|---------|--------------|
| `RUN_CONTRACT_TESTS` | Enable contract tests | `""` (disabled) | Contract tests |
| `RUN_RAG_TESTS` | Enable RAG quality tests | `""` (disabled) | RAG evaluation |
| `LLM__PROVIDER` | LLM provider to use | `"mock"` | All tests (auto-set) |
| `EMBEDDINGS__PROVIDER` | Embeddings provider | `"mock"` | All tests (auto-set) |
| `OPENAI_API_KEY` | OpenAI API key | Unset in tests (unless RAG/contract tests enabled) | Contract/RAG tests |
| `LLM__API_KEY` | Alternative API key env var | Unset in tests (unless RAG/contract tests enabled) | Contract/RAG tests |

### Automatic Mock Configuration

The `tests/conftest.py` file automatically:
- Sets `LLM__PROVIDER=mock` and `EMBEDDINGS__PROVIDER=mock` for all tests **unless** `RUN_CONTRACT_TESTS=1` or `RUN_RAG_TESTS=1`
- Clears `OPENAI_API_KEY` and `LLM__API_KEY` to prevent accidental real API calls **unless** contract or RAG tests are enabled
- Ensures mock providers are used even if `.env` has real keys

**You don't need to configure anything** - tests use mocks by default. When you enable contract or RAG tests, the API keys are preserved so those tests can run.

## Test Files and Their Purposes

### Core Unit Tests

#### `tests/test_architecture.py`
- **Purpose**: Enforces hexagonal architecture compliance
- **What it tests**: Import boundaries, dependency flow, layer isolation
- **Runtime**: < 1 second
- **Requirements**: None

```bash
pytest tests/test_architecture.py
```

#### `tests/test_services.py`
- **Purpose**: Tests all pipeline stage services
- **What it tests**: Ingestion, parsing, cleaning, chunking, enrichment, vectorization
- **Runtime**: < 2 seconds
- **Requirements**: None (uses mocks)

```bash
pytest tests/test_services.py
```

#### `tests/test_use_cases.py`
- **Purpose**: Tests application use cases (Upload, List, Get)
- **What it tests**: Use case orchestration and error handling
- **Runtime**: < 1 second
- **Requirements**: None

```bash
pytest tests/test_use_cases.py
```

#### `tests/test_persistence_filesystem.py`
- **Purpose**: Tests filesystem repository adapters
- **What it tests**: Document storage, retrieval, segment operations
- **Runtime**: < 1 second
- **Requirements**: None

```bash
pytest tests/test_persistence_filesystem.py
```

#### `tests/test_pdf_parser.py`
- **Purpose**: Tests PDF parsing adapter
- **What it tests**: pdfplumber integration, error handling
- **Runtime**: < 2 seconds
- **Requirements**: None

```bash
pytest tests/test_pdf_parser.py
```

#### `tests/test_parsing_adapter.py`
- **Purpose**: Tests LLM-based parsing adapter
- **What it tests**: Structured output, vision parsing, streaming
- **Runtime**: < 2 seconds
- **Requirements**: None (uses mock LLM)

```bash
pytest tests/test_parsing_adapter.py
```

#### `tests/test_parsing_error_handling.py`
- **Purpose**: Tests error handling in parsing pipeline
- **What it tests**: Timeout handling, error propagation, failure tracking
- **Runtime**: < 1 second
- **Requirements**: None

```bash
pytest tests/test_parsing_error_handling.py
```

#### `tests/test_run_manager.py`
- **Purpose**: Tests pipeline run management
- **What it tests**: Async execution, progress tracking, run persistence
- **Runtime**: < 1 second
- **Requirements**: None

```bash
pytest tests/test_run_manager.py
```

#### `tests/test_phase1_schema_changes.py`
- **Purpose**: Tests schema migration and compatibility
- **What it tests**: Document model evolution, backward compatibility
- **Runtime**: < 1 second
- **Requirements**: None

```bash
pytest tests/test_phase1_schema_changes.py
```

#### `tests/test_pixmap_factory.py`
- **Purpose**: Tests pixmap generation for vision parsing
- **What it tests**: Image generation, storage, metadata
- **Runtime**: < 1 second
- **Requirements**: None

```bash
pytest tests/test_pixmap_factory.py
```

### Integration Tests

#### `tests/test_dashboard.py`
- **Purpose**: Tests dashboard UI and background pipeline execution
- **What it tests**: Page rendering, upload flow, async run tracking
- **Runtime**: < 3 seconds (uses mocks)
- **Requirements**: None (uses mocks)
- **Note**: Marked as `@pytest.mark.slow` but uses mocks, so still fast

```bash
pytest tests/test_dashboard.py
```

#### `tests/test_end_to_end.py`
- **Purpose**: End-to-end API workflow test
- **What it tests**: Upload → Process → Retrieve document flow
- **Runtime**: < 3 seconds (uses mocks)
- **Requirements**: None (uses mocks)
- **Note**: Automatically skips if real LLM provider detected

```bash
pytest tests/test_end_to_end.py
```

### Evaluation Tests

#### `tests/evaluation/test_cleaning_flags.py`
- **Purpose**: Evaluates cleaning prompt precision/recall
- **What it tests**: Segment flagging accuracy against ground truth
- **Runtime**: < 1 second (uses mocks)
- **Requirements**: None

```bash
pytest tests/evaluation/test_cleaning_flags.py
```

#### `tests/evaluation/test_rag_quality.py`
- **Purpose**: RAG pipeline quality evaluation using Ragas
- **What it tests**: Faithfulness, answer relevancy, context precision/recall
- **Runtime**: ~2-5 minutes (requires real LLM)
- **Requirements**: `RUN_RAG_TESTS=1`, `OPENAI_API_KEY` (or `LLM__API_KEY`), Ragas installed
- **Status**: ⚠️ **Skipped by default** - requires explicit opt-in

```bash
# Skip by default
pytest tests/evaluation/test_rag_quality.py  # SKIPPED

# Run explicitly (requires API key)
RUN_RAG_TESTS=1 OPENAI_API_KEY=sk-... pytest tests/evaluation/test_rag_quality.py

# Or use LLM__API_KEY
RUN_RAG_TESTS=1 LLM__API_KEY=sk-... pytest tests/evaluation/test_rag_quality.py
```

**Note**: 
- If `RUN_RAG_TESTS=1` is set but no API key is provided, the test will skip with a helpful error message.
- The test includes robust metrics extraction logic that handles various Ragas result formats.
- If metrics extraction fails, the test will print debug information about the result structure to help diagnose the issue.
- For debugging Ragas result structure, use: `RUN_RAG_TESTS=1 python tests/evaluation/debug_ragas_result.py`

#### `tests/evaluation/test_rag_langfuse_integration.py`
- **Purpose**: Integration test for Ragas + Langfuse evaluation
- **What it tests**: Trace scoring and evaluation storage
- **Runtime**: ~2-5 minutes (requires real LLM + Langfuse)
- **Requirements**: `RUN_RAG_TESTS=1`, `ENABLE_LANGFUSE=true`, API keys
- **Status**: ⚠️ **Skipped by default** - requires explicit opt-in

```bash
# Skip by default
pytest tests/evaluation/test_rag_langfuse_integration.py  # SKIPPED

# Run explicitly (requires Langfuse setup)
RUN_RAG_TESTS=1 ENABLE_LANGFUSE=true pytest tests/evaluation/test_rag_langfuse_integration.py
```

### Contract Tests

#### `tests_contracts/test_openai_contracts.py`
- **Purpose**: Live API contract tests for OpenAI integration
- **What it tests**: Real API responses, JSON mode, error handling
- **Runtime**: ~30-60 seconds
- **Requirements**: `RUN_CONTRACT_TESTS=1`, `OPENAI_API_KEY`
- **Status**: ⚠️ **Skipped by default** - requires explicit opt-in

```bash
# Skip by default
pytest tests_contracts/  # SKIPPED

# Run explicitly
RUN_CONTRACT_TESTS=1 pytest tests_contracts/
```

## Running Specific Test Categories

### Run Only Fast Unit Tests

```bash
# Exclude slow and contract tests
pytest -m "not slow and not contract"
```

### Run Only Contract Tests

```bash
RUN_CONTRACT_TESTS=1 pytest -m contract
```

### Run Only RAG Quality Tests

```bash
RUN_RAG_TESTS=1 pytest tests/evaluation/test_rag_quality.py
```

### Run All Tests (Including Slow/Contract)

```bash
RUN_CONTRACT_TESTS=1 RUN_RAG_TESTS=1 pytest
```

## Test Markers

The test suite uses pytest markers to categorize tests:

| Marker | Purpose | Usage |
|--------|---------|-------|
| `@pytest.mark.contract` | Marks contract tests | `pytest -m contract` |
| `@pytest.mark.slow` | Marks slow tests | `pytest -m "not slow"` |
| `@pytest.mark.skipif` | Conditional skipping | Used for RAG/contract tests |

### Using Markers

```bash
# Run only contract tests
pytest -m contract

# Run everything except slow tests
pytest -m "not slow"

# Run everything except contract tests
pytest -m "not contract"

# Run fast tests only (exclude both slow and contract)
pytest -m "not slow and not contract"
```

## Test Output and Debugging

### Verbose Output

```bash
# Show test names and results
pytest -v

# Show print statements
pytest -s

# Show both
pytest -v -s
```

### Stop on First Failure

```bash
pytest -x
```

### Run Specific Test

```bash
# By file
pytest tests/test_services.py

# By function
pytest tests/test_services.py::test_ingestion_updates_status

# By pattern
pytest -k "ingestion"
```

### Show Test Coverage

```bash
# Install coverage tool
pip install pytest-cov

# Run with coverage
pytest --cov=src/app --cov-report=html

# View HTML report
open htmlcov/index.html
```

## Troubleshooting

### Tests Are Slow

If tests are taking longer than expected:

1. **Check for real API calls**: Ensure `LLM__PROVIDER=mock` is set
   ```bash
   # Verify mock provider
   python -c "import os; print(os.getenv('LLM__PROVIDER', 'not set'))"
   ```

2. **Check for contract/RAG tests**: Ensure they're skipped
   ```bash
   pytest --collect-only | grep -E "(contract|rag)"
   ```

3. **Clear pytest cache**: Sometimes cache causes issues
   ```bash
   pytest --cache-clear
   ```

### Tests Fail with Import Errors

If you see import errors for optional dependencies:

- **Ragas errors**: Normal - Ragas tests are skipped unless `RUN_RAG_TESTS=1`
- **Langfuse errors**: Normal - Langfuse is optional
- **datasets errors**: Normal - Only needed for RAG evaluation

These are handled gracefully with try/except blocks.

### Tests Use Real API Keys

If tests are making real API calls:

1. **Check `.env` file**: Ensure it doesn't override test settings
2. **Check environment**: Ensure `LLM__PROVIDER=mock` is set
3. **Check conftest.py**: Verify mock configuration is active

The `tests/conftest.py` should automatically set mocks, but if you have a `.env` with `LLM__PROVIDER=openai`, it might override. The conftest clears `OPENAI_API_KEY` to prevent accidental calls.

### Contract Tests Fail

If contract tests fail:

1. **Verify API key**: Ensure `OPENAI_API_KEY` is set
   ```bash
   echo $OPENAI_API_KEY
   ```

2. **Check model access**: Ensure your API key has access to the configured model
   ```bash
   # Check configured model
   grep LLM__MODEL .env
   ```

3. **Run with verbose output**: See detailed error messages
   ```bash
   RUN_CONTRACT_TESTS=1 pytest tests_contracts/ -v -s
   ```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pytest  # Fast unit tests only
      
  contract-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: |
          RUN_CONTRACT_TESTS=1 pytest -m contract
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Best Practices

1. **Always run fast tests first**: `pytest` should complete in seconds
2. **Use markers to filter**: `pytest -m "not slow"` for quick feedback
3. **Run contract tests separately**: Only when needed, with real API keys
4. **Keep tests isolated**: Each test should be independent
5. **Use mocks by default**: Real API calls should be opt-in only

## Summary

- **Default**: `pytest` runs fast unit tests with mocks (< 10 seconds)
- **Contract tests**: `RUN_CONTRACT_TESTS=1 pytest -m contract` (requires API keys)
- **RAG tests**: `RUN_RAG_TESTS=1 pytest tests/evaluation/` (requires API keys)
- **All tests**: `RUN_CONTRACT_TESTS=1 RUN_RAG_TESTS=1 pytest` (requires API keys)

The test suite is designed to be fast and reliable by default, with optional integration tests available when needed.

