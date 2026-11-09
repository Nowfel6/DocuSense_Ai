"""Private async S3 support. Network calls require explicitly supplied configuration."""
import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Protocol, cast
from urllib.parse import urlsplit
from uuid import UUID

from aiobotocore.config import AioConfig
from aiobotocore.session import get_session

from .errors import IngestionError
from .settings import StorageSettings, TimingSettings
from .validation import Original


class ObjectStore(Protocol):
    def reference(self, company_id: UUID, document_id: UUID, extension: str) -> str: ...
    async def store(self, reference: str, original: Original) -> None: ...
    async def sign(self, reference: str, company_id: UUID, document_id: UUID) -> str: ...
    async def remove_unreferenced(self, reference: str, company_id: UUID, document_id: UUID) -> None: ...


class S3Client(Protocol):
    async def put_object(self, **kwargs: str | bytes | int) -> object: ...
    async def delete_object(self, *, Bucket: str, Key: str) -> object: ...
    async def head_object(self, *, Bucket: str, Key: str) -> object: ...
    async def generate_presigned_url(self, ClientMethod: str, *, Params: dict[str, str], ExpiresIn: int, HttpMethod: str) -> str: ...


class S3ObjectStore:
    def __init__(self, client: S3Client, config: StorageSettings, timing: TimingSettings) -> None:
        self.client, self.config, self.timing = client, config, timing

    def reference(self, company_id: UUID, document_id: UUID, extension: str) -> str:
        """Generate a tenant/document key independent of the uploaded display name."""
        if extension not in ("pdf", "png", "jpg"):
            raise IngestionError("INTERNAL_ERROR")
        return f"s3://{self.config.bucket}/{company_id}/{document_id}/original.{extension}"

    def _key(self, reference: str, company_id: UUID, document_id: UUID) -> str:
        parsed = urlsplit(reference)
        if parsed.scheme != "s3" or parsed.netloc != self.config.bucket or parsed.query or parsed.fragment:
            raise IngestionError("INTERNAL_ERROR")
        allowed = {f"/{company_id}/{document_id}/original.{suffix}" for suffix in ("pdf", "png", "jpg")}
        if parsed.path not in allowed or reference != f"s3://{self.config.bucket}{parsed.path}":
            raise IngestionError("INTERNAL_ERROR")
        return parsed.path[1:]

    async def store(self, reference: str, original: Original) -> None:
        """Write exact original bytes with encryption; never invoke processing."""
        parsed = urlsplit(reference)
        try:
            company, document, _ = parsed.path.strip("/").split("/")
            key = self._key(reference, UUID(company), UUID(document))
        except (ValueError, AttributeError) as exc:
            raise IngestionError("INTERNAL_ERROR") from exc
        payload: dict[str, str | bytes | int] = {
            "Bucket": self.config.bucket, "Key": key, "Body": original.content,
            "ContentLength": len(original.content), "ContentType": original.mime_type,
            "ServerSideEncryption": self.config.encryption,
        }
        # Bucket policies must disallow public access. Omit ACL for bucket-owner-enforced S3.
        if self.config.kms_key_id is not None:
            payload["SSEKMSKeyId"] = self.config.kms_key_id.get_secret_value()
        try:
            await asyncio.wait_for(self.client.put_object(**payload), self.timing.io_timeout_seconds)
        except Exception as exc:
            raise IngestionError("STORAGE_UNAVAILABLE") from exc

    async def sign(self, reference: str, company_id: UUID, document_id: UUID) -> str:
        """Verify authorized object access, then issue a fixed 300-second read URL."""
        key = self._key(reference, company_id, document_id)
        try:
            await asyncio.wait_for(self.client.head_object(Bucket=self.config.bucket, Key=key), self.timing.io_timeout_seconds)
            url = await asyncio.wait_for(self.client.generate_presigned_url(
                "get_object", Params={"Bucket": self.config.bucket, "Key": key},
                ExpiresIn=300, HttpMethod="GET"), self.timing.io_timeout_seconds)
            endpoint, signed = urlsplit(self.config.endpoint), urlsplit(url)
            if signed.scheme != "https" or signed.netloc != endpoint.netloc or signed.username or signed.password or signed.fragment:
                raise ValueError("Invalid signing origin")
            return url
        except Exception as exc:
            raise IngestionError("STORAGE_UNAVAILABLE") from exc

    async def remove_unreferenced(self, reference: str, company_id: UUID, document_id: UUID) -> None:
        """Caller must first prove authoritative rollback/no reference; never bulk-delete."""
        key = self._key(reference, company_id, document_id)
        try:
            await asyncio.wait_for(self.client.delete_object(Bucket=self.config.bucket, Key=key), self.timing.io_timeout_seconds)
        except Exception as exc:
            raise IngestionError("STORAGE_UNAVAILABLE") from exc


@asynccontextmanager
async def open_s3(config: StorageSettings, timing: TimingSettings) -> AsyncIterator[S3ObjectStore]:
    """Own SDK lifecycle. No connection or credential discovery happens on import."""
    session = get_session()
    options = AioConfig(connect_timeout=timing.io_connect_timeout_seconds,
                        read_timeout=timing.io_timeout_seconds, signature_version="s3v4",
                        retries={"total_max_attempts": 1}, s3={"addressing_style": "path"})
    async with session.create_client(
        "s3", endpoint_url=config.endpoint, region_name=config.region, config=options,
        aws_access_key_id=config.access_key.get_secret_value() if config.access_key else None,
        aws_secret_access_key=config.secret_key.get_secret_value() if config.secret_key else None,
    ) as client:
        yield S3ObjectStore(cast(S3Client, client), config, timing)
