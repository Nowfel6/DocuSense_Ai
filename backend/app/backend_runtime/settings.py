"""Strict environment-backed runtime settings with no secret defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import AnyUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    """Validate all external adapter identities before any connection is opened."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    redis_url: SecretStr = Field(validation_alias="REDIS_URL")
    jwt_secret_key: SecretStr = Field(min_length=32, validation_alias="JWT_SECRET_KEY")
    jwt_issuer: str = Field(default="docusense", min_length=1, max_length=128)
    jwt_algorithm: Literal["HS256"] = "HS256"

    s3_endpoint: AnyUrl = Field(validation_alias="S3_ENDPOINT")
    s3_bucket: str = Field(min_length=3, max_length=63, validation_alias="S3_BUCKET")
    s3_access_key: SecretStr = Field(validation_alias="S3_ACCESS_KEY")
    s3_secret_key: SecretStr = Field(validation_alias="S3_SECRET_KEY")
    s3_region: str = Field(default="us-east-1", validation_alias="S3_REGION")
    s3_encryption: Literal["AES256", "aws:kms"] = Field(
        default="AES256", validation_alias="S3_ENCRYPTION"
    )
    s3_kms_key_id: SecretStr | None = Field(default=None, validation_alias="S3_KMS_KEY_ID")
    aws_ca_bundle: Path = Field(validation_alias="AWS_CA_BUNDLE")

    embedding_model: Literal["sentence-transformers/all-MiniLM-L6-v2"] = Field(
        validation_alias="EMBEDDING_MODEL"
    )
    embedding_revision: str = Field(min_length=40, max_length=64, validation_alias="EMBEDDING_REVISION")
    embedding_dimensions: Literal[384] = Field(validation_alias="EMBEDDING_DIMENSIONS")
    hf_home: Path = Field(validation_alias="HF_HOME")

    docling_artifacts_path: Path = Field(validation_alias="DOCLING_ARTIFACTS_PATH")
    easyocr_module_path: Path = Field(validation_alias="EASYOCR_MODULE_PATH")
    rag_pipeline_version: str = Field(min_length=1, max_length=64, validation_alias="RAG_PIPELINE_VERSION")
    rag_parser_version: str = Field(min_length=1, max_length=100, validation_alias="RAG_PARSER_VERSION")
    rag_ocr_policy_version: str = Field(min_length=1, max_length=64, validation_alias="RAG_OCR_POLICY_VERSION")

    llm_provider: Literal["groq"] = Field(validation_alias="LLM_PROVIDER")
    llm_api_key: SecretStr = Field(min_length=20, validation_alias="LLM_API_KEY")
    rag_llm_model: Literal["openai/gpt-oss-20b"] = Field(validation_alias="RAG_LLM_MODEL")
    rag_prompt_version: str = Field(min_length=1, max_length=64, validation_alias="RAG_PROMPT_VERSION")

    @field_validator("embedding_revision")
    @classmethod
    def immutable_revision(cls, value: str) -> str:
        lowered = value.strip().lower()
        if lowered in {"main", "master", "latest", "head", "default"}:
            raise ValueError("Embedding revision must be immutable")
        return value.strip()

    @model_validator(mode="after")
    def private_tls_and_artifacts(self) -> "RuntimeSettings":
        if self.s3_endpoint.scheme != "https":
            raise ValueError("Private object storage must use HTTPS")
        if self.s3_encryption == "aws:kms" and (
            self.s3_kms_key_id is None or not self.s3_kms_key_id.get_secret_value().strip()
        ):
            raise ValueError("KMS encryption requires S3_KMS_KEY_ID")
        for path, label in (
            (self.aws_ca_bundle, "AWS CA bundle"),
            (self.hf_home, "Hugging Face cache"),
            (self.docling_artifacts_path, "Docling artifacts"),
            (self.easyocr_module_path, "EasyOCR artifacts"),
        ):
            if not path.exists():
                raise ValueError(f"{label} path does not exist")
        return self

    @classmethod
    def from_env_file(cls, path: Path) -> "RuntimeSettings":
        path = path.resolve()
        values = {key: value for key, value in dotenv_values(path).items() if value is not None}
        # A checked-in/local env file supplies the complete baseline. Container
        # deployments may override individual runtime locations (for example
        # Windows model-cache paths mounted at /app) without maintaining a
        # second secret-bearing env file.
        values.update({key: os.environ[key] for key in values if key in os.environ})
        for key in ("AWS_CA_BUNDLE", "HF_HOME", "DOCLING_ARTIFACTS_PATH", "EASYOCR_MODULE_PATH"):
            if key in values:
                candidate = Path(values[key])
                if not candidate.is_absolute():
                    values[key] = str((path.parent / candidate).resolve())
        if "EMBEDDING_DIMENSIONS" in values:
            values["EMBEDDING_DIMENSIONS"] = int(values["EMBEDDING_DIMENSIONS"])
        return cls(**values)
