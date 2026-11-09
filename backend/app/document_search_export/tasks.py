"""Host-facing Feature 05 task boundary; Celery registration stays in composition."""
from collections.abc import Awaitable, Callable
from uuid import UUID

from .worker import ExportWorkerService

TASK_NAME = "exports.generate"


def create_task(worker: ExportWorkerService) -> Callable[[UUID], Awaitable[bool]]:
    """Return the only authorized export task callable: one export ID."""
    if worker is None:
        raise ValueError("A configured export worker is required")

    async def generate(export_id: UUID) -> bool:
        return await worker.run(export_id)

    return generate


__all__ = ["TASK_NAME", "create_task"]


