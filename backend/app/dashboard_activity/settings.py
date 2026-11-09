"""Validated non-secret Feature 06 runtime policy."""
from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardActivitySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCUSENSE_DASHBOARD_", extra="ignore", frozen=True,
    )

    definition_version: str = "dashboard-metrics-v1"
    default_period_days: int = Field(default=30, ge=1, le=366)
    maximum_period_days: int = Field(default=366, ge=1, le=366)
    maximum_buckets: int = Field(default=366, ge=1, le=366)
    activity_page_size_default: int = Field(default=20, ge=1, le=100)
    activity_page_size_maximum: int = Field(default=100, ge=1, le=100)
    statement_timeout_ms: int = Field(default=2_000, ge=100, le=30_000)

    @model_validator(mode="after")
    def locked_policy(self) -> "DashboardActivitySettings":
        if self.definition_version != "dashboard-metrics-v1":
            raise ValueError("Dashboard metric definition version is locked")
        if self.default_period_days != 30 or self.maximum_period_days != 366:
            raise ValueError("Dashboard period policy is locked")
        if self.maximum_buckets != 366:
            raise ValueError("Dashboard bucket limit is locked")
        if self.activity_page_size_default != 20 or self.activity_page_size_maximum != 100:
            raise ValueError("Activity pagination policy is locked")
        return self


__all__ = ["DashboardActivitySettings"]
