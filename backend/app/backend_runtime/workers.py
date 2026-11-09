"""Concrete Celery task registration and bounded recovery scheduling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Protocol

from celery import Celery

from ..document_ingestion.dispatcher import Dispatcher, DispatchResult
from ..document_search_export.worker import ExportDispatcher, ExportExpiryService

from .export_repositories import SearchExportSqlRepository
from .queue import register_tasks

logger = logging.getLogger("docusense.runtime.workers")


class Lifecycle(Protocol):
    async def start(self) -> None: ...
    async def close(self) -> None: ...


@dataclass(frozen=True)
class ReconcileResult:
    document_dispatch: DispatchResult
    recovered_exports: int
    export_dispatches: int
    expired_exports: int


class RuntimeReconciler:
    """Run one ordered, bounded recovery pass without exposing a public route."""

    def __init__(
        self,
        document_dispatcher: Dispatcher,
        export_repository: SearchExportSqlRepository,
        export_dispatcher: ExportDispatcher,
        export_expiry: ExportExpiryService,
        *,
        batch_size: int = 100,
        interval_seconds: float = 2.0,
    ) -> None:
        if any(value is None for value in (
            document_dispatcher, export_repository, export_dispatcher, export_expiry,
        )):
            raise ValueError("All reconciliation dependencies are mandatory")
        if not 1 <= batch_size <= 1000 or interval_seconds <= 0:
            raise ValueError("Invalid reconciliation bounds")
        self._documents = document_dispatcher
        self._exports = export_repository
        self._export_dispatcher = export_dispatcher
        self._expiry = export_expiry
        self._batch_size = batch_size
        self._interval = interval_seconds

    async def tick(self) -> ReconcileResult:
        documents = await self._documents.tick()
        recovered = await self._exports.recover_expired_leases(limit=self._batch_size)
        dispatched = await self._export_dispatcher.dispatch_due(self._batch_size)
        expired = await self._expiry.expire_due(self._batch_size)
        return ReconcileResult(documents, len(recovered), dispatched, expired)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                result = await self.tick()
                logger.info(
                    "reconcile_tick documents=%s document_failures=%s "
                    "recovered_exports=%s export_dispatches=%s expired_exports=%s",
                    result.document_dispatch.published,
                    result.document_dispatch.failed,
                    result.recovered_exports,
                    result.export_dispatches,
                    result.expired_exports,
                )
                print(
                    f"reconcile_tick documents={result.document_dispatch.published}"
                    f" failures={result.document_dispatch.failed}"
                    f" recovered={result.recovered_exports}"
                    f" export_dispatches={result.export_dispatches}"
                    f" expired={result.expired_exports}",
                    flush=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("reconcile_tick_failed")
                print("reconcile_tick_failed (see logs)", flush=True)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass


class WorkerRunner:
    """Run all deliveries on one process-local event loop and resource graph."""

    def __init__(
        self,
        app: Celery,
        lifecycle: Lifecycle,
        process_document,
        generate_export,
    ) -> None:
        if any(value is None for value in (
            app, lifecycle, process_document, generate_export,
        )):
            raise ValueError("Worker dependencies are mandatory")
        self.app = app
        self._lifecycle = lifecycle
        self._started = False
        self._runner = asyncio.Runner()

        async def document(document_id, job_id):
            await self.start()
            print(f"document_task start document_id={document_id} job_id={job_id}", flush=True)
            try:
                result = await process_document(document_id, job_id)
                print(f"document_task done document_id={document_id} result={result}", flush=True)
                return result
            except Exception:
                import traceback as _tb
                print("document_task FAILED:", flush=True)
                _tb.print_exc()
                raise

        async def export(export_id):
            await self.start()
            print(f"export_task start export_id={export_id}", flush=True)
            try:
                result = await generate_export(export_id)
                print(f"export_task done export_id={export_id} result={result}", flush=True)
                return result
            except Exception:
                import traceback as _tb
                print("export_task FAILED:", flush=True)
                _tb.print_exc()
                raise

        register_tasks(app, document, export, run_async=self._run)

    def _run(self, work) -> bool:
        return self._runner.run(work)

    async def start(self) -> None:
        if self._started:
            return
        await self._lifecycle.start()
        self._started = True

    async def close(self) -> None:
        if not self._started:
            return
        await self._lifecycle.close()
        self._started = False

    def shutdown(self) -> None:
        if self._started:
            self._runner.run(self.close())
        self._runner.close()


__all__ = ["ReconcileResult", "RuntimeReconciler", "WorkerRunner"]


