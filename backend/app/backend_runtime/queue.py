"""Concrete Celery/Redis task publishing and registration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from celery import Celery


DOCUMENT_TASK = "documents.process"
EXPORT_TASK = "exports.generate"


def create_celery(redis_url: str) -> Celery:
    if not redis_url.startswith(("redis://", "rediss://")):
        raise ValueError("A Redis broker URL is required")
    app = Celery("docusense", broker=redis_url, backend=redis_url)
    app.conf.update(
        accept_content=["json"], task_serializer="json", result_serializer="json",
        task_acks_late=True, task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1, broker_connection_retry_on_startup=True,
        task_default_queue="docusense",
    )
    return app


class CeleryPublisher:
    """Publish identifiers only; business payloads never enter Redis."""

    def __init__(self, app: Celery) -> None:
        self._app = app

    async def publish_document(self, document_id: UUID, job_id: UUID) -> None:
        await asyncio.to_thread(
            self._app.send_task, DOCUMENT_TASK,
            args=[str(document_id), str(job_id)], queue="documents",
        )

    async def publish(self, *args: object) -> None:
        """Satisfy ingestion and export publisher ports without accepting data payloads."""
        if len(args) == 2 and isinstance(args[0], UUID) and isinstance(args[1], UUID):
            await self.publish_document(args[0], args[1])
            return
        if len(args) == 2 and args[0] == EXPORT_TASK and isinstance(args[1], UUID):
            await asyncio.to_thread(
                self._app.send_task, EXPORT_TASK,
                args=[str(args[1])], queue="exports",
            )
            return
        raise ValueError("Only approved ID-only tasks may be published")


def register_tasks(
    app: Celery,
    process_document: Callable[[UUID, UUID], Awaitable[bool]],
    generate_export: Callable[[UUID], Awaitable[bool]],
    *,
    run_async: Callable[[Awaitable[bool]], bool] = asyncio.run,
) -> None:
    """Register sync Celery entries that run the reviewed async workers."""
    if DOCUMENT_TASK in app.tasks or EXPORT_TASK in app.tasks:
        raise RuntimeError("DocuSense tasks are already registered")

    @app.task(name=DOCUMENT_TASK, bind=True, acks_late=True)
    def document_entry(_task: object, document_id: str, job_id: str) -> bool:
        return run_async(process_document(UUID(document_id), UUID(job_id)))

    @app.task(name=EXPORT_TASK, bind=True, acks_late=True)
    def export_entry(_task: object, export_id: str) -> bool:
        return run_async(generate_export(UUID(export_id)))


__all__ = [
    "CeleryPublisher", "DOCUMENT_TASK", "EXPORT_TASK", "create_celery", "register_tasks",
]


