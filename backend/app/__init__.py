"""DocuSense FastAPI application package."""
import sys

# CRITICAL: Set event loop policy BEFORE any asyncio usage
# Required for Psycopg on Windows (doesn't work with ProactorEventLoop)
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
