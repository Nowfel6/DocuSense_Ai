"""Concrete runtime adapters for the verified DocuSense backend contracts."""

from .auth import AuthFailure, AuthIdentity, AuthenticatedUser, AuthService, SharedAuthResolver
from .auth_adapters import (
    DashboardAuthAdapter,
    IngestionAuthAdapter,
    RagAuthAdapter,
    ReviewAuthAdapter,
    SearchExportAuthAdapter,
)
from .database import DatabaseRuntime, EXPECTED_TABLES, load_verified_models
from ..dashboard_activity.repository import SqlDashboardRepository
from ..dashboard_activity.service import (
    ActivityService, AnalyticsService, ProcessingValidationCatalogProvider,
)
from .host import (
    HostSettings, RuntimeGraph, compose_runtime, create_application,
    create_application_from_env,
)
from .export_repositories import SearchExportSqlRepository
from .providers import (
    DoclingParserAdapter, GroqExtractionAdapter, MiniLMEmbeddingAdapter,
    MiniLMTokenizerAdapter,
)
from .queue import DOCUMENT_TASK, EXPORT_TASK, CeleryPublisher, create_celery, register_tasks
from .rag_repositories import RagSqlRepository
from .rate_limit import RedisRateLimiter
from .repositories import IngestionSqlRepository
from .review_repositories import ReviewSqlRepository
from .review_source import ReviewSourceAccess
from .settings import RuntimeSettings
from .storage import ManagedS3Client, S3ExportStorage, S3SourceObjectReader, open_export_storage
from .workers import ReconcileResult, RuntimeReconciler, WorkerRunner

__all__ = [
    "AuthFailure",
    "AuthIdentity",
    "AuthService",
    "AuthenticatedUser",
    "CeleryPublisher",
    "DOCUMENT_TASK",
    "DatabaseRuntime",
    "DashboardAuthAdapter",
    "DoclingParserAdapter",
    "EXPECTED_TABLES",
    "EXPORT_TASK",
    "GroqExtractionAdapter",
    "HostSettings",
    "IngestionAuthAdapter",
    "IngestionSqlRepository",
    "MiniLMEmbeddingAdapter",
    "MiniLMTokenizerAdapter",
    "RagAuthAdapter",
    "RagSqlRepository",
    "RedisRateLimiter",
    "ReviewAuthAdapter",
    "ReviewSourceAccess",
    "ReviewSqlRepository",
    "RuntimeSettings",
    "RuntimeGraph",
    "RuntimeReconciler",
    "ReconcileResult",
    "ManagedS3Client",
    "S3ExportStorage",
    "S3SourceObjectReader",
    "SearchExportAuthAdapter",
    "SearchExportSqlRepository",
    "SqlDashboardRepository",
    "ActivityService",
    "AnalyticsService",
    "ProcessingValidationCatalogProvider",
    "SharedAuthResolver",
    "create_celery",
    "compose_runtime",
    "create_application",
    "create_application_from_env",
    "load_verified_models",
    "open_export_storage",
    "register_tasks",
    "WorkerRunner",
]

