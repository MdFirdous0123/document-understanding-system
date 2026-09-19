"""DocIQ — Document Intelligence & Question Extraction Service."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.api.v1 import auth, documents, questions, groups

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
## DocIQ — Document Intelligence & Question Extraction Service

A scalable backend service for processing examination PDFs and images,
extracting structured questions using Google Gemini Vision AI, and
exposing them via a clean REST API.

### Key Features
- 📄 Upload PDF and image documents (JPG, PNG)
- ⚡ Asynchronous processing via Celery + Redis
- 🤖 AI-powered question extraction (Google Gemini 1.5 Flash)
- 🔑 Answer key detection and cross-document association
- 📊 Confidence scoring and review flagging
- 🔗 Document grouping (Question Paper + Answer Key)
- 🔐 JWT authentication — user-scoped data access

### Quick Start
1. `POST /api/v1/auth/register` — create account
2. `POST /api/v1/auth/login` — get JWT token
3. `POST /api/v1/documents/upload` — upload a document
4. `GET  /api/v1/documents/{id}` — poll until `status == completed`
5. `GET  /api/v1/documents/{id}/questions` — retrieve extracted questions
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Pragati Bharati Engineering Assignment",
        "url": "https://github.com/MdFirdous0123/document-understanding-system",
    },
)

# CORS — allow all origins in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(documents.router, prefix=settings.API_V1_STR)
app.include_router(questions.router, prefix=settings.API_V1_STR)
app.include_router(groups.router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Health"], summary="Service info")
def root():
    """Root endpoint — returns service info and links."""
    return {
        "service": "DocIQ — Document Intelligence Service",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["Health"], summary="Health check")
def health_check():
    """Simple health check for load balancers and container orchestrators."""
    return {"status": "healthy", "service": "dociq-api", "version": "1.0.0"}
