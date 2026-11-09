"""Embedding provider boundary and all-or-nothing vector validation."""
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from .errors import ProcessingError
from .schemas import EmbeddedChunk

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingProvider(Protocol):
    model: str
    revision: str

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector per input without persisting partial results."""
        ...


def validate_embedding_batch(
    chunk_ids: Sequence[UUID], vectors: Sequence[Sequence[float]], model: str, revision: str
) -> tuple[EmbeddedChunk, ...]:
    if model != MODEL or not revision.strip() or revision.strip().lower() in {"main", "master", "latest", "head", "default"}:
        raise ProcessingError("EMBEDDING_CONFIGURATION_MISMATCH")
    if len(chunk_ids) != len(vectors):
        raise ProcessingError("EMBEDDING_CONFIGURATION_MISMATCH")
    try:
        return tuple(EmbeddedChunk(chunk_id=chunk_id, vector=tuple(vector), model=model, revision=revision)
                     for chunk_id, vector in zip(chunk_ids, vectors, strict=True))
    except (ValidationError, ValueError, TypeError) as exc:
        raise ProcessingError("EMBEDDING_CONFIGURATION_MISMATCH") from exc
