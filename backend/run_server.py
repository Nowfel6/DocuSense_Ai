"""Start the local FastAPI server with a Psycopg-compatible Windows loop."""

from __future__ import annotations

import asyncio
import sys

import uvicorn

# Construct the application before the event loop is entered.  Runtime imports
# include Psycopg's async integration, which must observe the selector policy.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.main import app


async def serve() -> None:
    """Run Uvicorn without letting it select a Proactor loop on Windows."""
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, access_log=True)
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    if sys.platform == "win32":
        # Psycopg async connections require selector-based readiness polling.
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(serve())
        return
    asyncio.run(serve())


if __name__ == "__main__":
    main()
