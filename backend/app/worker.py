"""DocuSense Celery worker entry point."""

from .backend_runtime.entrypoints import create_worker

celery_app = create_worker()

__all__ = ["celery_app"]
