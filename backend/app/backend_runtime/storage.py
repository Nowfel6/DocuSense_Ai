"""Concrete encrypted private S3 adapter for Feature 5 export artifacts."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import hashlib
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from botocore.exceptions import ClientError

from ..document_search_export.storage import require_private_object_key


class S3Client(Protocol):
    async def put_object(self, **kwargs: Any) -> Any: ...
    async def head_object(self, **kwargs: Any) -> dict[str, Any]: ...
    async def get_object(self, **kwargs: Any) -> dict[str, Any]: ...
    async def copy_object(self, **kwargs: Any) -> Any: ...
    async def delete_object(self, **kwargs: Any) -> Any: ...
    async def generate_presigned_url(self, *args: Any, **kwargs: Any) -> str: ...


class ManagedS3Client:
    """One explicitly started TLS client shared by API and worker adapters."""

    def __init__(
        self, *, endpoint: str, access_key: str, secret_key: str,
        region: str, ca_bundle: Path,
    ) -> None:
        self._settings = {
            "endpoint_url": endpoint,
            "region_name": region,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "verify": str(ca_bundle),
        }
        self._manager: Any | None = None
        self._client: Any | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        config = AioConfig(
            connect_timeout=10, read_timeout=30, signature_version="s3v4",
            retries={"total_max_attempts": 1}, s3={"addressing_style": "path"},
        )
        self._manager = get_session().create_client("s3", config=config, **self._settings)
        self._client = await self._manager.__aenter__()

    async def close(self) -> None:
        manager, self._manager, self._client = self._manager, None, None
        if manager is not None:
            await manager.__aexit__(None, None, None)

    def _require(self) -> Any:
        if self._client is None:
            raise RuntimeError("Object storage client has not been started")
        return self._client

    async def verify_bucket(self, bucket: str) -> None:
        await self._require().head_bucket(Bucket=bucket)

    async def put_object(self, **kwargs: Any) -> Any:
        return await self._require().put_object(**kwargs)

    async def head_object(self, **kwargs: Any) -> dict[str, Any]:
        return await self._require().head_object(**kwargs)

    async def get_object(self, **kwargs: Any) -> dict[str, Any]:
        return await self._require().get_object(**kwargs)

    async def copy_object(self, **kwargs: Any) -> Any:
        return await self._require().copy_object(**kwargs)

    async def delete_object(self, **kwargs: Any) -> Any:
        return await self._require().delete_object(**kwargs)

    async def generate_presigned_url(self, *args: Any, **kwargs: Any) -> str:
        return await self._require().generate_presigned_url(*args, **kwargs)


class S3ExportStorage:
    def __init__(self, client: S3Client, *, bucket: str, endpoint: str,
                 encryption: str = "AES256", kms_key_id: str | None = None,
                 io_timeout: float = 30.0) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Object storage endpoint must be credential-free HTTPS")
        if encryption == "aws:kms" and not kms_key_id:
            raise ValueError("KMS encryption requires a key ID")
        self.client = client
        self.bucket = bucket
        self.endpoint = endpoint.rstrip("/")
        self.encryption = encryption
        self.kms_key_id = kms_key_id
        self.io_timeout = io_timeout

    @staticmethod
    def _export_id(object_key: str) -> UUID:
        parts = object_key.split("/")
        if len(parts) < 3 or parts[0] != "exports":
            raise ValueError("Unexpected export object key")
        try:
            export_id = UUID(parts[1])
        except ValueError as exc:
            raise ValueError("Unexpected export object key") from exc
        require_private_object_key(object_key, export_id)
        return export_id

    async def put_staging(self, export_id: UUID, attempt: int, source: BinaryIO,
                          size_bytes: int, content_type: str, sha256: str) -> str:
        if attempt < 1 or size_bytes < 1 or len(sha256) != 64:
            raise ValueError("Invalid staging metadata")
        key = f"exports/{export_id}/attempt-{attempt}/{uuid4().hex}.staging"
        data = await asyncio.to_thread(source.read)
        if len(data) != size_bytes or hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError("Artifact bytes do not match declared metadata")
        request: dict[str, Any] = {
            "Bucket": self.bucket, "Key": key, "Body": data,
            "ContentLength": size_bytes, "ContentType": content_type,
            "ServerSideEncryption": self.encryption,
            "Metadata": {"sha256": sha256, "export-id": str(export_id)},
        }
        if self.kms_key_id:
            request["SSEKMSKeyId"] = self.kms_key_id
        await asyncio.wait_for(self.client.put_object(**request), self.io_timeout)
        return key

    async def verify(self, object_key: str, size_bytes: int, sha256: str) -> bool:
        self._export_id(object_key)
        try:
            head = await asyncio.wait_for(
                self.client.head_object(Bucket=self.bucket, Key=object_key), self.io_timeout,
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        metadata = head.get("Metadata") or {}
        return (
            int(head.get("ContentLength", -1)) == size_bytes
            and metadata.get("sha256") == sha256
            and head.get("ServerSideEncryption") == self.encryption
        )

    async def promote(self, staging_key: str, export_id: UUID, sha256: str) -> str:
        if self._export_id(staging_key) != export_id or "/attempt-" not in staging_key:
            raise ValueError("Staging ownership mismatch")
        final_key = f"exports/{export_id}/artifact-{sha256}"
        try:
            head = await self.client.head_object(Bucket=self.bucket, Key=final_key)
            if (head.get("Metadata") or {}).get("sha256") == sha256:
                return final_key
            raise ValueError("Deterministic final key contains different content")
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        request: dict[str, Any] = {
            "Bucket": self.bucket, "Key": final_key,
            "CopySource": {"Bucket": self.bucket, "Key": staging_key},
            "MetadataDirective": "COPY", "ServerSideEncryption": self.encryption,
        }
        if self.kms_key_id:
            request["SSEKMSKeyId"] = self.kms_key_id
        await asyncio.wait_for(self.client.copy_object(**request), self.io_timeout)
        return final_key

    async def read(self, object_key: str) -> bytes:
        self._export_id(object_key)
        response = await asyncio.wait_for(
            self.client.get_object(Bucket=self.bucket, Key=object_key), self.io_timeout,
        )
        return await asyncio.wait_for(response["Body"].read(), self.io_timeout)

    async def sign(self, object_key: str, expires_seconds: int) -> str:
        self._export_id(object_key)
        if not 1 <= expires_seconds <= 300:
            raise ValueError("Signing lifetime must be 1..300 seconds")
        await asyncio.wait_for(
            self.client.head_object(Bucket=self.bucket, Key=object_key), self.io_timeout,
        )
        url = await self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=expires_seconds, HttpMethod="GET",
        )
        expected, actual = urlsplit(self.endpoint), urlsplit(url)
        if actual.scheme != "https" or actual.netloc != expected.netloc or actual.fragment:
            raise ValueError("Signer returned an unsafe origin")
        return url

    async def delete_exact(self, object_key: str) -> None:
        self._export_id(object_key)
        await asyncio.wait_for(
            self.client.delete_object(Bucket=self.bucket, Key=object_key), self.io_timeout,
        )


class S3SourceObjectReader:
    """Read one exact persisted ingestion original with a hard byte bound."""

    def __init__(self, client: S3Client, *, bucket: str, io_timeout: float = 30.0) -> None:
        self.client = client
        self.bucket = bucket
        self.io_timeout = io_timeout

    def _key(self, private_reference: str) -> str:
        parsed = urlsplit(private_reference)
        parts = parsed.path.strip("/").split("/")
        if (
            parsed.scheme != "s3" or parsed.netloc != self.bucket
            or parsed.query or parsed.fragment or "\\" in private_reference
            or len(parts) != 3 or not parts[2].startswith("original.")
        ):
            raise ValueError("Invalid private source reference")
        UUID(parts[0])
        UUID(parts[1])
        if parts[2] not in {"original.pdf", "original.png", "original.jpg"}:
            raise ValueError("Invalid private source reference")
        return "/".join(parts)

    async def read(self, private_reference: str, maximum_bytes: int) -> bytes:
        if not 1 <= maximum_bytes <= 10_485_760:
            raise ValueError("Invalid source byte bound")
        key = self._key(private_reference)
        head = await asyncio.wait_for(
            self.client.head_object(Bucket=self.bucket, Key=key), self.io_timeout,
        )
        size = int(head.get("ContentLength", -1))
        if size < 1 or size > maximum_bytes:
            raise ValueError("Source object is empty or oversized")
        response = await asyncio.wait_for(
            self.client.get_object(Bucket=self.bucket, Key=key), self.io_timeout,
        )
        # `Body.read(N)` truncates to the first chunk of a chunked response, which
        # surfaces as a "size changed" failure against MinIO + aioboto. Stream
        # via `iter_chunks()` instead and accumulate until we either match the
        # declared size or exceed the configured hard byte bound.
        chunks: list[bytes] = []
        total = 0
        async for chunk in response["Body"].iter_chunks(chunk_size=65536):
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError("Source object is empty or oversized")
            chunks.append(chunk)
        data = b"".join(chunks)
        if len(data) != size:
            raise ValueError("Source object size changed while reading")
        return data


@asynccontextmanager
async def open_export_storage(
    *, endpoint: str, bucket: str, access_key: str, secret_key: str,
    region: str, ca_bundle: Path, encryption: str = "AES256",
    kms_key_id: str | None = None,
) -> AsyncIterator[S3ExportStorage]:
    config = AioConfig(
        connect_timeout=10, read_timeout=30, signature_version="s3v4",
        retries={"total_max_attempts": 1}, s3={"addressing_style": "path"},
    )
    session = get_session()
    async with session.create_client(
        "s3", endpoint_url=endpoint, region_name=region, config=config,
        aws_access_key_id=access_key, aws_secret_access_key=secret_key,
        verify=str(ca_bundle),
    ) as client:
        yield S3ExportStorage(
            cast(S3Client, client), bucket=bucket, endpoint=endpoint,
            encryption=encryption, kms_key_id=kms_key_id,
        )


__all__ = [
    "ManagedS3Client", "S3ExportStorage", "S3SourceObjectReader",
    "open_export_storage",
]


