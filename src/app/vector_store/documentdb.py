from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

from ..application.interfaces import VectorStoreAdapter
from ..config import settings

logger = logging.getLogger(__name__)


class DocumentDBVectorStore(VectorStoreAdapter):
    """
    Vector store adapter for Amazon DocumentDB using MongoDB-compatible API.
    
    Stores chunk vectors in DocumentDB with HNSW indexing for efficient similarity search.
    Implements the VectorStoreAdapter protocol for seamless integration with VectorService.
    
    Features:
    - Automatic HNSW index creation on first use
    - TLS/SSL encryption support (required by DocumentDB)
    - Connection pooling via pymongo
    - Document-level vector management (upsert/delete by document_id)
    """

    def __init__(
        self,
        uri: str | None = None,
        database_name: str | None = None,
        collection_name: str | None = None,
        vector_dimension: int | None = None,
        index_type: str = "hnsw",
        similarity_metric: str = "cosine",
        m: int = 16,
        ef_construction: int = 64,
    ) -> None:
        """
        Initialize DocumentDB vector store adapter.
        
        Args:
            uri: DocumentDB connection URI. If None, uses settings.vector_store.documentdb_uri
            database_name: Database name. If None, uses settings.vector_store.documentdb_database
            collection_name: Collection name. If None, uses settings.vector_store.documentdb_collection
            vector_dimension: Vector dimension. If None, uses settings.embeddings.vector_dimension
            index_type: Vector index type ("hnsw" or "ivfflat"). Default: "hnsw"
            similarity_metric: Similarity metric ("cosine", "euclidean", "dotProduct"). Default: "cosine"
            m: Max connections per node for HNSW. Default: 16
            ef_construction: Dynamic candidate list size for HNSW construction. Default: 64
        """
        # Resolve configuration from settings if not provided
        self.uri = uri or settings.vector_store.documentdb_uri
        self.database_name = database_name or settings.vector_store.documentdb_database
        self.collection_name = collection_name or settings.vector_store.documentdb_collection
        self.vector_dimension = vector_dimension or settings.embeddings.vector_dimension
        
        if not self.uri:
            raise ValueError(
                "DocumentDB URI is required. Set DOCUMENTDB_URI environment variable "
                "or pass uri parameter to DocumentDBVectorStore."
            )
        if not self.database_name:
            raise ValueError(
                "DocumentDB database name is required. Set DOCUMENTDB_DATABASE environment variable "
                "or pass database_name parameter to DocumentDBVectorStore."
            )
        
        # Index configuration
        self.index_type = index_type
        self.similarity_metric = similarity_metric
        self.m = m
        self.ef_construction = ef_construction
        
        # Initialize connection (lazy connection on first use)
        self._client: MongoClient | None = None
        self._database: Database | None = None
        self._collection: Collection | None = None
        self._index_created = False
        
        logger.info(
            "DocumentDBVectorStore initialized: database=%s, collection=%s, dimension=%d",
            self.database_name,
            self.collection_name,
            self.vector_dimension,
        )

    def _ensure_connection(self) -> None:
        """Establish connection to DocumentDB if not already connected."""
        if self._client is None:
            try:
                logger.debug("Connecting to DocumentDB: %s", self._masked_uri())
                self._client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
                # Test connection
                self._client.admin.command("ping")
                self._database = self._client[self.database_name]
                self._collection = self._database[self.collection_name]
                logger.info("Successfully connected to DocumentDB")
            except ServerSelectionTimeoutError as exc:
                logger.error("Failed to connect to DocumentDB: %s", exc)
                raise ConnectionError(f"Cannot connect to DocumentDB: {exc}") from exc
            except Exception as exc:
                logger.error("Unexpected error connecting to DocumentDB: %s", exc)
                raise

    def _masked_uri(self) -> str:
        """Return URI with password masked for logging."""
        if "@" not in self.uri:
            return self.uri
        parts = self.uri.split("@")
        if "://" in parts[0]:
            protocol_user = parts[0].split("://")
            if ":" in protocol_user[1]:
                user_pass = protocol_user[1].split(":")
                masked = f"{protocol_user[0]}://{user_pass[0]}:****@{parts[1]}"
                return masked
        return self.uri

    def _ensure_index(self) -> None:
        """Create vector index if it doesn't exist."""
        if self._index_created:
            return
        
        self._ensure_connection()
        assert self._collection is not None
        
        # Check if index already exists
        existing_indexes = self._collection.list_indexes()
        index_names = [idx["name"] for idx in existing_indexes]
        
        if "vector_index" in index_names:
            logger.info("Vector index already exists, skipping creation")
            self._index_created = True
            return
        
        # Create vector index
        try:
            logger.info(
                "Creating vector index: type=%s, dimensions=%d, similarity=%s",
                self.index_type,
                self.vector_dimension,
                self.similarity_metric,
            )
            
            vector_options: dict[str, Any] = {
                "type": self.index_type,
                "dimensions": self.vector_dimension,
                "similarity": self.similarity_metric,
            }
            
            # Add HNSW-specific parameters
            if self.index_type == "hnsw":
                vector_options["m"] = self.m
                vector_options["efConstruction"] = self.ef_construction
            
            # Use runCommand for compatibility (some drivers don't support vectorOptions in createIndex)
            self._database.command(
                {
                    "createIndexes": self.collection_name,
                    "indexes": [
                        {
                            "key": {"vector": "vector"},
                            "name": "vector_index",
                            "vectorOptions": vector_options,
                        }
                    ],
                }
            )
            
            self._index_created = True
            logger.info("Vector index created successfully")
            
        except OperationFailure as exc:
            # Index might already exist (race condition) or DocumentDB version doesn't support vector search
            if "already exists" in str(exc).lower() or "duplicate" in str(exc).lower():
                logger.info("Vector index already exists (race condition)")
                self._index_created = True
            else:
                logger.error("Failed to create vector index: %s", exc)
                raise RuntimeError(f"Cannot create vector index: {exc}") from exc
        except Exception as exc:
            logger.error("Unexpected error creating vector index: %s", exc)
            raise

    def upsert_chunks(self, document_id: str, vectors: Sequence[Mapping[str, Any]]) -> None:
        """
        Upsert chunk vectors for a document.
        
        Args:
            document_id: UUID of the document
            vectors: Sequence of chunk dictionaries with keys:
                - chunk_id: UUID of the chunk
                - page_number: Page number (int)
                - vector: List of floats (embedding vector)
                - metadata: Dict with chunk metadata
        """
        if not vectors:
            logger.debug("No vectors to upsert for document_id=%s", document_id)
            return
        
        self._ensure_connection()
        self._ensure_index()
        assert self._collection is not None
        
        # Prepare documents for upsert
        documents = []
        for vec_data in vectors:
            chunk_id = vec_data.get("chunk_id")
            if not chunk_id:
                logger.warning("Skipping vector without chunk_id: %s", vec_data)
                continue
            
            # Extract vector
            vector = vec_data.get("vector", [])
            if not vector or not isinstance(vector, list):
                logger.warning("Skipping chunk %s without valid vector", chunk_id)
                continue
            
            # Build document
            doc = {
                "document_id": document_id,
                "chunk_id": chunk_id,
                "page_number": vec_data.get("page_number", 0),
                "vector": vector,
                "metadata": vec_data.get("metadata", {}),
            }
            documents.append(doc)
        
        if not documents:
            logger.warning("No valid documents to upsert for document_id=%s", document_id)
            return
        
        # Upsert using chunk_id as unique identifier
        # Delete existing chunks for this document first to handle updates
        self._collection.delete_many({"document_id": document_id})
        
        # Insert new chunks
        try:
            result = self._collection.insert_many(documents)
            logger.info(
                "Upserted %d chunks for document_id=%s (inserted %d)",
                len(documents),
                document_id,
                len(result.inserted_ids),
            )
        except Exception as exc:
            logger.error("Failed to upsert chunks for document_id=%s: %s", document_id, exc)
            raise

    def delete_document(self, document_id: str) -> None:
        """
        Delete all vectors associated with a document.
        
        Args:
            document_id: UUID of the document to delete
        """
        self._ensure_connection()
        assert self._collection is not None
        
        try:
            result = self._collection.delete_many({"document_id": document_id})
            logger.info(
                "Deleted %d chunks for document_id=%s",
                result.deleted_count,
                document_id,
            )
        except Exception as exc:
            logger.error("Failed to delete document_id=%s: %s", document_id, exc)
            raise

    def get_vectors(self, document_id: str) -> list[Mapping[str, Any]]:
        """
        Retrieve all vectors for a document.
        
        This method is not part of the VectorStoreAdapter protocol but is useful
        for testing and debugging.
        
        Args:
            document_id: UUID of the document
            
        Returns:
            List of chunk documents with vectors
        """
        self._ensure_connection()
        assert self._collection is not None
        
        try:
            chunks = list(self._collection.find({"document_id": document_id}))
            logger.debug("Retrieved %d chunks for document_id=%s", len(chunks), document_id)
            return chunks
        except Exception as exc:
            logger.error("Failed to get vectors for document_id=%s: %s", document_id, exc)
            raise

    def close(self) -> None:
        """Close the DocumentDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._database = None
            self._collection = None
            logger.info("DocumentDB connection closed")

    def __enter__(self) -> DocumentDBVectorStore:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

