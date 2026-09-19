"""Tests for question retrieval and answer key endpoints."""
import uuid
from app.models.document import Document, DocumentStatus, DocumentRole
from app.models.question import Question, QuestionType, ReviewStatus, AnswerSource


def _make_document(db, owner_id):
    doc = Document(
        id=uuid.uuid4(),
        filename="test.pdf",
        original_filename="Physics Exam.pdf",
        file_path="/tmp/test.pdf",
        file_type="pdf",
        file_size=4096,
        status=DocumentStatus.COMPLETED,
        document_role=DocumentRole.QUESTION_PAPER,
        owner_id=owner_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _make_questions(db, doc_id, count=3):
    questions = []
    for i in range(count):
        confidence = 0.95 if i < 2 else 0.35   # last one is low confidence
        q = Question(
            id=uuid.uuid4(),
            document_id=doc_id,
            question_number=str(i + 1),
            question_text=f"Sample question {i + 1}: What is {i + 1} + {i + 1}?",
            options=[
                {"label": "A", "text": str(i * 2)},
                {"label": "B", "text": str((i + 1) * 2)},
                {"label": "C", "text": str((i + 2) * 2)},
                {"label": "D", "text": str((i + 3) * 2)},
            ],
            question_type=QuestionType.MCQ,
            has_image=False,
            has_table=False,
            answer="B" if i < 2 else None,
            answer_source=AnswerSource.SAME_DOCUMENT if i < 2 else AnswerSource.UNMATCHED,
            answer_confidence=0.92 if i < 2 else 0.0,
            confidence=confidence,
            review_status=ReviewStatus.OK if confidence >= 0.75 else ReviewStatus.FAILED,
            source_pages=[i + 1],
            extraction_warnings=[] if i < 2 else ["Low scan quality detected"],
        )
        db.add(q)
        questions.append(q)
    db.commit()
    return questions


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_get_questions_list(client, auth_headers, test_user, db):
    doc = _make_document(db, test_user.id)
    _make_questions(db, doc.id, count=3)

    response = client.get(
        f"/api/v1/documents/{doc.id}/questions",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["questions"]) == 3


def test_get_questions_returns_structure(client, auth_headers, test_user, db):
    """Verify question response has all required fields."""
    doc = _make_document(db, test_user.id)
    _make_questions(db, doc.id, count=1)

    response = client.get(
        f"/api/v1/documents/{doc.id}/questions",
        headers=auth_headers,
    )
    q = response.json()["questions"][0]
    assert "id" in q
    assert "question_text" in q
    assert "confidence" in q
    assert "review_status" in q
    assert "source_pages" in q
    assert "options" in q


def test_get_single_question(client, auth_headers, test_user, db):
    doc = _make_document(db, test_user.id)
    questions = _make_questions(db, doc.id, count=1)
    q_id = str(questions[0].id)

    response = client.get(f"/api/v1/questions/{q_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["question_number"] == "1"
    assert data["question_type"] == "mcq"
    assert len(data["options"]) == 4


def test_get_nonexistent_question(client, auth_headers):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/v1/questions/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


def test_filter_questions_by_confidence(client, auth_headers, test_user, db):
    """Only questions meeting min_confidence threshold are returned."""
    doc = _make_document(db, test_user.id)
    _make_questions(db, doc.id, count=3)  # 2 have 0.95, 1 has 0.35

    response = client.get(
        f"/api/v1/documents/{doc.id}/questions?min_confidence=0.8",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # only the high-confidence ones


def test_filter_questions_by_review_status(client, auth_headers, test_user, db):
    """Filter by review_status=failed returns only failed questions."""
    doc = _make_document(db, test_user.id)
    _make_questions(db, doc.id, count=3)

    response = client.get(
        f"/api/v1/documents/{doc.id}/questions?review_status=failed",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1


def test_get_answer_key(client, auth_headers, test_user, db):
    """Answer key summary shows correct answered/unanswered counts."""
    doc = _make_document(db, test_user.id)
    _make_questions(db, doc.id, count=3)  # 2 have answers, 1 does not

    response = client.get(
        f"/api/v1/documents/{doc.id}/answers",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_questions"] == 3
    assert data["answered"] == 2
    assert data["unanswered"] == 1


def test_get_warnings_empty(client, auth_headers, test_user, db):
    """Document with no warnings returns empty list."""
    doc = _make_document(db, test_user.id)

    response = client.get(
        f"/api/v1/documents/{doc.id}/warnings",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json() == []


def test_questions_unauthorized(client, auth_headers, db):
    """Cannot access another user's document questions."""
    other_user_doc_id = "00000000-0000-0000-0000-000000000001"
    response = client.get(
        f"/api/v1/documents/{other_user_doc_id}/questions",
        headers=auth_headers,
    )
    assert response.status_code == 404  # doc not found for this user


def test_questions_unauthenticated(client, test_user, db):
    """Accessing questions without auth returns HTTP 401."""
    doc = _make_document(db, test_user.id)
    response = client.get(f"/api/v1/documents/{doc.id}/questions")
    assert response.status_code == 401
