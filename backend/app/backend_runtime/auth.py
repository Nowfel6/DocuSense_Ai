"""Stable shared-auth imports for the integrated application package."""

from ..auth.routes import create_auth_router
from ..auth.service import (
    AuthFailure, AuthenticatedUser, AuthIdentity, AuthService, CreatedApiKey,
    SharedAuthResolver,
)

__all__ = [
    "AuthFailure", "AuthenticatedUser", "AuthIdentity", "AuthService",
    "CreatedApiKey", "SharedAuthResolver", "create_auth_router",
]
