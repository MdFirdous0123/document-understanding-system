"""Tests for document upload and management endpoints."""
import io
from unittest.mock import patch, MagicMock


def _mock_task():
    mock = MagicMock()
    mock.id = "test-celery-task-id"
    return mock


def test_upload_pdf(client, auth_headers):
    """Valid PDF upload returns 202 with document_id."""
    with patch("app.api.v1.documents.process_document_task") as mock_task:
        mock_task.delay.return_value = _mock_task()
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("exam.pdf", io.BytesIO(b"%PDF-1.4 test content"), "application/pdf")},
            headers=auth_headers,
        )
    assert response.status_code == 202
    data = response.json()
    assert "document_id" in data
    assert data["status"] == "pending"
    assert "Processing started" in data["message"]


def test_upload_jpg_image(client, auth_headers):
    """Valid JPG upload is accepted."""
    with patch("app.api.v1.documents.process_document_task") as mock_task:
        mock_task.delay.return_value = _mock_task()
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("scan.jpg", io.BytesIO(b"fake jpg bytes"), "image/jpeg")},
            headers=auth_headers,
        )
    assert response.status_code == 202


def test_upload_png_image(client, auth_headers):
    """Valid PNG upload is accepted."""
    with patch("app.api.v1.documents.process_document_task") as mock_task:
        mock_task.delay.return_value = _mock_task()
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("page.png", io.BytesIO(b"fake png bytes"), "image/png")},
            headers=auth_headers,
        )
    assert response.status_code == 202


def test_upload_unsupported_file_type(client, auth_headers):
    """Unsupported file extensions are rejected with HTTP 400."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc.docx", io.BytesIO(b"Word content"), "application/msword")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_empty_file(client, auth_headers):
    """Empty file uploads are rejected with HTTP 400."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_without_auth(client):
    """Upload without JWT returns HTTP 401."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert response.status_code == 401


def test_upload_invalid_document_role(client, auth_headers):
    """Invalid document_role value is rejected."""
    with patch("app.api.v1.documents.process_document_task") as mock_task:
        mock_task.delay.return_value = _mock_task()
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 content"), "application/pdf")},
            data={"document_role": "invalid_role"},
            headers=auth_headers,
        )
    assert response.status_code == 400


def test_list_documents_empty(client, auth_headers):
    """Listing documents returns an empty list for a new user."""
    response = client.get("/api/v1/documents/", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_documents_returns_uploaded(client, auth_headers):
    """Uploaded documents appear in the listing."""
    with patch("app.api.v1.documents.process_document_task") as mock_task:
        mock_task.delay.return_value = _mock_task()
        client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
            headers=auth_headers,
        )
    response = client.get("/api/v1/documents/", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_get_specific_document(client, auth_headers):
    """Can retrieve a specific document by ID."""
    with patch("app.api.v1.documents.process_document_task") as mock_task:
        mock_task.delay.return_value = _mock_task()
        upload_resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("check.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            headers=auth_headers,
        )
    doc_id = upload_resp.json()["document_id"]
    response = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == doc_id
    assert data["original_filename"] == "check.pdf"


def test_get_nonexistent_document(client, auth_headers):
    """Requesting a non-existent document returns HTTP 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/v1/documents/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


def test_delete_document(client, auth_headers):
    """Deleting a document removes it from the database."""
    with patch("app.api.v1.documents.process_document_task") as mock_task:
        mock_task.delay.return_value = _mock_task()
        upload_resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("del.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            headers=auth_headers,
        )
    doc_id = upload_resp.json()["document_id"]
    delete_resp = client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    # Verify it's gone
    get_resp = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert get_resp.status_code == 404
