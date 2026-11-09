"""Process entry-point factories for ASGI, Celery, and reconciliation."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from celery import Celery, signals
from fastapi import FastAPI

from .host import HostSettings, compose_runtime, create_application
from .settings import RuntimeSettings

_worker_runners = []


def _paths() -> tuple[Path, Path]:
    project = Path(__file__).resolve().parents[3]
    env_file = Path(os.environ.get("DOCUSENSE_ENV_FILE", project / ".env")).resolve()
    models = Path(os.environ.get("DOCUSENSE_DATABASE_MODELS", project / "database")).resolve()
    if not env_file.is_file() or not models.is_dir():
        raise RuntimeError("Configured runtime artifact paths do not exist")
    return env_file, models


def _graph():
    env_file, models = _paths()
    return compose_runtime(
        RuntimeSettings.from_env_file(env_file),
        HostSettings.from_env_file(env_file),
        models_directory=models,
    )


def create_api() -> FastAPI:
    """Uvicorn factory: ``uvicorn backend_runtime.entrypoints:create_api --factory``."""
    return create_application(_graph())


def create_worker() -> Celery:
    """Celery factory with process-local async resources and ID-only tasks."""
    graph = _graph()
    runner = graph.worker_runner()
    _worker_runners.append(runner)

    @signals.worker_process_shutdown.connect(weak=False)
    def close_worker(**_kwargs) -> None:
        runner.shutdown()

    return runner.app


async def reconcile() -> None:
    """Run the durable dispatcher/recovery/expiry companion until interrupted."""
    print("reconcile: building graph", flush=True)
    graph = _graph()
    print("reconcile: starting graph", flush=True)
    await graph.start()
    print("reconcile: running reconciler loop", flush=True)
    stop = asyncio.Event()
    try:
        await graph.reconciler.run(stop)
    finally:
        stop.set()
        await graph.close()
    print("reconcile: stopped", flush=True)


def run_reconciler() -> None:
    # psycopg async cannot use the Windows-default ProactorEventLoop. Install
    # the selector policy before the loop is created so the dispatcher's
    # asyncpg sessions can actually open connections.
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except AttributeError:
            pass
    print("run_reconciler: starting", flush=True)
    try:
        asyncio.run(reconcile())
    except KeyboardInterrupt:
        print("run_reconciler: stopped", flush=True)
    except Exception as exc:
        import traceback
        print(f"run_reconciler FAILED: {exc!r}", flush=True)
        traceback.print_exc()
        sys.stdout.flush()
        raise


__all__ = ["create_api", "create_worker", "reconcile", "run_reconciler"]

