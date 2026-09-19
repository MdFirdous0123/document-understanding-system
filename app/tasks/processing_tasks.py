"""
Celery tasks for asynchronous document processing.

Pipeline:
1. process_document_task   — converts PDF/image → page PNGs → Gemini extraction → DB
2. link_answers_task       — matches answers from answer key doc to question paper
"""
import logging
import os
from pathlib import Path
from typing import List
from datetime import datetime, timezone

from celery import Task
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.config import settings
from app.models.document import Document, DocumentStatus, DocumentRole
from app.models.question import (
    Question, ExtractionWarning,
    QuestionType, ReviewStatus, AnswerSource, WarningSeverity,
)
from app.services.extraction_service import extract_questions_from_images, associate_answers

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db() -> Session:
    return SessionLocal()


def _pdf_to_images(file_path: str, output_dir: str) -> List[str]:
    """
    Render each page of a PDF to a PNG at 2× resolution using PyMuPDF.
    Returns list of absolute image paths, ordered by page number.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(file_path)
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i, page in enumerate(doc):
        mat = fitz.Matrix(2.0, 2.0)   # 2× zoom → ~144 dpi
        pix = page.get_pixmap(matrix=mat)
        img_path = os.path.join(output_dir, f"page_{i + 1}.png")
        pix.save(img_path)
        paths.append(img_path)
    doc.close()
    return paths


def _image_to_page(file_path: str, output_dir: str) -> List[str]:
    """
    Normalise an uploaded image to PNG and return it in a list.
    """
    from PIL import Image

    os.makedirs(output_dir, exist_ok=True)
    img = Image.open(file_path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    out_path = os.path.join(output_dir, "page_1.png")
    img.save(out_path, "PNG")
    return [out_path]


def _map_question_type(raw: str) -> QuestionType:
    try:
        return QuestionType(raw)
    except ValueError:
        return QuestionType.UNKNOWN


def _map_answer_source(raw: str) -> AnswerSource:
    try:
        return AnswerSource(raw)
    except ValueError:
        return AnswerSource.UNKNOWN


def _map_severity(raw: str) -> WarningSeverity:
    try:
        return WarningSeverity(raw)
    except ValueError:
        return WarningSeverity.WARNING


def _review_status_from_confidence(confidence: float) -> ReviewStatus:
    if confidence >= 0.75:
        return ReviewStatus.OK
    if confidence >= 0.5:
        return ReviewStatus.NEEDS_REVIEW
    return ReviewStatus.FAILED


# ── Main processing task ──────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="process_document_task",
)
def process_document_task(self: Task, document_id: str):
    """
    Process an uploaded document asynchronously.

    Steps:
    1. Mark status → processing
    2. Convert PDF/image to page PNGs
    3. Call Gemini Vision in page batches of 2
    4. Persist extracted questions and warnings
    5. Mark status → completed (or failed on exception)
    6. If document belongs to a group, trigger link_answers_task
    """
    db = _db()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error(f"Document {document_id} not found in DB")
            return

        # Mark processing
        document.status = DocumentStatus.PROCESSING
        document.celery_task_id = self.request.id
        db.commit()

        logger.info(f"[{document_id}] Processing '{document.original_filename}'")

        # ── Convert to page images ──────────────────────────────────────────
        pages_dir = os.path.join(
            str(Path(settings.UPLOAD_DIR).resolve()),
            "pages",
            document_id,
        )
        if document.file_type == "pdf":
            image_paths = _pdf_to_images(document.file_path, pages_dir)
        else:
            image_paths = _image_to_page(document.file_path, pages_dir)

        document.page_count = len(image_paths)
        db.commit()

        logger.info(f"[{document_id}] {len(image_paths)} page(s) to process")

        # ── Extract questions in batches ────────────────────────────────────
        all_questions: List[dict] = []
        all_answer_keys: List[dict] = []
        is_answer_key_doc = False
        batch_size = 2

        for batch_start in range(0, len(image_paths), batch_size):
            batch_imgs = image_paths[batch_start: batch_start + batch_size]
            batch_pages = list(range(batch_start + 1, batch_start + len(batch_imgs) + 1))

            logger.info(f"[{document_id}] Extracting pages {batch_pages}")
            result = extract_questions_from_images(batch_imgs, batch_pages)

            all_questions.extend(result.get("questions", []))
            all_answer_keys.extend(result.get("answer_keys", []))

            if result.get("is_answer_key_page"):
                is_answer_key_doc = True

            # Persist page-level warnings
            for warn in result.get("page_warnings", []):
                db.add(ExtractionWarning(
                    document_id=document_id,
                    page_number=batch_pages[0] if batch_pages else None,
                    warning_type=warn.get("warning_type", "unknown"),
                    message=warn.get("message", ""),
                    severity=_map_severity(warn.get("severity", "warning")),
                ))

        # ── Associate same-document answers ────────────────────────────────
        if all_answer_keys:
            all_questions = associate_answers(all_questions, all_answer_keys)

        # ── Determine document role ─────────────────────────────────────────
        if is_answer_key_doc and not all_questions:
            document.document_role = DocumentRole.ANSWER_KEY
        elif is_answer_key_doc:
            document.document_role = DocumentRole.MIXED
        elif all_questions:
            document.document_role = DocumentRole.QUESTION_PAPER
        # else keep as UNKNOWN

        # ── Persist questions ───────────────────────────────────────────────
        for q_data in all_questions:
            confidence = float(q_data.get("confidence", 0.5))
            review_st = _review_status_from_confidence(confidence)

            question = Question(
                document_id=document_id,
                question_number=q_data.get("question_number"),
                question_text=q_data.get("question_text", ""),
                options=q_data.get("options", []),
                question_type=_map_question_type(q_data.get("question_type", "unknown")),
                has_image=bool(q_data.get("has_image", False)),
                has_table=bool(q_data.get("has_table", False)),
                answer=q_data.get("answer"),
                answer_source=_map_answer_source(q_data.get("answer_source", "unknown")),
                answer_confidence=float(q_data.get("answer_confidence", 0.0)),
                confidence=confidence,
                review_status=review_st,
                source_pages=q_data.get("source_pages", []),
                extraction_warnings=q_data.get("warnings", []),
            )
            db.add(question)

            # Extra warning row for low confidence questions
            if confidence < 0.75:
                db.add(ExtractionWarning(
                    document_id=document_id,
                    warning_type="low_confidence",
                    message=(
                        f"Question '{q_data.get('question_number', 'N/A')}' "
                        f"extracted with confidence {confidence:.2f}"
                    ),
                    severity=(
                        WarningSeverity.WARNING
                        if confidence >= 0.5
                        else WarningSeverity.ERROR
                    ),
                ))

        document.status = DocumentStatus.COMPLETED
        document.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            f"[{document_id}] Done — {len(all_questions)} questions, "
            f"role={document.document_role}"
        )

        # Trigger cross-document answer linking if in a group
        if document.group_id:
            link_answers_task.delay(str(document.group_id))

    except Exception as exc:
        logger.error(f"[{document_id}] Processing failed: {exc}", exc_info=True)
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.status = DocumentStatus.FAILED
                doc.error_message = str(exc)[:2000]
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc)
    finally:
        db.close()


# ── Answer linking task ───────────────────────────────────────────────────────

@celery_app.task(bind=True, name="link_answers_task")
def link_answers_task(self: Task, group_id: str):
    """
    Match answers from answer-key documents to questions in question-paper documents
    within the same document group.
    """
    db = _db()
    try:
        group_docs = (
            db.query(Document)
            .filter(
                Document.group_id == group_id,
                Document.status == DocumentStatus.COMPLETED,
            )
            .all()
        )

        question_docs = [
            d for d in group_docs
            if d.document_role in (DocumentRole.QUESTION_PAPER, DocumentRole.MIXED)
        ]
        answer_docs = [
            d for d in group_docs
            if d.document_role in (DocumentRole.ANSWER_KEY, DocumentRole.MIXED)
        ]

        if not question_docs or not answer_docs:
            logger.info(
                f"[group:{group_id}] Waiting — need both question paper and answer key"
            )
            return

        # Build answer map from all answer-key documents
        answer_map: dict = {}
        for ad in answer_docs:
            rows = (
                db.query(Question)
                .filter(
                    Question.document_id == ad.id,
                    Question.answer.isnot(None),
                )
                .all()
            )
            for row in rows:
                key = str(row.question_number or "").strip().lower()
                if key:
                    answer_map[key] = {
                        "answer": row.answer,
                        "confidence": row.answer_confidence,
                    }

        if not answer_map:
            logger.info(f"[group:{group_id}] No answers found in answer-key docs")
            return

        # Update questions in question-paper documents
        updated = 0
        for qd in question_docs:
            questions = db.query(Question).filter(Question.document_id == qd.id).all()
            for q in questions:
                key = str(q.question_number or "").strip().lower()
                if key and key in answer_map:
                    q.answer = answer_map[key]["answer"]
                    q.answer_confidence = answer_map[key]["confidence"]
                    q.answer_source = AnswerSource.LINKED_DOCUMENT
                    updated += 1

        db.commit()
        logger.info(f"[group:{group_id}] Linked {updated} answer(s)")

    except Exception as exc:
        logger.error(f"[group:{group_id}] link_answers_task failed: {exc}", exc_info=True)
    finally:
        db.close()
