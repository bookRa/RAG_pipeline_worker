from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..container import get_app_container
from ..domain.models import Document
from ..services.pipeline_runner import PipelineRunner

router = APIRouter()

ALLOWED_EXTENSIONS = {"pdf", "docx", "ppt", "pptx"}
DOCUMENT_STORE: dict[str, Document] = {}


def get_pipeline_runner() -> PipelineRunner:
    return get_app_container().pipeline_runner


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    runner: PipelineRunner = Depends(get_pipeline_runner),
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

    result = runner.run(document)
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
