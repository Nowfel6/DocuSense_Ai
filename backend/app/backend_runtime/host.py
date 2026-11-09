"""Production application composition for all DocuSense backend features."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis

from ..dashboard_activity.repository import SqlDashboardRepository
from ..dashboard_activity.routes import create_router as create_dashboard_router
from ..dashboard_activity.service import (
    ActivityService, AnalyticsService, ProcessingValidationCatalogProvider,
)
from ..dashboard_activity.settings import DashboardActivitySettings
from ..document_ingestion.dispatcher import Dispatcher
from ..document_ingestion.routes import create_router as create_ingestion_router
from ..document_ingestion.service import IngestionService
from ..document_ingestion.settings import StorageSettings, TimingSettings
from ..document_ingestion.storage import S3ObjectStore
from ..document_processing_rag.chunking import ChunkingService
from ..document_processing_rag.extraction import ExtractionService
from ..document_processing_rag.orchestrator import ProcessingOrchestrator
from ..document_processing_rag.retrieval import RetrievalService
from ..document_processing_rag.routes import create_router as create_rag_router
from ..document_processing_rag.service import RagReadService
from ..document_processing_rag.settings import (
    PipelineIdentitySettings, ProcessingSettings, build_identity,
)
from ..document_processing_rag.tasks import create_task as create_document_task
from ..document_search_export.export import ExportCommandService, ExportQueryService
from ..document_search_export.routes import create_router as create_export_router
from ..document_search_export.search import SearchService
from ..document_search_export.settings import SearchExportSettings
from ..document_search_export.tasks import create_task as create_export_task
from ..document_search_export.worker import (
    ArtifactGenerator, ExportDispatcher, ExportExpiryService, ExportWorkerService,
)
from ..human_review_audit.routes import create_router as create_review_router
from ..human_review_audit.service import (
    ReviewCommandService, ReviewQueryService, ReviewValidationService,
)

from .auth import AuthService, SharedAuthResolver, create_auth_router
from .auth_adapters import (
    DashboardAuthAdapter, IngestionAuthAdapter, RagAuthAdapter, ReviewAuthAdapter,
    SearchExportAuthAdapter,
)
from .database import DatabaseRuntime, load_verified_models
from .openapi import configure_openapi
from .export_repositories import SearchExportSqlRepository
from .providers import (
    DoclingParserAdapter, GroqExtractionAdapter, MiniLMEmbeddingAdapter,
    MiniLMTokenizerAdapter,
)
from .queue import CeleryPublisher, create_celery
from .rag_repositories import RagSqlRepository
from .rate_limit import RedisRateLimiter
from .repositories import IngestionSqlRepository
from .review_repositories import ReviewSqlRepository
from .review_source import ReviewSourceAccess
from .settings import RuntimeSettings
from .storage import ManagedS3Client, S3ExportStorage, S3SourceObjectReader
from .workers import RuntimeReconciler, WorkerRunner


class HostSettings(BaseSettings):
    """Non-secret gateway and release policy."""

    model_config = SettingsConfigDict(
        env_prefix="DOCUSENSE_", extra="ignore", frozen=True,
    )

    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    supported_currencies: frozenset[str]
    rate_actor_limit: int = Field(default=60, ge=1, le=10_000)
    rate_company_limit: int = Field(default=300, ge=1, le=100_000)
    rate_window_seconds: int = Field(default=60, ge=1, le=3600)
    reconcile_batch_size: int = Field(default=100, ge=1, le=1000)
    reconcile_interval_seconds: float = Field(default=2.0, gt=0, le=300)
    stream_downloads: bool = True

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("At least one exact CORS origin is required")
        normalized: list[str] = []
        for value in values:
            parsed = urlsplit(value)
            local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if (
                parsed.scheme not in ({"https"} if not local else {"http", "https"})
                or not parsed.netloc or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            ):
                raise ValueError("CORS origins must be exact credential-free origins")
            normalized.append(value.rstrip("/"))
        if len(set(normalized)) != len(normalized):
            raise ValueError("CORS origins must be unique")
        return tuple(normalized)

    @field_validator("supported_currencies")
    @classmethod
    def validate_currencies(cls, values: frozenset[str]) -> frozenset[str]:
        if not values or any(
            len(value) != 3 or not value.isascii() or not value.isupper()
            for value in values
        ):
            raise ValueError("Supported currencies must be uppercase three-letter codes")
        return values

    @classmethod
    def from_env_file(cls, path: Path) -> "HostSettings":
        return cls(_env_file=path.resolve(), _env_file_encoding="utf-8")


@dataclass
class RuntimeGraph:
    settings: RuntimeSettings
    policy: HostSettings
    models_directory: Path
    database: DatabaseRuntime
    redis: Redis
    s3: ManagedS3Client
    auth_service: AuthService
    ingestion_service: IngestionService
    ingestion_auth: IngestionAuthAdapter
    rag_service: RagReadService
    rag_auth: RagAuthAdapter
    review_query: ReviewQueryService
    review_validation: ReviewValidationService
    review_command: ReviewCommandService
    review_auth: ReviewAuthAdapter
    search_service: SearchService
    export_command: ExportCommandService
    export_query: ExportQueryService
    export_auth: SearchExportAuthAdapter
    limiter: RedisRateLimiter
    process_document: Any
    generate_export: Any
    reconciler: RuntimeReconciler
    celery: Any
    dashboard_analytics: AnalyticsService | None = None
    dashboard_activity: ActivityService | None = None
    dashboard_auth: DashboardAuthAdapter | None = None
    _started: bool = False

    async def start(self) -> None:
        if self._started:
            return
        load_verified_models(self.models_directory)
        await self.database.verify_schema()
        await self.redis.ping()
        try:
            await self.s3.start()
            await self.s3.verify_bucket(self.settings.s3_bucket)
        except Exception:
            await self.s3.close()
            raise
        self._started = True

    async def ready(self) -> None:
        if not self._started:
            raise RuntimeError("Runtime has not started")
        await self.database.verify_schema()
        await self.redis.ping()
        await self.s3.verify_bucket(self.settings.s3_bucket)

    async def close(self) -> None:
        await self.s3.close()
        await self.redis.aclose()
        await self.database.close()
        self._started = False

    def worker_runner(self) -> WorkerRunner:
        return WorkerRunner(
            self.celery, self, self.process_document, self.generate_export,
        )


def compose_runtime(
    settings: RuntimeSettings,
    policy: HostSettings,
    *,
    models_directory: Path,
) -> RuntimeGraph:
    """Build one dependency graph without opening network connections."""
    database = DatabaseRuntime(settings.database_url.get_secret_value())
    redis = Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=False)
    celery = create_celery(settings.redis_url.get_secret_value())
    publisher = CeleryPublisher(celery)
    s3 = ManagedS3Client(
        endpoint=str(settings.s3_endpoint).rstrip("/"),
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        region=settings.s3_region,
        ca_bundle=settings.aws_ca_bundle,
    )
    timing = TimingSettings()
    storage_settings = StorageSettings(
        endpoint=str(settings.s3_endpoint).rstrip("/"),
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
        encryption=settings.s3_encryption,
        kms_key_id=settings.s3_kms_key_id,
    )
    ingestion_storage = S3ObjectStore(s3, storage_settings, timing)
    export_storage = S3ExportStorage(
        s3, bucket=settings.s3_bucket,
        endpoint=str(settings.s3_endpoint).rstrip("/"),
        encryption=settings.s3_encryption,
        kms_key_id=(
            settings.s3_kms_key_id.get_secret_value()
            if settings.s3_kms_key_id is not None else None
        ),
    )
    source_reader = S3SourceObjectReader(s3, bucket=settings.s3_bucket)

    auth_service = AuthService(
        settings.jwt_secret_key.get_secret_value(), issuer=settings.jwt_issuer,
    )
    shared_auth = SharedAuthResolver(database.sessions, auth_service)
    limiter = RedisRateLimiter(
        redis,
        actor_limit=policy.rate_actor_limit,
        company_limit=policy.rate_company_limit,
        window_seconds=policy.rate_window_seconds,
    )

    embedding = MiniLMEmbeddingAdapter(
        model=settings.embedding_model,
        revision=settings.embedding_revision,
        cache_folder=settings.hf_home,
    )
    tokenizer = MiniLMTokenizerAdapter(
        model=settings.embedding_model,
        revision=settings.embedding_revision,
        cache_folder=settings.hf_home,
    )
    parser = DoclingParserAdapter(
        artifacts_path=settings.docling_artifacts_path,
        easyocr_path=settings.easyocr_module_path,
        pipeline_version=settings.rag_pipeline_version,
        parser_version=settings.rag_parser_version,
        ocr_policy_version=settings.rag_ocr_policy_version,
    )
    extraction_provider = GroqExtractionAdapter(
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.rag_llm_model,
        prompt_version=settings.rag_prompt_version,
    )

    ingestion_repository = IngestionSqlRepository(database.sessions)
    rag_repository = RagSqlRepository(database.sessions)
    review_repository = ReviewSqlRepository(database.sessions)
    search_repository = SearchExportSqlRepository(database.sessions, embedding)
    dashboard_settings = DashboardActivitySettings()
    dashboard_repository = SqlDashboardRepository(
        database.sessions,
        statement_timeout_ms=dashboard_settings.statement_timeout_ms,
    )
    dashboard_catalog = ProcessingValidationCatalogProvider(
        (settings.rag_pipeline_version,),
    )
    dashboard_analytics = AnalyticsService(
        dashboard_repository, dashboard_catalog, dashboard_settings,
    )
    dashboard_activity = ActivityService(dashboard_repository, dashboard_settings)

    # Literal[False] is an invariant, not an environment switch. Supplying the
    # typed value prevents dotenv's textual "false" from becoming a parse edge.
    processing = ProcessingSettings(auto_approval_enabled=False)
    identity_settings = PipelineIdentitySettings(
        pipeline_version=settings.rag_pipeline_version,
        parser_version=settings.rag_parser_version,
        ocr_policy_version=settings.rag_ocr_policy_version,
        embedding_model=settings.embedding_model,
        embedding_revision=settings.embedding_revision,
        llm_provider=settings.llm_provider,
        llm_model=settings.rag_llm_model,
        prompt_version=settings.rag_prompt_version,
    )
    chunker = ChunkingService(
        tokenizer,
        child_tokens=processing.child_tokens,
        parent_tokens=processing.parent_tokens,
        overlap_tokens=processing.prose_overlap_tokens,
    )
    retrieval = RetrievalService(
        embedding, rag_repository,
        candidate_limit=processing.retrieval_candidates,
        selected_limit=processing.selected_evidence,
        context_token_limit=processing.context_tokens,
    )
    extractor = ExtractionService(
        extraction_provider, policy.supported_currencies,
        request_timeout_seconds=processing.llm_timeout_seconds,
    )
    orchestrator = ProcessingOrchestrator(
        rag_repository, source_reader, parser, chunker, embedding, retrieval,
        extractor, processing, build_identity(identity_settings, processing),
    )

    ingestion_service = IngestionService(
        ingestion_repository, ingestion_storage, publisher, timing,
        invoice_reader=rag_repository,
    )
    rag_service = RagReadService(rag_repository)
    review_query = ReviewQueryService(
        review_repository, ReviewSourceAccess(ingestion_storage),
    )
    review_validation = ReviewValidationService(
        review_repository, policy.supported_currencies,
    )
    review_command = ReviewCommandService(
        review_repository, policy.supported_currencies,
    )

    search_settings = SearchExportSettings(
        embedding_model=settings.embedding_model,
        embedding_revision=settings.embedding_revision,
        embedding_dimension=settings.embedding_dimensions,
        supported_currencies=policy.supported_currencies,
    )
    generator = ArtifactGenerator(search_repository, export_storage, search_settings)
    export_worker = ExportWorkerService(search_repository, generator, search_settings)
    search_service = SearchService(search_repository, embedding, search_settings)
    export_command = ExportCommandService(
        search_repository, publisher, generator, search_settings,
    )
    export_query = ExportQueryService(
        search_repository, export_storage, search_settings,
        stream_downloads=policy.stream_downloads,
    )
    reconciler = RuntimeReconciler(
        Dispatcher(ingestion_repository, publisher, timing),
        search_repository,
        ExportDispatcher(search_repository, publisher),
        ExportExpiryService(search_repository, export_storage),
        batch_size=policy.reconcile_batch_size,
        interval_seconds=policy.reconcile_interval_seconds,
    )
    return RuntimeGraph(
        settings=settings, policy=policy, models_directory=models_directory,
        database=database, redis=redis, s3=s3, auth_service=auth_service,
        ingestion_service=ingestion_service,
        ingestion_auth=IngestionAuthAdapter(shared_auth),
        rag_service=rag_service, rag_auth=RagAuthAdapter(shared_auth),
        review_query=review_query, review_validation=review_validation,
        review_command=review_command, review_auth=ReviewAuthAdapter(shared_auth),
        search_service=search_service, export_command=export_command,
        export_query=export_query, export_auth=SearchExportAuthAdapter(shared_auth),
        limiter=limiter,
        process_document=create_document_task(orchestrator),
        generate_export=create_export_task(export_worker),
        reconciler=reconciler, celery=celery,
        dashboard_analytics=dashboard_analytics,
        dashboard_activity=dashboard_activity,
        dashboard_auth=DashboardAuthAdapter(shared_auth),
    )


def create_application(graph: RuntimeGraph) -> FastAPI:
    """Create the one API gateway, with one owner for every route path."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await graph.start()
        try:
            yield
        finally:
            await graph.close()

    app = FastAPI(title="DocuSense API", version="1.0.0", lifespan=lifespan)
    app.state.runtime = graph
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(graph.policy.trusted_hosts),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(graph.policy.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-API-Key"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    async def session_dependency() -> AsyncIterator[Any]:
        async with graph.database.session() as session:
            yield session

    app.include_router(create_auth_router(graph.auth_service, session_dependency))
    app.include_router(create_ingestion_router(
        graph.ingestion_service, graph.ingestion_auth, graph.limiter,
        include_detail=False,
    ))
    app.include_router(create_rag_router(graph.rag_service, graph.rag_auth, graph.limiter))
    # Static Feature 5 paths must precede the review catch-all document detail path.
    app.include_router(create_export_router(
        graph.search_service, graph.export_command, graph.export_query,
        graph.export_auth, graph.limiter,
    ))
    dashboard_dependencies = (
        getattr(graph, "dashboard_analytics", None),
        getattr(graph, "dashboard_activity", None),
        getattr(graph, "dashboard_auth", None),
    )
    if all(value is not None for value in dashboard_dependencies):
        app.include_router(create_dashboard_router(
            dashboard_dependencies[0],  # type: ignore[arg-type]
            dashboard_dependencies[1],  # type: ignore[arg-type]
            dashboard_dependencies[2],  # type: ignore[arg-type]
            graph.limiter,
        ))
    elif any(value is not None for value in dashboard_dependencies):
        raise ValueError("Feature 06 runtime dependencies must be supplied together")
    app.include_router(create_review_router(
        graph.review_query, graph.review_validation, graph.review_command,
        graph.review_auth, graph.limiter,
    ))

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> dict[str, str]:
        await graph.ready()
        return {"status": "ready"}

    # Plain alias for generic localhost probes (e.g. local tooling that polls
    # `GET /health` by convention). Kept out of the OpenAPI schema; readiness
    # checking is the authoritative probe at /health/ready.
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Local tooling also probes `GET /v1/models` when scanning for
    # OpenAI-compatible LLM servers. This application is not an LLM provider,
    # so answer with a valid but empty model list instead of a 404 to keep
    # localhost scan logs quiet. Hidden from the OpenAPI schema.
    @app.get("/v1/models", include_in_schema=False)
    async def probe_models() -> dict[str, object]:
        return {"object": "list", "data": []}

    configure_openapi(app)
    return app


def create_application_from_env(env_file: Path, *, models_directory: Path) -> FastAPI:
    settings = RuntimeSettings.from_env_file(env_file)
    policy = HostSettings.from_env_file(env_file)
    return create_application(
        compose_runtime(settings, policy, models_directory=models_directory)
    )


__all__ = [
    "HostSettings", "RuntimeGraph", "compose_runtime", "create_application",
    "create_application_from_env",
]
