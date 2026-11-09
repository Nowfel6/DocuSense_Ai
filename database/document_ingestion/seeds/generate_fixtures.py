"""Create small synthetic database-only fixtures; never touches a database.

Existing different bytes are refused. Committed fixtures, not a regenerated
image from a different encoder version, are the canonical checksummed input.
"""
import hashlib
import io
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent / "document-ingestion-fixtures"


def pdf(label: str) -> bytes:
    stream = f"BT /F1 12 Tf 30 100 Td ({label}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 150] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    return bytes(data)


def image_bytes(kind: str, color: tuple[int, int, int]) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(output, format=kind)
    return output.getvalue()


def write_new_or_equal(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Refusing to overwrite changed fixture: {path.name}")
        return
    path.write_bytes(data)


def generate() -> None:
    fixtures = [
        ("F1", "synthetic-invoice.pdf", "application/pdf", pdf("SYNTHETIC DATABASE INVOICE F1")),
        ("F2", "synthetic-order.png", "image/png", image_bytes("PNG", (32, 96, 160))),
        ("F3", "synthetic-packing.jpg", "image/jpeg", image_bytes("JPEG", (160, 96, 32))),
        ("F4", "synthetic-failed.pdf", "application/pdf", pdf("SYNTHETIC DATABASE FAILURE F4")),
    ]
    manifest = {"scope": "DATABASE_ONLY", "version": 1, "files": []}
    ROOT.mkdir(exist_ok=True)
    for key, name, mime, data in fixtures:
        write_new_or_equal(ROOT / name, data)
        manifest["files"].append({
            "key": key, "path": name, "mime_type": mime,
            "file_size_bytes": len(data), "file_hash": hashlib.sha256(data).hexdigest(),
        })
    write_new_or_equal(ROOT / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    print("Four synthetic assets and their checksum manifest are consistent.")


if __name__ == "__main__":
    generate()
