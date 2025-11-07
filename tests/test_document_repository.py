from src.app.domain.models import Document
from src.app.persistence.adapters.document_filesystem import FileSystemDocumentRepository


def test_document_repository_persists_and_lists(tmp_path):
    repository = FileSystemDocumentRepository(tmp_path)
    doc_a = Document(filename="a.pdf", file_type="pdf")
    doc_b = Document(filename="b.docx", file_type="docx")

    repository.save(doc_a)
    repository.save(doc_b)

    stored = repository.list()
    stored_ids = {doc.id for doc in stored}
    assert doc_a.id in stored_ids
    assert doc_b.id in stored_ids

    fetched = repository.get(doc_a.id)
    assert fetched is not None
    assert fetched.filename == "a.pdf"
