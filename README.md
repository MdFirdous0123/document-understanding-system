# DocIQ — Document Intelligence & Question Extraction Service

> **Pragati Bharati Engineering Assignment — Round 2**
> Full Stack Developer | Document Intelligence & Question Extraction Service

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Technology Choices](#technology-choices)
3. [Quick Start](#quick-start)
4. [API Reference](#api-reference)
5. [Processing Pipeline](#processing-pipeline)
6. [Question Extraction Strategy](#question-extraction-strategy)
7. [Confidence & Review Mechanism](#confidence--review-mechanism)
8. [Security](#security)
9. [Testing](#testing)
10. [Design Decisions & Trade-offs](#design-decisions--trade-offs)
11. [AI Usage Disclosure](#ai-usage-disclosure)

---

## Architecture Overview

```
┌─────────────┐     HTTP      ┌──────────────────┐    Enqueue     ┌────────────────┐
│   Client    │ ─────────────▶│  FastAPI API      │ ──────────────▶│  Redis Queue   │
│ (Postman /  │               │  (Port 8000)      │                │  (Port 6379)   │
│  Browser)   │               └────────┬─────────┘                └───────┬────────┘
└─────────────┘                        │                                   │
                                Read/Write                           Consume tasks
                                       │                                   │
                              ┌────────▼──────────┐          ┌────────────▼────────┐
                              │  PostgreSQL DB     │◀─────────│  Celery Worker      │
                              │  (Port 5432)       │  Write   │  (processes docs)   │
                              │  - users           │          └────────────┬────────┘
                              │  - documents       │                       │
                              │  - questions       │          ┌────────────▼────────┐
                              │  - doc_groups      │          │ Google Gemini       │
                              │  - ext_warnings    │          │ Vision AI           │
                              └────────────────────┘          │ (OCR + Extract)     │
                                                              └─────────────────────┘
```

### Component Roles

| Component | Role |
|-----------|------|
| **FastAPI** | Receives uploads, returns task IDs immediately, serves query results |
| **PostgreSQL** | Persistent storage for all metadata, extracted questions, warnings |
| **Redis** | Celery message broker — task queue |
| **Celery Worker** | Async document processor — converts PDFs, calls Gemini Vision |
| **Gemini 1.5 Flash** | Vision AI — reads page images, returns structured JSON questions |
| **Flower** | Celery task monitoring dashboard (Port 5555) |

---

## Technology Choices

| Technology | Version | Reason |
|------------|---------|--------|
| **FastAPI** | 0.111 | Required; async-native, auto-generates OpenAPI docs |
| **PostgreSQL** | 16 | Required; JSONB columns for flexible question/options storage |
| **Redis** | 7 | Required; Celery broker for async task dispatch |
| **Celery** | 5.4 | Distributed async task processing with retry/error handling |
| **SQLAlchemy** | 2.0 | ORM with Alembic migrations |
| **Alembic** | 1.13 | Database migration management |
| **Google Gemini 1.5 Flash** | API | Vision-capable AI; returns structured JSON; free tier |
| **PyMuPDF (fitz)** | 1.24 | Fast PDF→image conversion, no poppler dependency |
| **python-jose** | 3.3 | JWT token creation and validation |
| **passlib bcrypt** | 1.7 | Secure password hashing |
| **Pillow** | 10.3 | Image processing and format normalisation |

### Why Google Gemini 1.5 Flash?

- **Vision-native**: Reads raw page images — no text layer required (works on scans)
- **Structured output**: Returns JSON reliably when prompted with a schema
- **Contextual understanding**: Recognises question numbers, MCQ options, answer keys, tables
- **Handles imperfect docs**: Works on blurry, rotated, or low-resolution scans
- **Free tier**: 15 requests/min — sufficient for demo and evaluation
- **Alternative considered**: Tesseract OCR + regex parsing — rejected because it requires
  extensive pre-processing and doesn't understand document structure

---

## Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed
- Google Gemini API key (free): https://aistudio.google.com/app/apikey

### Step 1 — Clone and Configure

```bash
git clone https://github.com/MdFirdous0123/document-understanding-system.git
cd document-understanding-system
cp .env.example .env
```

Edit `.env`:
```
GEMINI_API_KEY=your-gemini-api-key-here
SECRET_KEY=any-random-32-character-string-here
```

### Step 2 — Start All Services

```bash
docker-compose up -d
```

This starts: PostgreSQL, Redis, FastAPI API, Celery Worker, Flower dashboard.

### Step 3 — Run Database Migrations

```bash
docker-compose exec api alembic upgrade head
```

### Step 4 — Verify

| Service | URL |
|---------|-----|
| API (Swagger UI) | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health Check | http://localhost:8000/health |
| Flower (task monitor) | http://localhost:5555 |

### Step 5 — Generate Sample Documents (optional)

```bash
python scripts/create_sample_pdf.py
```

---

### Local Development (without Docker)

```bash
# 1. Install dependencies
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt

# 2. Set up .env
cp .env.example .env
# edit DATABASE_URL and REDIS_URL to point to local PostgreSQL/Redis

# 3. Run migrations
alembic upgrade head

# 4. Start API
uvicorn app.main:app --reload

# 5. Start Celery worker (new terminal)
celery -A app.core.celery_app worker --loglevel=info -Q document_processing,celery
```

---

## API Reference

### Authentication
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register` | None | Register new user |
| POST | `/api/v1/auth/login` | None | Login → JWT token |
| GET | `/api/v1/auth/me` | JWT | Current user profile |

### Documents
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/documents/upload` | JWT | Upload PDF/image (async) |
| GET | `/api/v1/documents/` | JWT | List my documents |
| GET | `/api/v1/documents/{id}` | JWT | Document status & info |
| DELETE | `/api/v1/documents/{id}` | JWT | Delete document |

### Questions
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/documents/{id}/questions` | JWT | All questions (filterable) |
| GET | `/api/v1/questions/{id}` | JWT | Single question detail |
| GET | `/api/v1/documents/{id}/answers` | JWT | Answer key summary |
| GET | `/api/v1/documents/{id}/warnings` | JWT | Extraction warnings |

### Document Groups
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/groups/` | JWT | Create group |
| GET | `/api/v1/groups/` | JWT | List groups |
| GET | `/api/v1/groups/{id}` | JWT | Group details |
| GET | `/api/v1/groups/{id}/documents` | JWT | Documents in group |
| POST | `/api/v1/groups/{id}/link-answers` | JWT | Trigger answer linking |

---

## Processing Pipeline

```
User uploads PDF or image
        │
        ▼
FastAPI validates file (type, size, auth)
        │
        ▼
File saved to disk → Document record created (status: pending)
        │
        ▼
Celery task dispatched → document status: processing
        │
        ├─── PDF? → PyMuPDF renders each page at 2× zoom → PNG images
        └─── Image? → Pillow normalises to PNG
        │
        ▼
Pages batched (2 at a time) → sent to Gemini Vision AI
        │
        ▼
Gemini returns structured JSON:
  - questions[] with number, text, options, type, confidence
  - answer_keys[] with question_number → answer
  - page_warnings[] for quality/OCR issues
        │
        ▼
Answer keys found in same doc → associated with questions
        │
        ▼
Questions + warnings saved to PostgreSQL
        │
        ▼
Document status → completed (or failed on exception)
        │
        ▼ (if in a document group)
link_answers_task → cross-document answer matching
```

---

## Question Extraction Strategy

### Gemini Vision Prompting

The system sends page images to Gemini 1.5 Flash with a structured prompt requesting JSON output. The prompt specifies:
- Exact JSON schema to follow
- Question types to classify (MCQ, short answer, long answer, etc.)
- How to score confidence
- How to identify answer key sections
- How to flag images, tables, and quality issues

### Multi-page Questions

Pages are processed in **batches of 2** so Gemini can see both pages simultaneously and recognise that a question starting on page N continues on page N+1. The `source_pages` field records all pages a question spans.

### Answer Key Association

1. **Same-document**: Gemini identifies answer key sections within the same document → answers populated during extraction
2. **Cross-document (group)**: Upload Q-Paper + Answer Key to same group → `link_answers_task` matches by `question_number`
3. **Unmatched**: If no match found, `answer=null`, `answer_source=unmatched`, `answer_confidence=0.0`

---

## Confidence & Review Mechanism

| Confidence Range | `review_status` | Meaning |
|-----------------|-----------------|---------|
| 0.75 – 1.00 | `ok` | High-confidence extraction, ready to use |
| 0.50 – 0.74 | `needs_review` | Partial extraction, human review recommended |
| 0.00 – 0.49 | `failed` | Could not reliably extract — do not use without review |

### Warning Types

| Warning Type | Severity | Trigger |
|-------------|----------|---------|
| `low_quality` | warning | Blurry or low-resolution page detected |
| `low_confidence` | warning/error | Question extracted with confidence < 0.75 |
| `ocr_error` | error | AI suspects OCR errors in text |
| `no_api_key` | error | Gemini API key not configured |
| `extraction_error` | error | AI API call failed |
| `parse_error` | error | Could not parse AI JSON response |

Each question carries:
- `confidence`: float 0–1
- `review_status`: ok / needs_review / failed
- `extraction_warnings`: list of warning strings specific to this question
- `source_pages`: which pages the question came from (for manual verification)

---

## Security

| Concern | Mitigation |
|---------|-----------|
| Authentication | JWT Bearer tokens (python-jose, bcrypt passwords) |
| Authorisation | All DB queries filter by `owner_id = current_user.id` |
| File type validation | Extension + MIME type check; unsupported types rejected |
| File size limits | `MAX_FILE_SIZE_MB` env var (default 50 MB) |
| Empty files | Explicitly rejected |
| Secrets | All in `.env` (never committed); `.env` in `.gitignore` |
| Credentials | `GEMINI_API_KEY` stored in env only, never logged |
| Unauthorised access | 404 returned (not 403) to prevent enumeration |

---

## Scalability Considerations

- **Worker scaling**: `docker-compose scale worker=N` adds more Celery workers
- **Task routing**: Separate `document_processing` queue isolates heavy work
- **DB connection pool**: SQLAlchemy `pool_size=10, max_overflow=20`
- **Monitoring**: Flower dashboard tracks task success/failure rates
- **Future**: Replace local file storage with AWS S3/MinIO for horizontal scaling

---

## Testing

```bash
# Install dependencies (if not already)
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py -v
pytest tests/test_documents.py -v
pytest tests/test_questions.py -v
```

Tests use SQLite (in-memory) — no external database required for testing.

### Test Coverage
- User registration, duplicate email rejection
- Login with correct/wrong credentials
- JWT-protected endpoint access
- Document upload (PDF, PNG, JPG)
- Invalid file type rejection (HTTP 400)
- Empty file rejection (HTTP 400)
- Invalid document_role rejection
- Document listing, retrieval, deletion
- Cross-user access protection (HTTP 404)
- Question listing with filters (confidence, review_status)
- Single question retrieval
- Answer key endpoint (answered/unanswered counts)
- Warnings endpoint

---

## Design Decisions & Trade-offs

### Gemini over Tesseract
**Decision**: Google Gemini 1.5 Flash (Vision AI)
**Trade-off**: Requires API key; rate-limited on free tier
**Reason**: Gemini understands document structure contextually and returns structured JSON directly. Tesseract requires extensive preprocessing and doesn't understand question formats.

### Local file storage over S3
**Decision**: Local filesystem (`./uploads`)
**Trade-off**: Not horizontally scalable without shared volume
**Reason**: Simpler for demo setup. Architecture supports swapping to S3 by changing file write/read operations in `documents.py`.

### Page batching (2 pages per call)
**Decision**: Send 2 pages per Gemini call
**Trade-off**: More API calls for large documents
**Reason**: Allows Gemini to see question continuations across page boundaries.

### SQLite for tests
**Decision**: Use SQLite in tests instead of PostgreSQL
**Trade-off**: Some PostgreSQL-specific features (JSONB) behave differently in SQLite
**Reason**: No external DB needed to run tests; faster test execution.

---

## AI Usage Disclosure

This solution uses **Google Gemini 1.5 Flash** (Google DeepMind) for:
- Reading document page images via Vision API
- Extracting structured question data (question number, text, options, type)
- Detecting answer key sections
- Providing confidence scores for each extraction

**SDK**: `google-generativeai` Python package
**Model**: `gemini-1.5-flash` (multimodal vision + text)

All other code (FastAPI routes, Celery tasks, database models, auth, migrations, tests) is custom-written and understood by the author.

---

## Project Structure

```
document-understanding-system/
├── app/
│   ├── main.py                        # FastAPI app entry point
│   ├── core/
│   │   ├── config.py                  # Pydantic settings (env-based)
│   │   ├── database.py                # SQLAlchemy engine + session
│   │   ├── security.py                # JWT + bcrypt
│   │   ├── celery_app.py              # Celery configuration
│   │   └── redis_client.py            # Redis connection
│   ├── models/
│   │   ├── user.py                    # User ORM model
│   │   ├── document_group.py          # DocumentGroup ORM model
│   │   ├── document.py                # Document ORM model
│   │   └── question.py                # Question + ExtractionWarning ORM models
│   ├── schemas/
│   │   ├── user.py                    # Pydantic request/response schemas
│   │   ├── document.py
│   │   └── question.py
│   ├── api/
│   │   ├── deps.py                    # JWT dependency injection
│   │   └── v1/
│   │       ├── auth.py                # /auth/* endpoints
│   │       ├── documents.py           # /documents/* endpoints
│   │       ├── questions.py           # /questions/* endpoints
│   │       └── groups.py              # /groups/* endpoints
│   ├── services/
│   │   └── extraction_service.py      # Gemini Vision AI extraction
│   └── tasks/
│       └── processing_tasks.py        # Celery async tasks
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py      # Initial DB migration
├── tests/
│   ├── conftest.py                    # Fixtures (SQLite test DB)
│   ├── test_auth.py
│   ├── test_documents.py
│   └── test_questions.py
├── sample_docs/                       # Sample input documents
├── sample_output/                     # Sample extracted JSON
├── postman/
│   └── DocIQ_API_Collection.json      # Postman collection
├── scripts/
│   └── create_sample_pdf.py           # Sample document generator
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── pytest.ini
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```
