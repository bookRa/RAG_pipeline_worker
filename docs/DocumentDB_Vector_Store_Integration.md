# DocumentDB Vector Store Integration

## Overview

This document outlines the integration of Amazon DocumentDB's Vector Search capability into the RAG pipeline worker, replacing the in-memory vector store with a persistent, scalable database-backed solution.

## Architectural Decisions

### 1. Why DocumentDB?

**Decision**: Use Amazon DocumentDB 5.0+ with Vector Search support as the primary vector store.

**Rationale**:
- **Managed Service**: DocumentDB is a fully managed AWS service, reducing operational overhead
- **MongoDB Compatibility**: Uses MongoDB-compatible API, allowing use of standard `pymongo` driver
- **Vector Search Native**: Built-in HNSW and IVFFlat indexing for efficient similarity search
- **Scalability**: Can handle large-scale vector storage and querying
- **Integration**: Seamlessly integrates with existing AWS infrastructure
- **Production-Ready**: Supports up to 2,000 dimensions with indexing, 16,000 without

**Trade-offs**:
- Requires AWS infrastructure (not suitable for local-only development)
- Additional cost compared to in-memory storage
- Network latency vs local storage

### 2. Adapter Pattern

**Decision**: Implement `DocumentDBVectorStore` as a separate adapter implementing the `VectorStoreAdapter` protocol.

**Rationale**:
- **Hexagonal Architecture**: Maintains separation between domain logic and infrastructure
- **Swappable Implementations**: Allows switching between `InMemoryVectorStore` and `DocumentDBVectorStore` via configuration
- **Testability**: Can mock or substitute vector store implementations for testing
- **Future-Proof**: Easy to add additional vector store implementations (e.g., Pinecone, Weaviate)

**Implementation Location**: `src/app/vector_store/documentdb.py`

### 3. Index Strategy

**Decision**: Use HNSW (Hierarchical Navigable Small World) index type by default.

**Rationale**:
- **Performance**: Better query performance and recall compared to IVFFlat
- **Dynamic Updates**: Handles incremental updates better than IVFFlat
- **No Training Required**: Can be created without initial data load
- **Production-Ready**: Recommended by AWS for most use cases

**Configuration**:
- `m`: 16 (max connections per node) - default, balances performance and memory
- `efConstruction`: 64 (dynamic candidate list size) - default, balances build time and quality
- `similarity`: "cosine" (default) - standard for text embeddings

### 4. Data Model

**Decision**: Store vectors as documents with the following structure:

```json
{
  "_id": ObjectId("..."),
  "document_id": "uuid-of-document",
  "chunk_id": "uuid-of-chunk",
  "page_number": 1,
  "vector": [0.123, 0.456, ...],
  "metadata": {
    "text": "...",
    "cleaned_text": "...",
    "contextualized_text": "...",
    ...
  },
  "created_at": ISODate("...")
}
```

**Rationale**:
- **Document-Centric**: Each chunk is a separate document, enabling efficient updates/deletes
- **Metadata Preservation**: Stores full chunk metadata alongside vectors for retrieval
- **Query Flexibility**: Can filter by `document_id`, `page_number`, or search by vector similarity
- **Indexing**: Vector field can be indexed for similarity search

### 5. Connection Management

**Decision**: Use `pymongo.MongoClient` with TLS/SSL enabled for DocumentDB connections.

**Rationale**:
- **Security**: DocumentDB requires TLS encryption
- **Standard Library**: `pymongo` is the official MongoDB driver, well-maintained and documented
- **Connection Pooling**: Built-in connection pooling for efficient resource usage
- **AWS Integration**: Can use AWS IAM authentication or username/password

**Configuration**:
- Connection string via `DOCUMENTDB_URI` environment variable
- Database name via `DOCUMENTDB_DATABASE` environment variable
- Collection name via `DOCUMENTDB_COLLECTION` (default: "pipeline_vectors")

### 6. Index Creation Strategy

**Decision**: Create vector index automatically on first use if it doesn't exist.

**Rationale**:
- **Convenience**: Reduces manual setup steps
- **Idempotency**: Checks for existing index before creation
- **Configuration-Driven**: Uses embedding dimension from settings

**Implementation**:
- Check for existing index using `getIndexes()`
- Create HNSW index if missing with dimensions from `settings.embeddings.vector_dimension`
- Log index creation for observability

## Current Storage Mechanism Analysis

### How JSON Files Are Currently Saved

**Location**: `src/app/persistence/adapters/document_filesystem.py`

**Process**:
1. **Vector Generation**: `VectorService.vectorize()` generates embeddings and attaches them to chunks via `chunk.metadata.extra["vector"]`
2. **Vector Store Upsert**: `VectorService` calls `vector_store.upsert_chunks(document_id, payload)` with chunk data
3. **In-Memory Storage**: `InMemoryVectorStore` stores vectors in a dictionary (`self._store[document_id]`)
4. **Document Persistence**: `FileSystemDocumentRepository.save()` serializes the entire `Document` object (including vectors in chunk metadata) to JSON at `artifacts/documents/<doc_id>.json`

**Key Files**:
- `src/app/services/vector_service.py` (lines 122-137): Calls `vector_store.upsert_chunks()`
- `src/app/vector_store/in_memory.py`: Stores vectors in memory dictionary
- `src/app/persistence/adapters/document_filesystem.py` (lines 17-21): Saves document JSON including vectors

### How This Changes with DocumentDB

**What Changes**:
1. **Vector Storage**: Vectors move from in-memory dictionary to DocumentDB collection
2. **Persistence**: Vectors are now persisted in DocumentDB, not just in document JSON files
3. **Query Capability**: Can perform similarity search directly on DocumentDB using `$vectorSearch`

**What Stays the Same**:
1. **Document JSON Files**: Still saved to `artifacts/documents/<doc_id>.json` with vectors embedded
   - **Rationale**: Maintains backward compatibility, enables offline access, provides audit trail
2. **Vector Service Interface**: `VectorService` still calls `vector_store.upsert_chunks()` - no changes needed
3. **Chunk Metadata**: Vectors still attached to chunks in the domain model

**Dual Storage Strategy**:
- **DocumentDB**: Primary vector store for similarity search and production queries
- **JSON Files**: Secondary storage for backup, debugging, and local development

## Implementation Details

### Required Packages

```bash
pip install pymongo>=4.0.0
```

**Note**: `boto3` is NOT required for basic DocumentDB connectivity. It's only needed if:
- Using AWS IAM authentication (DocumentDB supports username/password by default)
- Interacting with other AWS services

### Connection String Format

DocumentDB connection strings follow MongoDB format:
```
mongodb://username:password@host:port/database?tls=true&tlsCAFile=/path/to/rds-ca-bundle.pem
```

For AWS DocumentDB, TLS is required. The CA certificate can be downloaded from AWS.

### Vector Index Creation

The adapter automatically creates an HNSW index on first use:

```python
collection.create_index(
    [("vector", "vector")],
    name="vector_index",
    vectorOptions={
        "type": "hnsw",
        "dimensions": 1536,  # From settings.embeddings.vector_dimension
        "similarity": "cosine",
        "m": 16,
        "efConstruction": 64
    }
)
```

### Query Pattern

For similarity search (future enhancement):

```python
results = collection.aggregate([
    {
        "$search": {
            "vectorSearch": {
                "vector": query_vector,
                "path": "vector",
                "similarity": "cosine",
                "k": 10,
                "efSearch": 40
            }
        }
    }
])
```

## Configuration

### Environment Variables

```bash
# DocumentDB Connection
DOCUMENTDB_URI=mongodb://user:pass@docdb-cluster.cluster-xxx.us-east-1.docdb.amazonaws.com:27017/pipeline_db?tls=true&tlsCAFile=/path/to/rds-ca-bundle.pem
DOCUMENTDB_DATABASE=pipeline_db
DOCUMENTDB_COLLECTION=pipeline_vectors

# Vector Store Selection
VECTOR_STORE__DRIVER=documentdb  # Options: in_memory, documentdb
```

### Settings Configuration

The `VectorStoreSettings` class in `src/app/config.py` already includes DocumentDB configuration:

```python
class VectorStoreSettings(BaseModel):
    driver: Literal["in_memory", "llama_index_local", "documentdb"] = "llama_index_local"
    documentdb_uri: str | None = None
    documentdb_database: str | None = None
    documentdb_collection: str = "pipeline_vectors"
```

## Migration Path

### Development → Production

1. **Development**: Use `in_memory` driver (current default)
2. **Staging**: Switch to `documentdb` with test cluster
3. **Production**: Use `documentdb` with production cluster

### Data Migration

If migrating existing vectors from JSON files:

1. Read vectors from `artifacts/documents/*.json`
2. Extract chunk vectors from `chunk.metadata.extra["vector"]`
3. Bulk insert into DocumentDB using `upsert_chunks()`

## Testing Strategy

### Unit Tests
- Mock `pymongo.MongoClient` and `Collection`
- Test `upsert_chunks()`, `delete_document()`, `get_vectors()`
- Verify index creation logic

### Integration Tests
- Use test DocumentDB cluster or MongoDB Atlas (MongoDB-compatible)
- Test actual database operations
- Verify vector similarity search queries

### Contract Tests
- Ensure `DocumentDBVectorStore` implements `VectorStoreAdapter` protocol
- Verify interface compatibility with `InMemoryVectorStore`

## Observability

The adapter logs:
- Connection establishment
- Index creation events
- Upsert/delete operations (with document_id)
- Error conditions (connection failures, index creation failures)

## Future Enhancements

1. **Similarity Search**: Implement `query()` method using `$vectorSearch`
2. **Batch Operations**: Optimize bulk upserts for large documents
3. **Connection Pooling**: Tune connection pool settings for high throughput
4. **Index Management**: Add methods to recreate/update indexes
5. **Monitoring**: Add metrics for query performance, index size, etc.

## References

- [Amazon DocumentDB Vector Search Documentation](https://docs.aws.amazon.com/documentdb/latest/developerguide/vector-search.html)
- [PyMongo Documentation](https://pymongo.readthedocs.io/)
- [MongoDB Vector Search Guide](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/)

