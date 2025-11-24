# Vector Storage Architecture: JSON Files vs DocumentDB

## Executive Summary

This document provides an in-depth analysis of how vectors are currently stored in JSON files and how this changes when switching to DocumentDB. It identifies the exact modules, services, and files responsible for vector persistence and explains the architectural implications.

## Current Architecture: JSON-Based Vector Storage

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Vector Storage Flow                          │
└─────────────────────────────────────────────────────────────────┘

1. VectorService.vectorize()
   ├─ Generates embeddings via EmbeddingGenerator
   ├─ Attaches vectors to chunks: chunk.metadata.extra["vector"]
   └─ Calls vector_store.upsert_chunks(document_id, payload)

2. InMemoryVectorStore.upsert_chunks()
   └─ Stores vectors in memory: self._store[document_id] = vectors

3. FileSystemDocumentRepository.save()
   └─ Serializes entire Document (including vectors) to JSON
      └─ artifacts/documents/<doc_id>.json
```

### Detailed Module Analysis

#### 1. Vector Generation and Attachment

**File**: `src/app/services/vector_service.py`

**Method**: `VectorService.vectorize()`

**Lines**: 54-147

**What It Does**:
- Generates embeddings for each chunk's text (using `contextualized_text`, `cleaned_text`, or `text`)
- Attaches vectors to chunks via `chunk.metadata.extra["vector"]`
- Creates a payload list with chunk data including vectors
- Calls `vector_store.upsert_chunks(document_id, payload)`

**Key Code Section**:
```122:137:src/app/services/vector_service.py
        if self.vector_store:
            payload = []
            for page in updated_pages:
                for chunk in page.chunks:
                    vector = []
                    if chunk.metadata and "vector" in chunk.metadata.extra:
                        vector = chunk.metadata.extra["vector"]
                    payload.append(
                        {
                            "chunk_id": chunk.id,
                            "page_number": chunk.page_number,
                            "vector": vector,
                            "metadata": chunk.metadata.model_dump() if chunk.metadata else {},
                        }
                    )
            self.vector_store.upsert_chunks(updated_document.id, payload)
```

**Vector Storage Location**: 
- **In-Memory**: `InMemoryVectorStore._store[document_id]` (temporary, lost on restart)
- **In Domain Model**: `chunk.metadata.extra["vector"]` (persisted to JSON)

#### 2. In-Memory Vector Store

**File**: `src/app/vector_store/in_memory.py`

**Class**: `InMemoryVectorStore`

**What It Does**:
- Implements `VectorStoreAdapter` protocol
- Stores vectors in a Python dictionary: `self._store[document_id] = list(vectors)`
- **Critical**: This is **ephemeral** - vectors are lost when the process restarts

**Key Code**:
```14:15:src/app/vector_store/in_memory.py
    def upsert_chunks(self, document_id: str, vectors: Sequence[Mapping[str, Any]]) -> None:  # noqa: D401
        self._store[document_id] = list(vectors)
```

**Limitations**:
- No persistence beyond process lifetime
- No similarity search capability
- Limited to single-process, single-machine usage

#### 3. Document JSON Persistence

**File**: `src/app/persistence/adapters/document_filesystem.py`

**Class**: `FileSystemDocumentRepository`

**Method**: `save(document: Document)`

**Lines**: 17-21

**What It Does**:
- Serializes the entire `Document` object to JSON
- Saves to `artifacts/documents/<document_id>.json`
- **Important**: This includes vectors embedded in `chunk.metadata.extra["vector"]`

**Key Code**:
```17:21:src/app/persistence/adapters/document_filesystem.py
    def save(self, document: Document) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        target = self.base_dir / f"{document.id}.json"
        with target.open("w", encoding="utf-8") as open(target, "w", encoding="utf-8") as handle:
            json.dump(document.model_dump(mode="json"), handle, indent=2)
```

**When Called**:
- After pipeline completion by `PipelineRunManager`
- Via `UploadDocumentUseCase` after document processing

**JSON Structure Example**:
```json
{
  "id": "abc-123",
  "status": "vectorized",
  "pages": [
    {
      "page_number": 1,
      "chunks": [
        {
          "id": "chunk-1",
          "text": "...",
          "metadata": {
            "extra": {
              "vector": [0.123, 0.456, ...],
              "vector_dimension": 1536
            }
          }
        }
      ]
    }
  ]
}
```

#### 4. Run Artifacts (Secondary Storage)

**File**: `src/app/persistence/adapters/filesystem.py`

**Class**: `FileSystemPipelineRunRepository`

**What It Does**:
- Saves run-specific snapshots of documents to `artifacts/runs/<run_id>/document.json`
- Saves stage outputs to `artifacts/runs/<run_id>/stages/vectorization.json`
- These also contain vectors embedded in the document structure

**Purpose**: 
- Audit trail for pipeline executions
- Debugging and analysis of specific runs
- Stage-level inspection

## New Architecture: DocumentDB Vector Storage

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│              DocumentDB Vector Storage Flow                      │
└─────────────────────────────────────────────────────────────────┘

1. VectorService.vectorize() [UNCHANGED]
   ├─ Generates embeddings
   ├─ Attaches vectors to chunks: chunk.metadata.extra["vector"]
   └─ Calls vector_store.upsert_chunks(document_id, payload)

2. DocumentDBVectorStore.upsert_chunks()
   ├─ Connects to DocumentDB (lazy connection)
   ├─ Ensures vector index exists (HNSW)
   └─ Upserts vectors to DocumentDB collection
      └─ Collection: pipeline_vectors
         └─ Documents: {document_id, chunk_id, vector, metadata, ...}

3. FileSystemDocumentRepository.save() [UNCHANGED]
   └─ Still saves Document JSON with vectors embedded
      └─ artifacts/documents/<doc_id>.json (backup/debugging)
```

### What Changes

#### 1. Vector Store Implementation

**File**: `src/app/vector_store/documentdb.py` (NEW)

**Class**: `DocumentDBVectorStore`

**What It Does**:
- Implements `VectorStoreAdapter` protocol (same interface as `InMemoryVectorStore`)
- Connects to Amazon DocumentDB using `pymongo`
- Automatically creates HNSW vector index on first use
- Stores vectors as separate documents in DocumentDB collection

**Key Differences from InMemoryVectorStore**:
- **Persistence**: Vectors survive process restarts
- **Scalability**: Can handle millions of vectors across multiple instances
- **Query Capability**: Supports similarity search via `$vectorSearch`
- **Network Access**: Requires DocumentDB connection (not local-only)

**Document Structure in DocumentDB**:
```json
{
  "_id": ObjectId("..."),
  "document_id": "abc-123",
  "chunk_id": "chunk-1",
  "page_number": 1,
  "vector": [0.123, 0.456, ...],
  "metadata": {
    "text": "...",
    "cleaned_text": "...",
    ...
  }
}
```

#### 2. VectorService (NO CHANGES)

**File**: `src/app/services/vector_service.py`

**Status**: **UNCHANGED**

**Why**: The `VectorService` depends only on the `VectorStoreAdapter` protocol, not concrete implementations. It calls `vector_store.upsert_chunks()` regardless of which adapter is used.

**Impact**: Zero code changes needed in `VectorService` when switching vector stores.

#### 3. Document JSON Files (DUAL STORAGE)

**File**: `src/app/persistence/adapters/document_filesystem.py`

**Status**: **UNCHANGED** - Still saves JSON files with vectors

**Rationale for Keeping JSON Files**:
1. **Backward Compatibility**: Existing tools/scripts that read JSON files continue to work
2. **Offline Access**: Can access document data without DocumentDB connection
3. **Debugging**: Easy to inspect document structure locally
4. **Backup**: JSON files serve as a backup of document data
5. **Development**: Local development doesn't require DocumentDB setup

**What This Means**:
- Vectors are stored in **TWO places**:
  1. **DocumentDB**: Primary storage for similarity search and production queries
  2. **JSON Files**: Secondary storage for backup, debugging, and local access

**Storage Redundancy**: This is intentional and beneficial:
- DocumentDB provides fast similarity search
- JSON files provide human-readable backup and offline access

#### 4. Container Configuration

**File**: `src/app/container.py`

**Changes**: Added `_create_vector_store()` factory method

**What It Does**:
- Selects vector store implementation based on `settings.vector_store.driver`
- Falls back to `InMemoryVectorStore` if DocumentDB initialization fails
- Logs vector store selection for observability

**Configuration-Driven Selection**:
```python
if driver == "documentdb":
    return DocumentDBVectorStore(...)
elif driver == "in_memory":
    return InMemoryVectorStore()
```

## Detailed Comparison

### Storage Locations

| Storage Type | Current (In-Memory) | New (DocumentDB) |
|--------------|-------------------|-------------------|
| **Primary Vector Store** | `InMemoryVectorStore._store` (dict) | DocumentDB collection |
| **Persistence** | ❌ Lost on restart | ✅ Persistent |
| **Scalability** | Single process | Multi-instance, millions of vectors |
| **Query Capability** | ❌ None | ✅ Similarity search via `$vectorSearch` |
| **Document JSON** | ✅ Contains vectors | ✅ Still contains vectors (backup) |
| **Run Artifacts** | ✅ Contains vectors | ✅ Still contains vectors (audit) |

### Module Responsibilities

| Module | Responsibility | Changes with DocumentDB |
|--------|---------------|------------------------|
| `VectorService` | Generate embeddings, attach to chunks, call `vector_store.upsert_chunks()` | **None** - Uses protocol interface |
| `InMemoryVectorStore` | Store vectors in memory dict | **Replaced** by `DocumentDBVectorStore` (via config) |
| `DocumentDBVectorStore` | Store vectors in DocumentDB | **New** - Implements same protocol |
| `FileSystemDocumentRepository` | Save Document JSON with embedded vectors | **None** - Continues to save JSON |
| `FileSystemPipelineRunRepository` | Save run artifacts with vectors | **None** - Continues to save artifacts |

### Data Flow Comparison

#### Current Flow (In-Memory)
```
VectorService → InMemoryVectorStore (memory dict) → [Lost on restart]
              ↓
              FileSystemDocumentRepository → JSON file (persistent backup)
```

#### New Flow (DocumentDB)
```
VectorService → DocumentDBVectorStore → DocumentDB (persistent, queryable)
              ↓
              FileSystemDocumentRepository → JSON file (backup/debugging)
```

## Migration Considerations

### Backward Compatibility

✅ **Fully Backward Compatible**:
- JSON files continue to be saved with vectors
- Existing code reading JSON files continues to work
- Can switch back to `in_memory` driver at any time

### Data Migration

If migrating existing vectors from JSON files:

1. **Read JSON Files**: Load documents from `artifacts/documents/*.json`
2. **Extract Vectors**: Extract `chunk.metadata.extra["vector"]` from each chunk
3. **Bulk Insert**: Use `DocumentDBVectorStore.upsert_chunks()` to insert into DocumentDB

**Migration Script Example**:
```python
from pathlib import Path
from src.app.persistence.adapters.document_filesystem import FileSystemDocumentRepository
from src.app.vector_store import DocumentDBVectorStore

repo = FileSystemDocumentRepository(Path("artifacts/documents"))
vector_store = DocumentDBVectorStore(...)

for doc in repo.list():
    payload = []
    for page in doc.pages:
        for chunk in page.chunks:
            if chunk.metadata and "vector" in chunk.metadata.extra:
                payload.append({
                    "chunk_id": chunk.id,
                    "page_number": chunk.page_number,
                    "vector": chunk.metadata.extra["vector"],
                    "metadata": chunk.metadata.model_dump() if chunk.metadata else {},
                })
    if payload:
        vector_store.upsert_chunks(doc.id, payload)
```

### Configuration Changes

**Environment Variables** (new):
```bash
VECTOR_STORE__DRIVER=documentdb
DOCUMENTDB_URI=mongodb://user:pass@host:port/db?tls=true&tlsCAFile=/path/to/ca.pem
DOCUMENTDB_DATABASE=pipeline_db
DOCUMENTDB_COLLECTION=pipeline_vectors
```

**No Code Changes Required**: Switching vector stores is purely configuration-driven.

## Summary

### Key Takeaways

1. **VectorService is Unchanged**: The service layer doesn't know or care which vector store is used - it uses the protocol interface.

2. **JSON Files Still Saved**: Document JSON files continue to contain vectors for backward compatibility and debugging.

3. **Dual Storage Strategy**: 
   - DocumentDB: Primary storage for production queries
   - JSON Files: Backup and offline access

4. **Zero Breaking Changes**: Existing code continues to work. Switching to DocumentDB is configuration-only.

5. **Exact Module Responsible for JSON Saving**: 
   - **`FileSystemDocumentRepository.save()`** saves the entire Document (including vectors) to JSON
   - This happens **after** vectors are stored in the vector store
   - The JSON save is **independent** of which vector store adapter is used

### Files Modified

1. ✅ `src/app/vector_store/documentdb.py` - NEW: DocumentDB adapter
2. ✅ `src/app/vector_store/__init__.py` - Export DocumentDBVectorStore
3. ✅ `src/app/container.py` - Factory method for vector store selection
4. ✅ `requirements.txt` - Add pymongo dependency

### Files Unchanged (But Still Relevant)

1. `src/app/services/vector_service.py` - Uses protocol, no changes needed
2. `src/app/persistence/adapters/document_filesystem.py` - Still saves JSON (intentional)
3. `src/app/persistence/adapters/filesystem.py` - Still saves run artifacts (intentional)

### Architecture Benefits

- **Separation of Concerns**: Vector storage is decoupled from document persistence
- **Flexibility**: Can switch vector stores without changing business logic
- **Testability**: Can mock vector store for unit tests
- **Scalability**: DocumentDB provides production-grade vector storage and querying
- **Backward Compatibility**: JSON files ensure existing tools continue to work

