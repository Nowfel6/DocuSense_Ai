"""Validated Feature 05 settings; no secret has a source-code default."""
from __future__ import annotations

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchExportSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCUSENSE_SEARCH_EXPORT_",
        extra="ignore",
        frozen=True,
    )

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str
    embedding_dimension: int = 384
    supported_currencies: frozenset[str]

    search_page_size_default: int = 20
    search_page_size_max: int = 100
    export_document_max: int = 50_000
    sync_document_max: int = 500
    sync_row_estimate_max: int = 50_000
    sync_uncompressed_estimate_max: int = 64 * 1024 * 1024
    export_row_max: int = 1_000_000
    export_uncompressed_max: int = 2 * 1024 * 1024 * 1024
    active_async_per_user: int = 3
    active_async_per_company: int = 10
    lease_seconds: int = 300
    heartbeat_seconds: int = 60
    max_attempts: int = 4
    retention_seconds: int = 7 * 24 * 60 * 60
    signed_url_seconds: int = 300
    criteria_json_max_bytes: int = 16 * 1024
    request_body_max_bytes: int = 4 * 1024 * 1024
    spool_memory_max_bytes: int = 8 * 1024 * 1024
    xlsx_build_id: str = "stdlib-ooxml-v1"

    @field_validator("embedding_revision", "xlsx_build_id")
    @classmethod
    def nonblank_identity(cls, value: str) -> str:
        result = value.strip()
        if not result or result.lower() in {"latest", "main", "master"}:
            raise ValueError("Immutable non-floating identity is required")
        return result

    @field_validator("supported_currencies")
    @classmethod
    def currency_set(cls, value: frozenset[str]) -> frozenset[str]:
        if not value or any(len(item) != 3 or not item.isascii() or not item.isupper() for item in value):
            raise ValueError("Supported currencies must be uppercase ISO-like codes")
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> "SearchExportSettings":
        if self.embedding_model != "sentence-transformers/all-MiniLM-L6-v2":
            raise ValueError("Feature 05 model identity is locked")
        if self.embedding_dimension != 384:
            raise ValueError("Feature 05 embedding dimension is locked to 384")
        if not 1 <= self.search_page_size_default <= self.search_page_size_max <= 100:
            raise ValueError("Invalid search page policy")
        if not 1 <= self.sync_document_max <= 500 <= self.export_document_max <= 50_000:
            raise ValueError("Invalid export document policy")
        if not 1 <= self.sync_row_estimate_max <= self.export_row_max <= 1_000_000:
            raise ValueError("Invalid row policy")
        if not 1 <= self.sync_uncompressed_estimate_max <= self.export_uncompressed_max:
            raise ValueError("Invalid byte policy")
        if self.lease_seconds != 300 or not 1 <= self.heartbeat_seconds <= 60:
            raise ValueError("Lease/heartbeat policy mismatch")
        if self.max_attempts != 4 or self.retention_seconds != 604_800:
            raise ValueError("Attempt/retention policy mismatch")
        if not 1 <= self.signed_url_seconds <= 300:
            raise ValueError("Signed URL exceeds five minutes")
        if self.criteria_json_max_bytes > 16 * 1024:
            raise ValueError("Criteria metadata exceeds contract limit")
        return self


__all__ = ["SearchExportSettings"]


