"""Celery application and task queue configuration."""
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "dociq",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.processing_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_routes={
        "app.tasks.processing_tasks.process_document_task": {
            "queue": "document_processing"
        },
        "app.tasks.processing_tasks.link_answers_task": {
            "queue": "document_processing"
        },
    },
)
