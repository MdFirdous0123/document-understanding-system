"""
AI-based question extraction using Google Gemini Vision.

Strategy:
- Send page images to Gemini 1.5 Flash
- Request structured JSON output describing questions, options, types, and confidence
- Fallback to an error state if the API is unavailable
"""
import json
import logging
import re
from typing import List, Dict, Any, Optional

from PIL import Image
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Gemini setup (lazy import to avoid hard dependency) ──────────────────────
_gemini_model = None


def _get_model():
    global _gemini_model
    if _gemini_model is None:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            _gemini_model = genai.GenerativeModel("gemini-1.5-flash")
        except Exception as e:
            logger.error(f"Failed to initialise Gemini: {e}")
    return _gemini_model


# ── Extraction prompt ─────────────────────────────────────────────────────────
EXTRACTION_PROMPT = """
You are an expert examination document analyser.
Carefully read the provided page image(s) and extract every question you can find.

Return ONLY valid JSON — no markdown, no extra text — matching this exact schema:

{
  "questions": [
    {
      "question_number": "1",
      "question_text": "Full question text here",
      "question_type": "mcq",
      "options": [
        {"label": "A", "text": "Option A text"},
        {"label": "B", "text": "Option B text"}
      ],
      "has_image": false,
      "has_table": false,
      "source_pages": [1],
      "confidence": 0.95,
      "warnings": []
    }
  ],
  "answer_keys": [
    {
      "question_number": "1",
      "answer": "A",
      "confidence": 0.9
    }
  ],
  "page_warnings": [
    {
      "warning_type": "low_quality",
      "message": "Page appears blurry",
      "severity": "warning"
    }
  ],
  "is_answer_key_page": false
}

Rules:
- question_type must be one of: mcq, short_answer, long_answer, true_false, fill_in_the_blank, unknown
- Extract EVERY question visible, even if partially cut off
- Confidence: 0.9-1.0 = clear; 0.6-0.89 = mostly readable; 0.4-0.59 = partial; <0.4 = very uncertain
- If this page contains an answer key section, set is_answer_key_page=true and populate answer_keys
- has_image=true if the question refers to a figure, diagram, or image
- has_table=true if the question contains a table
- question_number may be null if not visible
- options=[] for non-MCQ questions
- Include OCR warnings, rotation warnings, or quality warnings in page_warnings
- If a question is split across pages, extract what is visible and add a warning
"""


# ── Public API ────────────────────────────────────────────────────────────────

def extract_questions_from_images(
    image_paths: List[str],
    page_numbers: List[int],
) -> Dict[str, Any]:
    """
    Extract questions from page images using Gemini Vision.

    Args:
        image_paths: Absolute paths to PNG/JPG page images.
        page_numbers: Corresponding page numbers (1-indexed).

    Returns:
        dict with keys: questions, answer_keys, page_warnings, is_answer_key_page
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set — returning empty extraction with warning")
        return _api_key_missing_result()

    model = _get_model()
    if model is None:
        return _error_result("Failed to initialise Gemini model")

    try:
        pil_images: List[Image.Image] = []
        for path in image_paths:
            img = Image.open(path)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            pil_images.append(img)

        page_context = f"These images are pages {page_numbers} of an examination document."
        prompt = f"{page_context}\n\n{EXTRACTION_PROMPT}"

        response = model.generate_content([prompt] + pil_images)
        raw = response.text.strip()
        return _parse_response(raw, page_numbers)

    except Exception as exc:
        logger.error(f"Gemini API call failed for pages {page_numbers}: {exc}")
        return _error_result(f"AI extraction error: {exc}")


def associate_answers(
    questions: List[Dict],
    answer_keys: List[Dict],
) -> List[Dict]:
    """
    Match answer_keys to questions by question_number.

    Populates 'answer', 'answer_confidence', and 'answer_source' on each question.
    """
    answer_map: Dict[str, Dict] = {}
    for ak in answer_keys:
        key = _normalize_number(ak.get("question_number", ""))
        if key:
            answer_map[key] = ak

    for q in questions:
        key = _normalize_number(q.get("question_number", ""))
        if key and key in answer_map:
            matched = answer_map[key]
            q["answer"] = matched.get("answer")
            q["answer_confidence"] = float(matched.get("confidence", 0.7))
            q["answer_source"] = "same_document"
        else:
            q.setdefault("answer", None)
            q.setdefault("answer_confidence", 0.0)
            q.setdefault("answer_source", "unmatched")

    return questions


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_number(val: Any) -> str:
    """Lowercase, strip, remove common prefixes for robust matching."""
    if val is None:
        return ""
    s = str(val).strip().lower()
    s = re.sub(r"^(q\.?|question\.?|no\.?|num\.?)\s*", "", s)
    s = re.sub(r"[.\)\]\s]+$", "", s)
    return s


def _parse_response(raw: str, page_numbers: List[int]) -> Dict[str, Any]:
    """Strip markdown fences and parse JSON from Gemini response."""
    # Remove ```json ... ``` wrappers if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error(f"JSON parse error: {exc}\nRaw:\n{raw[:600]}")
        return _error_result(f"Could not parse AI response: {exc}")

    # Normalise questions
    for q in data.get("questions", []):
        if not q.get("source_pages"):
            q["source_pages"] = page_numbers
        q.setdefault("options", [])
        q.setdefault("warnings", [])
        q.setdefault("has_image", False)
        q.setdefault("has_table", False)

    return {
        "questions": data.get("questions", []),
        "answer_keys": data.get("answer_keys", []),
        "page_warnings": data.get("page_warnings", []),
        "is_answer_key_page": bool(data.get("is_answer_key_page", False)),
    }


def _api_key_missing_result() -> Dict[str, Any]:
    return {
        "questions": [],
        "answer_keys": [],
        "page_warnings": [{
            "warning_type": "no_api_key",
            "message": (
                "GEMINI_API_KEY is not configured. "
                "Set it in .env to enable AI extraction. "
                "Get a free key at https://aistudio.google.com/app/apikey"
            ),
            "severity": "error",
        }],
        "is_answer_key_page": False,
    }


def _error_result(message: str) -> Dict[str, Any]:
    return {
        "questions": [],
        "answer_keys": [],
        "page_warnings": [{
            "warning_type": "extraction_error",
            "message": message,
            "severity": "error",
        }],
        "is_answer_key_page": False,
    }
