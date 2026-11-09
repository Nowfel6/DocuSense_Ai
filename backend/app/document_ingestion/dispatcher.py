"""Bounded delivery loop over a REQUIRED due-job repository port.

No ORM, global database connection, background startup, or broker is installed
here. Persistent claims/recovery remain blocked pending the verified DB handoff.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .repository import Publisher
from .settings import TimingSettings


@dataclass(frozen=True)
class DispatchCandidate:
    document_id: UUID
    job_id: UUID
    next_attempt_at: datetime | None
    created_at: datetime


class DispatchRepository(Protocol):
    async def due_page(self, after: DispatchCandidate | None, limit: int) -> tuple[DispatchCandidate, ...]:
        """Scan queued/due/attempt<4 jobs joined to documents, without job locks.

        Order by next_attempt_at ASC NULLS FIRST, created_at ASC, id ASC; continue
        strictly after the same tuple. Resolve due time in PostgreSQL. No writes,
        dispatch flags or invented company_id on jobs. Database adapter is gated.
        """
        ...


@dataclass(frozen=True)
class DispatchResult:
    published: int
    failed: int
    timed_out: bool


class Dispatcher:
    def __init__(self, repository: DispatchRepository, publisher: Publisher,
                 timing: TimingSettings, concurrency: int = 8) -> None:
        if not 1 <= concurrency <= timing.dispatch_batch_size:
            raise ValueError("Concurrency must fit the bounded batch")
        self.repository, self.publisher, self.timing = repository, publisher, timing
        self.concurrency = concurrency
        self.cursor: DispatchCandidate | None = None

    async def tick(self) -> DispatchResult:
        """Publish a bounded page; advance traversal even when the broker fails.

        Jobs remain durably queued. Cursor reset on restart/end means a failed or
        cancelled delivery is revisited, without marking a job dispatched.
        """
        published = failed = 0

        async def deliver(candidate: DispatchCandidate) -> None:
            nonlocal published, failed
            try:
                await asyncio.wait_for(self.publisher.publish(candidate.document_id, candidate.job_id),
                                       self.timing.broker_publish_timeout_seconds)
                published += 1
            except Exception:
                failed += 1

        async def page() -> None:
            candidates = await self.repository.due_page(self.cursor, self.timing.dispatch_batch_size)
            if len(candidates) > self.timing.dispatch_batch_size:
                raise ValueError("Repository returned more than the bounded page")
            if not candidates:
                self.cursor = None
                return
            for index in range(0, len(candidates), self.concurrency):
                chunk = candidates[index:index + self.concurrency]
                # Every item in this chunk is attempted; durable DB eligibility is unchanged.
                # Advancing before the attempt prevents a permanently slow first job starving others.
                self.cursor = chunk[-1]
                tasks = [asyncio.create_task(deliver(candidate)) for candidate in chunk]
                try:
                    await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)

        try:
            await asyncio.wait_for(page(), self.timing.dispatch_tick_budget_seconds)
        except asyncio.TimeoutError:
            return DispatchResult(published, failed, True)
        return DispatchResult(published, failed, False)
