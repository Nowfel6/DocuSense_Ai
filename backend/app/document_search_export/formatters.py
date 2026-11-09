"""Deterministic, provider-free CSV/XLSX/JSON/ZIP export writers."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import io
from itertools import chain
import json
from pathlib import PurePosixPath
import re
from typing import BinaryIO, Iterable, Iterator
from uuid import UUID
import zipfile

from .errors import WorkerFailure
from .repository import ExportInvoice, ExportLine
from .schemas import ExportFormat

HEADERS = (
    "InvoiceNo", "Supplier", "Date", "Currency", "Subtotal", "Tax", "Total",
    "ItemDescription", "Quantity", "UnitPrice", "ItemTotal",
)
SCHEMA_VERSION = "docusense-approved-invoice-export-v1"
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
CONTENT_TYPES: dict[ExportFormat, str] = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class FormatSummary:
    document_count: int
    row_count: int
    size_bytes: int
    sha256: str
    file_name: str
    content_type: str


class _TrackedInvoices:
    def __init__(self, invoices: Iterable[ExportInvoice]) -> None:
        self._invoices = iter(invoices)
        self.document_count = 0
        self._seen: set[UUID] = set()

    def __iter__(self) -> Iterator[ExportInvoice]:
        for invoice in self._invoices:
            if invoice.document_id in self._seen:
                raise WorkerFailure("EXPORT_DATA_INTEGRITY_ERROR", retryable=False)
            self._seen.add(invoice.document_id)
            self.document_count += 1
            yield invoice


def export_file_name(export_id: UUID, generated_at: datetime,
                     format_name: ExportFormat) -> str:
    stamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%d")
    return f"docusense_export_{stamp}_{export_id.hex[:8]}.{format_name}"


def async_zip_name(export_id: UUID, generated_at: datetime) -> str:
    stamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%d")
    return f"docusense_export_{stamp}_{export_id.hex[:8]}.zip"


def _safe_untrusted(value: str | None) -> str:
    if value is None:
        return ""
    return "'" + value if value.startswith(FORMULA_PREFIXES) else value


def _money(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".2f")


def _four(value: Decimal | None) -> str:
    if value is None:
        return ""
    rendered = format(value, ".4f").rstrip("0").rstrip(".")
    return rendered or "0"


def _rows(invoices: Iterable[ExportInvoice]) -> Iterator[tuple[object, ...]]:
    for invoice in invoices:
        lines: tuple[ExportLine | None, ...] = invoice.lines or (None,)
        for line in lines:
            yield (
                _safe_untrusted(invoice.invoice_number),
                _safe_untrusted(invoice.supplier_name),
                invoice.date_issued,
                _safe_untrusted(invoice.currency),
                invoice.subtotal,
                invoice.tax_amount,
                invoice.grand_total,
                _safe_untrusted(line.description) if line else "",
                line.quantity if line else None,
                line.unit_price if line else None,
                line.total_price if line else None,
            )


def _csv_value(index: int, value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return _four(value) if index in (8, 9) else _money(value)
    if value is None:
        return ""
    return str(value)


def _write_csv(destination: BinaryIO, invoices: Iterable[ExportInvoice],
               row_limit: int) -> int:
    destination.write(b"\xef\xbb\xbf")
    row_count = 0
    for row in chain((HEADERS,), _rows(invoices)):
        buffer = io.StringIO(newline="")
        csv.writer(buffer, lineterminator="\r\n").writerow(
            row if row is HEADERS else tuple(_csv_value(i, value) for i, value in enumerate(row))
        )
        destination.write(buffer.getvalue().encode("utf-8"))
        if row is not HEADERS:
            row_count += 1
            if row_count > row_limit:
                raise WorkerFailure("EXPORT_LIMIT_EXCEEDED", retryable=False)
    return row_count


def _json_invoice(invoice: ExportInvoice) -> dict[str, object]:
    return {
        "document_id": str(invoice.document_id),
        "invoice_id": str(invoice.invoice_id),
        "review_revision": invoice.review_revision,
        "invoice_number": invoice.invoice_number,
        "supplier_name": invoice.supplier_name,
        "date_issued": invoice.date_issued.isoformat() if invoice.date_issued else None,
        "currency": invoice.currency,
        "subtotal": _money(invoice.subtotal) or None,
        "tax_amount": _money(invoice.tax_amount) or None,
        "grand_total": _money(invoice.grand_total) or None,
        "is_math_valid": invoice.is_math_valid,
        "line_items": [
            {
                "line_item_id": str(line.line_item_id),
                "line_order": line.line_order,
                "description": line.description,
                "quantity": _four(line.quantity) or None,
                "unit_price": _four(line.unit_price) or None,
                "total_price": _money(line.total_price) or None,
            }
            for line in invoice.lines
        ],
    }


def _write_json(destination: BinaryIO, export_id: UUID, generated_at: datetime,
                invoices: Iterable[ExportInvoice], row_limit: int) -> int:
    prefix = {
        "schema_version": SCHEMA_VERSION,
        "export_id": str(export_id),
        "generated_at": generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    destination.write(b"{")
    destination.write(json.dumps(prefix, ensure_ascii=False, separators=(",", ":"))[1:-1].encode("utf-8"))
    destination.write(b',"invoices":[')
    row_count = 0
    for index, invoice in enumerate(invoices):
        if index:
            destination.write(b",")
        destination.write(json.dumps(_json_invoice(invoice), ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8"))
        row_count += max(1, len(invoice.lines))
        if row_count > row_limit:
            raise WorkerFailure("EXPORT_LIMIT_EXCEEDED", retryable=False)
    destination.write(b"]}")
    return row_count


def _xml_text(value: str) -> str:
    result = (value.replace("&", "&amp;").replace("<", "&lt;")
              .replace(">", "&gt;").replace('"', "&quot;"))
    return result.replace("\r", "&#13;").replace("\t", "&#9;")


def _column(index: int) -> str:
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _excel_date(value: date) -> int:
    return (value - date(1899, 12, 30)).days


def _cell(reference: str, value: object, column: int, header: bool = False) -> str:
    if header or isinstance(value, str):
        style = ' s="1"' if header else ""
        return f'<c r="{reference}" t="inlineStr"{style}><is><t xml:space="preserve">{_xml_text(str(value))}</t></is></c>'
    if isinstance(value, date):
        return f'<c r="{reference}" s="2" t="n"><v>{_excel_date(value)}</v></c>'
    if isinstance(value, Decimal):
        style = "4" if column in (8, 9) else "3"
        rendered = _four(value) if column in (8, 9) else _money(value)
        return f'<c r="{reference}" s="{style}" t="n"><v>{rendered}</v></c>'
    if value is None:
        return f'<c r="{reference}" t="inlineStr"><is><t></t></is></c>'
    return f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{_xml_text(str(value))}</t></is></c>'


def _zip_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, data)


def _write_xlsx(destination: BinaryIO, invoices: Iterable[ExportInvoice],
                row_limit: int) -> int:
    header_cells = "".join(
        _cell(f"{_column(index)}1", value, index, True)
        for index, value in enumerate(HEADERS)
    )
    content_types = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    root_rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Approved Invoices" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    styles = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="2"><numFmt numFmtId="164" formatCode="0.00"/><numFmt numFmtId="165" formatCode="0.####"/></numFmts><fonts count="2"><font/><font><b/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs></styleSheet>'''
    row_count = 0
    with zipfile.ZipFile(destination, "w") as archive:
        _zip_entry(archive, "[Content_Types].xml", content_types)
        _zip_entry(archive, "_rels/.rels", root_rels)
        _zip_entry(archive, "xl/workbook.xml", workbook)
        _zip_entry(archive, "xl/_rels/workbook.xml.rels", workbook_rels)
        _zip_entry(archive, "xl/styles.xml", styles)
        info = zipfile.ZipInfo(
            "xl/worksheets/sheet1.xml", date_time=(1980, 1, 1, 0, 0, 0)
        )
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o600 << 16
        with archive.open(info, "w") as sheet:
            sheet.write(
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            )
            sheet.write(f'<row r="1">{header_cells}</row>'.encode("utf-8"))
            for row_number, row in enumerate(_rows(invoices), start=2):
                cells = "".join(
                    _cell(f"{_column(index)}{row_number}", value, index)
                    for index, value in enumerate(row)
                )
                sheet.write(f'<row r="{row_number}">{cells}</row>'.encode("utf-8"))
                row_count += 1
                if row_count > row_limit:
                    raise WorkerFailure("EXPORT_LIMIT_EXCEEDED", retryable=False)
            sheet.write(b"</sheetData></worksheet>")
    return row_count


def write_export(destination: BinaryIO, export_id: UUID, generated_at: datetime,
                 format_name: ExportFormat, invoices: Iterable[ExportInvoice],
                 *, row_limit: int = 1_000_000,
                 byte_limit: int = 2 * 1024 * 1024 * 1024) -> FormatSummary:
    """Write one deterministic direct-format artifact into a seekable spool."""
    tracked = _TrackedInvoices(invoices)
    if format_name == "csv":
        row_count = _write_csv(destination, tracked, row_limit)
    elif format_name == "xlsx":
        row_count = _write_xlsx(destination, tracked, row_limit)
    else:
        row_count = _write_json(destination, export_id, generated_at, tracked, row_limit)
    if tracked.document_count == 0:
        raise WorkerFailure("EXPORT_DATA_INTEGRITY_ERROR", retryable=False)
    if row_count > row_limit:
        raise WorkerFailure("EXPORT_LIMIT_EXCEEDED", retryable=False)
    size = destination.tell()
    if size <= 0 or size > byte_limit:
        raise WorkerFailure("EXPORT_LIMIT_EXCEEDED", retryable=False)
    destination.seek(0)
    digest = hashlib.sha256(destination.read()).hexdigest()
    destination.seek(0)
    return FormatSummary(
        document_count=tracked.document_count,
        row_count=row_count,
        size_bytes=size,
        sha256=digest,
        file_name=export_file_name(export_id, generated_at, format_name),
        content_type=CONTENT_TYPES[format_name],
    )


def write_async_zip_stream(destination: BinaryIO, export_id: UUID,
                           generated_at: datetime, format_name: ExportFormat,
                           data_source: BinaryIO,
                           data_summary: FormatSummary) -> FormatSummary:
    """Stream one data file and deterministic manifest into the async ZIP."""
    if not _SAFE_NAME.fullmatch(data_summary.file_name):
        raise WorkerFailure("EXPORT_FORMATTER_FAILED", retryable=False)
    path = PurePosixPath(data_summary.file_name)
    if path.name != data_summary.file_name or path.is_absolute() or ".." in path.parts:
        raise WorkerFailure("EXPORT_FORMATTER_FAILED", retryable=False)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "export_id": str(export_id),
        "format": format_name,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "document_count": data_summary.document_count,
        "row_count": data_summary.row_count,
        "data_file_name": data_summary.file_name,
        "data_size_bytes": data_summary.size_bytes,
        "data_sha256": data_summary.sha256,
    }
    with zipfile.ZipFile(destination, "w") as archive:
        info = zipfile.ZipInfo(
            data_summary.file_name, date_time=(1980, 1, 1, 0, 0, 0)
        )
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o600 << 16
        digest = hashlib.sha256()
        size = 0
        data_source.seek(0)
        with archive.open(info, "w") as output:
            while chunk := data_source.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size != data_summary.size_bytes or digest.hexdigest() != data_summary.sha256:
            raise WorkerFailure("EXPORT_CHECKSUM_MISMATCH", retryable=True)
        _zip_entry(archive, "manifest.json", json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"))
    size = destination.tell()
    destination.seek(0)
    digest = hashlib.sha256(destination.read()).hexdigest()
    destination.seek(0)
    return FormatSummary(
        document_count=data_summary.document_count,
        row_count=data_summary.row_count,
        size_bytes=size,
        sha256=digest,
        file_name=async_zip_name(export_id, generated_at),
        content_type="application/zip",
    )


def write_async_zip(destination: BinaryIO, export_id: UUID, generated_at: datetime,
                    format_name: ExportFormat, data: bytes,
                    data_summary: FormatSummary) -> FormatSummary:
    """Compatibility wrapper for tests and bounded in-memory callers."""
    return write_async_zip_stream(
        destination, export_id, generated_at, format_name, io.BytesIO(data), data_summary
    )


__all__ = [
    "CONTENT_TYPES", "FormatSummary", "HEADERS", "SCHEMA_VERSION",
    "async_zip_name", "export_file_name", "write_async_zip",
    "write_async_zip_stream", "write_export",
]


