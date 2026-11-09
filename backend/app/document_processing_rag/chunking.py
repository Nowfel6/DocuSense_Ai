"""Deterministic structure-aware chunking over the canonical document contract."""
from __future__ import annotations

import hashlib
import json
from typing import Protocol
from uuid import UUID, uuid5

from .errors import ProcessingError
from .schemas import (
    BoundingBox, CanonicalDocument, CanonicalElement, ChunkDraft, ChunkType,
    StructuredTable, TableRow,
)


class Tokenizer(Protocol):
    def encode(self, text: str) -> tuple[str, ...]:
        """Use the exact configured model tokenizer and return stable token strings."""
        ...

    def decode(self, tokens: tuple[str, ...]) -> str:
        """Reconstruct a stable human-readable segment."""
        ...


def _groups(tokens: tuple[str, ...], size: int, overlap: int = 0) -> tuple[tuple[str, ...], ...]:
    if not tokens:
        return ()
    result: list[tuple[str, ...]] = []
    start = 0
    while start < len(tokens):
        result.append(tokens[start:start + size])
        if start + size >= len(tokens):
            break
        start += size - overlap
    return tuple(result)


def _table_text(headers: tuple[str, ...], rows: tuple[TableRow, ...]) -> str:
    lines = ["\t".join(headers)] if headers else []
    for row in rows:
        cells = sorted(row.cells, key=lambda cell: (cell.column, cell.row_span, cell.column_span))
        lines.append("\t".join(cell.text for cell in cells))
    return "\n".join(lines).strip()


class ChunkingService:
    def __init__(self, tokenizer: Tokenizer, child_tokens: int = 450,
                 parent_tokens: int = 1800, overlap_tokens: int = 50) -> None:
        if not (0 <= overlap_tokens < child_tokens <= parent_tokens):
            raise ValueError("Invalid chunk token limits")
        self.tokenizer = tokenizer
        self.child_tokens = child_tokens
        self.parent_tokens = parent_tokens
        self.overlap_tokens = overlap_tokens

    def build(self, document: CanonicalDocument) -> tuple[ChunkDraft, ...]:
        chunks: list[ChunkDraft] = []
        for page in document.pages:
            for element in page.elements:
                if element.element_type == "table":
                    self._table_chunks(document.document_id, document.pipeline_version, element, chunks)
                else:
                    self._text_chunks(document.document_id, document.pipeline_version, element, chunks)
        if not chunks:
            raise ProcessingError("CHUNKING_FAILED")
        return tuple(chunks)

    def _make(
        self, document_id: UUID, pipeline_version: str, ordinal: int, raw: str,
        token_count: int, element: CanonicalElement, role: str,
        parent_id: UUID | None = None, structured: StructuredTable | None = None,
    ) -> ChunkDraft:
        kind: ChunkType = {
            "heading": "header", "paragraph": "text", "list": "list",
            "table": "table", "image": "image", "header": "header",
            "footer": "text", "unknown": "unknown",
        }[element.element_type]  # type: ignore[assignment]
        structure_json = "" if structured is None else json.dumps(
            structured.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(f"{pipeline_version}\0{raw}\0{structure_json}".encode("utf-8")).hexdigest()
        chunk_id = uuid5(document_id, f"{pipeline_version}:{ordinal}:{digest}")
        boxes: tuple[BoundingBox, ...] = () if element.bounding_box is None else (element.bounding_box,)
        return ChunkDraft(
            chunk_id=chunk_id, parent_chunk_id=parent_id, ordinal=ordinal,
            page_start=element.page_number, page_end=element.page_number,
            section=element.section, chunk_type=kind, retrieval_role=role,
            raw_content=raw, structured_content=structured, summary=None,
            token_count=token_count, source_element_ids=(element.source_id,),
            bounding_boxes=boxes, content_hash=digest,
        )

    def _text_chunks(self, document_id: UUID, pipeline_version: str,
                     element: CanonicalElement, output: list[ChunkDraft]) -> None:
        tokens = self.tokenizer.encode(element.text.strip())
        if not tokens:
            return
        if len(tokens) <= self.child_tokens:
            output.append(self._make(document_id, pipeline_version, len(output),
                                     self.tokenizer.decode(tokens), len(tokens), element, "both"))
            return
        for parent_tokens in _groups(tokens, self.parent_tokens):
            parent_ordinal = len(output)
            parent = self._make(document_id, pipeline_version, parent_ordinal,
                                self.tokenizer.decode(parent_tokens), len(parent_tokens), element, "parent")
            output.append(parent)
            for child_tokens in _groups(parent_tokens, self.child_tokens, self.overlap_tokens):
                output.append(self._make(document_id, pipeline_version, len(output),
                                         self.tokenizer.decode(child_tokens), len(child_tokens),
                                         element, "child", parent.chunk_id))

    def _table_chunks(self, document_id: UUID, pipeline_version: str,
                      element: CanonicalElement, output: list[ChunkDraft]) -> None:
        table = element.table
        if table is None:
            raise ProcessingError("CHUNKING_FAILED")
        # Docling occasionally emits a table element with zero headers and zero
        # rows (e.g. a layout region flagged as a table but never populated).
        # We must not abort the whole pipeline for that: fall back to text
        # chunking using whatever raw text the layout model captured, and if
        # even that is blank, skip the element silently.
        if not table.headers and not table.rows:
            text = element.text.strip()
            if text:
                self._text_chunks(document_id, pipeline_version, element, output)
            return
        row_groups = self._table_row_groups(table, self.parent_tokens)
        for parent_rows in row_groups:
            parent_table = StructuredTable(headers=table.headers, rows=parent_rows)
            parent_text = _table_text(table.headers, parent_rows)
            parent_count = len(self.tokenizer.encode(parent_text))
            if not parent_text or parent_count > self.parent_tokens:
                raise ProcessingError("CHUNKING_FAILED")
            parent = self._make(document_id, pipeline_version, len(output), parent_text,
                                parent_count, element, "parent", structured=parent_table)
            output.append(parent)
            for child_rows in self._table_row_groups(parent_table, self.child_tokens):
                child_table = StructuredTable(headers=table.headers, rows=child_rows)
                child_text = _table_text(table.headers, child_rows)
                child_count = len(self.tokenizer.encode(child_text))
                if not child_text or child_count > self.child_tokens:
                    raise ProcessingError("CHUNKING_FAILED")
                output.append(self._make(document_id, pipeline_version, len(output), child_text,
                                         child_count, element, "child", parent.chunk_id, child_table))

    def _table_row_groups(self, table: StructuredTable, limit: int) -> tuple[tuple[TableRow, ...], ...]:
        header_count = len(self.tokenizer.encode("\t".join(table.headers)))
        groups: list[tuple[TableRow, ...]] = []
        current: list[TableRow] = []
        current_count = header_count
        for row in table.rows:
            row_count = len(self.tokenizer.encode(_table_text((), (row,))))
            if header_count + row_count > limit:
                raise ProcessingError("CHUNKING_FAILED")
            if current and current_count + row_count > limit:
                groups.append(tuple(current))
                current = []
                current_count = header_count
            current.append(row)
            current_count += row_count
        if current:
            groups.append(tuple(current))
        if not groups:
            raise ProcessingError("CHUNKING_FAILED")
        return tuple(groups)
