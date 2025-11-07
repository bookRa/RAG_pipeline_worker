from fastapi.testclient import TestClient

from src.app.main import app


def test_upload_and_retrieve_document():
    client = TestClient(app)
    files = {"file": ("demo.pdf", b"dummy content", "application/pdf")}

    response = client.post("/upload", files=files)
    assert response.status_code == 200, response.text
    document = response.json()

    assert document["pages"]
    assert document["pages"][0]["chunks"]

    doc_id = document["id"]

    list_response = client.get("/documents")
    assert list_response.status_code == 200
    documents = list_response.json()
    assert any(item["id"] == doc_id for item in documents)

    get_response = client.get(f"/documents/{doc_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == doc_id
