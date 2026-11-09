"""DocuSense ASGI application entry point."""

from .backend_runtime.entrypoints import create_api

app = create_api()

__all__ = ["app"]
