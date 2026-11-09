"""Runtime settings and validated recovery timing; no credentials are defaulted."""
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
PositiveInt = Annotated[int, Field(gt=0)]


class TimingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INGESTION_", extra="forbid", frozen=True)
    # Shared processing-job lease policy reconciled with document-processing-rag 1.0.
    lease_seconds: Positive = 300
    heartbeat_seconds: Positive = 30
    dispatch_interval_seconds: Positive = 2
    dispatch_batch_size: PositiveInt = 100
    dispatch_tick_budget_seconds: Positive = 2
    recovery_interval_seconds: Positive = 10
    io_connect_timeout_seconds: Positive = 5
    io_timeout_seconds: Positive = 30
    db_lock_timeout_seconds: Positive = 5
    db_statement_timeout_seconds: Positive = 10
    db_transaction_timeout_seconds: Positive = 15
    broker_publish_timeout_seconds: Positive = 0.1
    acceptance_deadline_seconds: Positive = 90
    upload_receive_timeout_seconds: Positive = 300
    orphan_grace_seconds: Positive = 900
    reconcile_interval_seconds: Positive = 300
    reconcile_batch_size: PositiveInt = 100

    @model_validator(mode="after")
    def timing(self) -> "TimingSettings":
        if self.heartbeat_seconds > self.lease_seconds / 3:
            raise ValueError("Heartbeat must be at most one third of lease")
        if self.heartbeat_seconds + self.io_timeout_seconds + self.db_transaction_timeout_seconds >= self.lease_seconds:
            raise ValueError("Lease must exceed heartbeat plus I/O and transaction deadlines")
        if not self.db_lock_timeout_seconds < self.db_statement_timeout_seconds < self.db_transaction_timeout_seconds:
            raise ValueError("Lock, statement and transaction deadlines must increase")
        if self.io_connect_timeout_seconds > self.io_timeout_seconds:
            raise ValueError("Connection timeout cannot exceed I/O timeout")
        if self.orphan_grace_seconds <= self.upload_receive_timeout_seconds + self.acceptance_deadline_seconds + self.db_transaction_timeout_seconds:
            raise ValueError("Orphan grace must exceed upload, acceptance and transaction deadlines")
        return self


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="S3_", extra="forbid", frozen=True)
    endpoint: str
    bucket: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")]
    access_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    region: str = "us-east-1"
    encryption: Literal["AES256", "aws:kms"] = "AES256"
    kms_key_id: SecretStr | None = None

    @model_validator(mode="after")
    def identity(self) -> "StorageSettings":
        url = urlsplit(self.endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Storage endpoint must be HTTPS without credentials/query/fragment")
        if url.path not in ("", "/"):
            raise ValueError("Storage endpoint cannot contain a path prefix")
        if (self.access_key is None) != (self.secret_key is None):
            raise ValueError("Supply both storage credentials or use managed identity")
        if self.encryption == "aws:kms" and self.kms_key_id is None:
            raise ValueError("KMS encryption requires a configured key")
        return self
