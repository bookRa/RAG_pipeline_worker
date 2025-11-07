from fastapi import APIRouter, Depends, File, UploadFile

from ..application.use_cases import GetDocumentUseCase, ListDocumentsUseCase, UploadDocumentUseCase
from ..container import get_app_container

router = APIRouter()


def get_upload_use_case() -> UploadDocumentUseCase:
    return get_app_container().upload_document_use_case


def get_list_use_case() -> ListDocumentsUseCase:
    return get_app_container().list_documents_use_case


def get_get_use_case() -> GetDocumentUseCase:
    return get_app_container().get_document_use_case


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    use_case: UploadDocumentUseCase = Depends(get_upload_use_case),
) -> dict:
    file_bytes = await file.read()
    document = use_case.execute(
        filename=file.filename or "",
        file_type=file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "",
        file_bytes=file_bytes,
        content_type=file.content_type,
    )
    return document.model_dump()


@router.get("/documents")
async def list_documents(
    use_case: ListDocumentsUseCase = Depends(get_list_use_case),
) -> list[dict]:
    documents = use_case.execute()
    return [doc.model_dump() for doc in documents]


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    use_case: GetDocumentUseCase = Depends(get_get_use_case),
) -> dict:
    document = use_case.execute(doc_id)
    return document.model_dump()
