# DocumentDB Vector Store Integration - Summary

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install `pymongo>=4.0.0` required for DocumentDB connectivity.

### 2. Configure Environment

Add to your `.env` file:

```bash
# Vector Store Selection
VECTOR_STORE__DRIVER=documentdb

# DocumentDB Connection
DOCUMENTDB_URI=mongodb://username:password@your-cluster.cluster-xxx.region.docdb.amazonaws.com:27017/database_name?tls=true&tlsCAFile=/path/to/rds-ca-bundle.pem
DOCUMENTDB_DATABASE=pipeline_db
DOCUMENTDB_COLLECTION=pipeline_vectors
```

### 3. Download DocumentDB CA Certificate

DocumentDB requires TLS. Download the CA certificate:

```bash
wget https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
```

Reference it in your connection string via `tlsCAFile` parameter.

### 4. Run the Application

The application will automatically:
- Connect to DocumentDB on first vector operation
- Create HNSW vector index if it doesn't exist
- Store vectors in DocumentDB collection

## Architecture Overview

### Components Created

1. **`DocumentDBVectorStore`** (`src/app/vector_store/documentdb.py`)
   - Implements `VectorStoreAdapter` protocol
   - Handles DocumentDB connection and indexing
   - Stores vectors as documents in DocumentDB collection

2. **Factory Method** (`src/app/container.py::_create_vector_store()`)
   - Selects vector store based on configuration
   - Falls back to in-memory store if DocumentDB unavailable

### What Stays the Same

- ✅ `VectorService` - No changes (uses protocol interface)
- ✅ `FileSystemDocumentRepository` - Still saves JSON files with vectors
- ✅ `FileSystemPipelineRunRepository` - Still saves run artifacts
- ✅ All existing code continues to work

### What Changes

- ✅ Vector storage moves from in-memory dict to DocumentDB
- ✅ Vectors are now persistent across restarts
- ✅ Can perform similarity search queries (future enhancement)

## Key Files

| File | Purpose | Status |
|------|---------|--------|
| `src/app/vector_store/documentdb.py` | DocumentDB adapter implementation | ✅ New |
| `src/app/vector_store/in_memory.py` | In-memory adapter (existing) | ✅ Unchanged |
| `src/app/container.py` | Vector store factory | ✅ Updated |
| `src/app/services/vector_service.py` | Vector generation service | ✅ Unchanged |
| `src/app/persistence/adapters/document_filesystem.py` | JSON document storage | ✅ Unchanged (still saves JSON) |
| `requirements.txt` | Python dependencies | ✅ Updated (added pymongo) |

## Documentation

- **[DocumentDB_Vector_Store_Integration.md](./DocumentDB_Vector_Store_Integration.md)**: Comprehensive integration guide with architectural decisions
- **[Vector_Storage_Architecture_Analysis.md](./Vector_Storage_Architecture_Analysis.md)**: Detailed analysis of JSON storage vs DocumentDB

## Testing

### Unit Tests

Mock `pymongo.MongoClient` to test adapter logic:

```python
from unittest.mock import Mock, MagicMock
from src.app.vector_store import DocumentDBVectorStore

mock_client = Mock()
mock_collection = Mock()
# ... setup mocks ...
store = DocumentDBVectorStore(uri="mongodb://test", database_name="test")
store._client = mock_client
store._collection = mock_collection
```

### Integration Tests

Use a test DocumentDB cluster or MongoDB Atlas (MongoDB-compatible) for integration testing.

## Troubleshooting

### Connection Issues

**Error**: `Cannot connect to DocumentDB`

**Solutions**:
1. Verify `DOCUMENTDB_URI` is correct
2. Ensure TLS is enabled (`tls=true` in connection string)
3. Check network connectivity (security groups, VPC)
4. Verify credentials are correct

### Index Creation Issues

**Error**: `Cannot create vector index`

**Solutions**:
1. Ensure DocumentDB version is 5.0+
2. Verify vector dimension matches `settings.embeddings.vector_dimension`
3. Check DocumentDB instance has sufficient resources

### Fallback Behavior

If DocumentDB initialization fails, the container automatically falls back to `InMemoryVectorStore` and logs a warning. Check logs for details.

## Next Steps

1. **Similarity Search**: Implement `query()` method using `$vectorSearch` operator
2. **Batch Operations**: Optimize bulk upserts for large documents
3. **Monitoring**: Add metrics for query performance and index health
4. **Migration**: Create script to migrate existing vectors from JSON files

## References

- [Amazon DocumentDB Vector Search Docs](https://docs.aws.amazon.com/documentdb/latest/developerguide/vector-search.html)
- [PyMongo Documentation](https://pymongo.readthedocs.io/)

