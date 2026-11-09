"""Bounded multipart ingestion and original-byte validation; no processing work."""
import asyncio
from collections.abc import AsyncGenerator, Iterable
from dataclasses import dataclass
import hashlib
import re
import struct
import unicodedata
import zlib

from pydantic import ValidationError
from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import FormData, Headers, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .errors import IngestionError, invalid
from .schemas import MAX_FILE_BYTES, MimeType, UploadForm, Warning

CHUNK_BYTES = 65536
MAX_OVERHEAD = 65536


def unique_fields(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Keep multiplicity checks before query/form conversion loses duplicates."""
    result: dict[str, str] = {}
    for name, value in items:
        if name in result:
            raise invalid(name, "Repeated fields are not allowed.")
        result[name] = value
    return result


def display_name(raw: str | None) -> str:
    if raw is None or any(c in raw for c in ("/", "\\", ":")) or any(
        unicodedata.category(c).startswith("C") for c in raw
    ):
        raise invalid("file", "Unsafe file name.")
    name = unicodedata.normalize("NFC", raw).strip()
    if not 1 <= len(name) <= 255 or name in (".", ".."):
        raise invalid("file", "File name must be a safe nonempty basename of at most 255 characters.")
    return name


class BoundedMultipartParser(MultiPartParser):
    """Pinned Starlette extension: bound file bytes and metadata while streaming."""
    def __init__(self, headers: Headers, stream: AsyncGenerator[bytes, None]) -> None:
        super().__init__(headers, stream, max_files=1, max_fields=2, max_part_size=512)
        self.file_bytes = 0
        self.metadata_bytes = 0
        self.complete = False
        self.digest = hashlib.sha256()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self.file_bytes += end - start
            if self.file_bytes > MAX_FILE_BYTES:
                raise IngestionError("FILE_TOO_LARGE")
            self.digest.update(memoryview(data)[start:end])
        super().on_part_data(data, start, end)

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._count_metadata(end - start)
        super().on_header_field(data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._count_metadata(end - start)
        super().on_header_value(data, start, end)

    def _count_metadata(self, size: int) -> None:
        self.metadata_bytes += size
        if self.metadata_bytes > MAX_OVERHEAD:
            raise invalid("file", "Multipart metadata exceeds the limit.")

    def on_headers_finished(self) -> None:
        names = [name for name, _ in self._current_part.item_headers]
        if names.count(b"content-disposition") != 1 or names.count(b"content-type") > 1:
            raise invalid("file", "Ambiguous multipart headers.")
        # Check raw disposition before python-multipart's legacy Windows basename cleanup.
        raw = self._current_part.content_disposition
        if b"\\" in raw or b"/" in raw:
            raise invalid("file", "Unsafe file name.")
        super().on_headers_finished()

    def on_end(self) -> None:
        self.complete = True


@dataclass(frozen=True)
class Original:
    file_name: str
    content: bytes
    file_hash: str
    mime_type: MimeType
    extension: str
    low_resolution: bool

    @property
    def warnings(self) -> list[Warning]:
        if self.low_resolution:
            return [Warning(code="LOW_IMAGE_RESOLUTION", message="Image width or height is below 1000 pixels.")]
        return []


def _jpeg_size(content: bytes) -> tuple[int, int]:
    end = min(len(content), 262144)  # Header inspection budget, never decode pixels.
    offset = 2
    while offset + 1 < end:
        if content[offset] != 255:
            break
        while offset < end and content[offset] == 255:
            offset += 1
        if offset >= end:
            break
        marker = content[offset]
        offset += 1
        if marker in (0xD9, 0xDA):
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > end:
            break
        length = int.from_bytes(content[offset:offset + 2], "big")
        if length < 2 or offset + length > end:
            break
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if length < 8:
                break
            height, width = struct.unpack(">HH", content[offset + 3:offset + 7])
            components = content[offset + 7]
            if not width or not height or not components or length != 8 + 3 * components:
                break
            return width, height
        offset += length
    raise IngestionError("UNSUPPORTED_FILE_TYPE")


def inspect_original(name: str, content: bytes, claimed_mime: str | None,
                     file_hash: str | None = None) -> Original:
    """Check only bounded original format/headers; leave deep parsing to workers."""
    name = display_name(name)
    if not content:
        raise invalid("file", "File must not be empty.")
    if len(content) > MAX_FILE_BYTES:
        raise IngestionError("FILE_TOO_LARGE")
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    width = height = 1000
    mime: MimeType
    if re.match(rb"%PDF-[12]\.[0-9](?:[\r\n\t ]|$)", content):
        mime, extension, allowed = "application/pdf", "pdf", ("pdf",)
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(content) < 33 or content[8:16] != b"\x00\x00\x00\rIHDR":
            raise IngestionError("UNSUPPORTED_FILE_TYPE")
        if zlib.crc32(content[12:29]) != int.from_bytes(content[29:33], "big"):
            raise IngestionError("UNSUPPORTED_FILE_TYPE")
        width, height = struct.unpack(">II", content[16:24])
        bit_depth, color_type, compression, filtering, interlace = content[24:29]
        valid_depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
        if not width or not height or width > 2147483647 or height > 2147483647 or bit_depth not in valid_depths.get(color_type, ()) or compression or filtering or interlace not in (0, 1):
            raise IngestionError("UNSUPPORTED_FILE_TYPE")
        mime, extension, allowed = "image/png", "png", ("png",)
    elif content.startswith(b"\xff\xd8"):
        width, height = _jpeg_size(content)
        mime, extension, allowed = "image/jpeg", "jpg", ("jpg", "jpeg")
    else:
        raise IngestionError("UNSUPPORTED_FILE_TYPE")
    claimed = claimed_mime.split(";", 1)[0].strip().lower() if claimed_mime else ""
    if suffix not in allowed or claimed not in ("", "application/octet-stream", mime):
        raise IngestionError("UNSUPPORTED_FILE_TYPE")
    return Original(name, content, file_hash or hashlib.sha256(content).hexdigest(),
                    mime, extension, width < 1000 or height < 1000)


async def parse_upload(headers: Headers, source: AsyncGenerator[bytes, None],
                       timeout: float) -> tuple[Original, UploadForm]:
    """Consume bounded multipart input and close every temporary file on all exits."""
    if len(headers.getlist("content-type")) != 1 or headers["content-type"].split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise invalid("file", "Expected multipart/form-data.")

    async def bounded() -> AsyncGenerator[bytes, None]:
        total = 0
        async for chunk in source:
            total += len(chunk)
            if total > MAX_FILE_BYTES + MAX_OVERHEAD:
                raise IngestionError("FILE_TOO_LARGE")
            for start in range(0, len(chunk), CHUNK_BYTES):
                yield chunk[start:start + CHUNK_BYTES]

    parser = BoundedMultipartParser(headers, bounded())
    form: FormData | None = None
    try:
        form = await asyncio.wait_for(parser.parse(), timeout)
        if not parser.complete:
            raise invalid("file", "Incomplete multipart request.")
        file: UploadFile | None = None
        fields: list[tuple[str, str]] = []
        for key, value in form.multi_items():
            if isinstance(value, UploadFile):
                if key != "file" or file is not None:
                    raise invalid("file", "Exactly one file is required.")
                file = value
            else:
                fields.append((key, value))
        if file is None:
            raise invalid("file", "Exactly one file is required.")
        scalar = UploadForm.model_validate(unique_fields(fields))
        # Streamed limit was enforced before spooling. Bounded read preserves identical bytes.
        content = await file.read(MAX_FILE_BYTES + 1)
        original = inspect_original(display_name(file.filename), content, file.content_type, parser.digest.hexdigest())
        return original, scalar
    except ValidationError as exc:
        raise invalid("form", "Invalid form fields.") from exc
    except (MultiPartException, MultipartParseError, ValueError, LookupError, asyncio.TimeoutError) as exc:
        raise invalid("file", "Invalid or incomplete multipart request.") from exc
    finally:
        if form is not None:
            await form.close()
