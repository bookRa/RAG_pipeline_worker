from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..container import get_app_container
from ..domain.models import Document
from ..persistence.ports import DocumentRepository
from ..services.pipeline_runner import PipelineRunner

router = APIRouter()

ALLOWED_EXTENSIONS = {"pdf", "docx", "ppt", "pptx"}


def get_pipeline_runner() -> PipelineRunner:
    return get_app_container().pipeline_runner


def get_document_repository() -> DocumentRepository:
    return get_app_container().document_repository


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    runner: PipelineRunner = Depends(get_pipeline_runner),
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> dict:
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

    result = runner.run(document, file_bytes=file_bytes)
    document = result.document
    document_repository.save(document)
    return document.model_dump()


@router.get("/documents")
async def list_documents(
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> list[dict]:
    return [doc.model_dump() for doc in document_repository.list()]


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> dict:
    document = document_repository.get(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document.model_dump()
