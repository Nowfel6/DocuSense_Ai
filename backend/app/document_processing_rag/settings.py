"""Validated non-secret RAG processing configuration."""
import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .schemas import ProcessingIdentity

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
PositiveInt = Annotated[int, Field(gt=0)]


class ProcessingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROCESSING_", extra="forbid", frozen=True)

    lease_seconds: Positive = 300
    heartbeat_seconds: Positive = 30
    object_read_timeout_seconds: Positive = 120
    parser_timeout_seconds: Positive = 600
    embedding_batch_timeout_seconds: Positive = 120
    llm_timeout_seconds: Positive = 120
    attempt_timeout_seconds: Positive = 1200
    max_tasks_per_child: PositiveInt = 50
    embedding_batch_size: Annotated[int, Field(ge=1, le=128)] = 32
    retrieval_candidates: Literal[24] = 24
    selected_evidence: Literal[12] = 12
    context_tokens: Literal[8000] = 8000
    child_tokens: Literal[450] = 450
    parent_tokens: Literal[1800] = 1800
    prose_overlap_tokens: Literal[50] = 50
    auto_approval_enabled: Literal[False] = False

    @model_validator(mode="after")
    def timing(self) -> "ProcessingSettings":
        if self.heartbeat_seconds > self.lease_seconds / 3:
            raise ValueError("Heartbeat must be at most one third of the lease")
        if self.object_read_timeout_seconds >= self.attempt_timeout_seconds:
            raise ValueError("Object timeout must fit inside the attempt")
        if self.parser_timeout_seconds >= self.attempt_timeout_seconds:
            raise ValueError("Parser timeout must fit inside the attempt")
        if self.llm_timeout_seconds * 2 >= self.attempt_timeout_seconds:
            raise ValueError("Original and corrective LLM calls must fit inside the attempt")
        return self


class PipelineIdentitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", extra="forbid", frozen=True)

    pipeline_version: Annotated[str, Field(min_length=1, max_length=64)]
    parser_version: Annotated[str, Field(min_length=1, max_length=100)]
    ocr_policy_version: Annotated[str, Field(min_length=1, max_length=64)]
    embedding_model: Literal["sentence-transformers/all-MiniLM-L6-v2"] = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: Annotated[str, Field(min_length=1, max_length=255)]
    llm_provider: Annotated[str, Field(min_length=1, max_length=100)]
    llm_model: Annotated[str, Field(min_length=1, max_length=255)]
    prompt_version: Annotated[str, Field(min_length=1, max_length=64)]
    schema_version: Literal["commercial-invoice-v1"] = "commercial-invoice-v1"

    @model_validator(mode="after")
    def immutable_versions(self) -> "PipelineIdentitySettings":
        floating = {"main", "master", "latest", "head", "default"}
        if self.embedding_revision.strip().lower() in floating:
            raise ValueError("Embedding revision must be immutable")
        return self


def build_identity(identity: PipelineIdentitySettings,
                   processing: ProcessingSettings) -> ProcessingIdentity:
    """Hash canonical non-secret settings into the persisted run identity."""
    material = {"identity": identity.model_dump(mode="json"),
                "processing": processing.model_dump(mode="json")}
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return ProcessingIdentity(
        pipeline_version=identity.pipeline_version,
        configuration_hash=hashlib.sha256(encoded).hexdigest(),
        parser_version=identity.parser_version,
        ocr_policy_version=identity.ocr_policy_version,
        embedding_revision=identity.embedding_revision,
        llm_provider=identity.llm_provider,
        llm_model=identity.llm_model,
        prompt_version=identity.prompt_version,
        schema_version=identity.schema_version,
    )
