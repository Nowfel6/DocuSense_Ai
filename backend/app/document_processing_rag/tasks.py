"""Host-facing logical task entry; concrete Celery wiring remains a composition concern."""
from collections.abc import Awaitable, Callable
from uuid import UUID

from .orchestrator import ProcessingOrchestrator

TASK_NAME = "documents.process"


def create_task(orchestrator: ProcessingOrchestrator) -> Callable[[UUID, UUID], Awaitable[bool]]:
    """Return the only authorized two-ID task callable; no implicit fake dependencies."""
    if orchestrator is None:
        raise ValueError("A configured processing orchestrator is required")

    async def process(document_id: UUID, job_id: UUID) -> bool:
        return await orchestrator.process(document_id, job_id)

    return process
