from fastapi import APIRouter, File, HTTPException, UploadFile

from ..domain.models import Document
from ..services.chunking_service import ChunkingService
from ..services.cleaning_service import CleaningService
from ..services.enrichment_service import EnrichmentService
from ..services.extraction_service import ExtractionService
from ..services.ingestion_service import IngestionService
from ..services.pipeline_runner import PipelineRunner
from ..services.vector_service import VectorService

router = APIRouter()

ALLOWED_EXTENSIONS = {"pdf", "docx", "ppt", "pptx"}
DOCUMENT_STORE: dict[str, Document] = {}

ingestion_service = IngestionService()
extraction_service = ExtractionService()
cleaning_service = CleaningService()
chunking_service = ChunkingService()
enrichment_service = EnrichmentService()
vector_service = VectorService()
pipeline_runner = PipelineRunner(
    ingestion=ingestion_service,
    extraction=extraction_service,
    cleaning=cleaning_service,
    chunking=chunking_service,
    enrichment=enrichment_service,
    vectorization=vector_service,
)


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    extension = file.filename.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_bytes = await file.read()
    document = Document(
        filename=file.filename,
        file_type=extension,
        size_bytes=len(file_bytes),
        metadata={"content_type": file.content_type},
    )

    result = pipeline_runner.run(document)
    document = result.document

    DOCUMENT_STORE[document.id] = document
    return document.model_dump()


@router.get("/documents")
async def list_documents() -> list[dict]:
    return [doc.model_dump() for doc in DOCUMENT_STORE.values()]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str) -> dict:
    document = DOCUMENT_STORE.get(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document.model_dump()
