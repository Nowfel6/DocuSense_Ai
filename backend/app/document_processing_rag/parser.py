"""Parser boundary and deterministic OCR policy; no parser SDK is selected here."""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .schemas import CanonicalDocument


@dataclass(frozen=True)
class PageSignals:
    usable_alphanumeric_characters: int
    raster_coverage: float
    replacement_or_control_characters: int
    extracted_characters: int
    has_meaningful_raster: bool

    def __post_init__(self) -> None:
        if self.usable_alphanumeric_characters < 0 or self.replacement_or_control_characters < 0 or self.extracted_characters < 0:
            raise ValueError("Character counts cannot be negative")
        if not 0 <= self.raster_coverage <= 1:
            raise ValueError("Raster coverage must be between zero and one")


def should_ocr(signals: PageSignals) -> bool:
    """Apply the locked per-page OCR thresholds and skip genuinely blank pages."""
    if signals.extracted_characters == 0 and not signals.has_meaningful_raster:
        return False
    sparse_raster = signals.usable_alphanumeric_characters < 20 and signals.raster_coverage >= 0.25
    corrupt_ratio = (
        signals.extracted_characters > 0
        and signals.replacement_or_control_characters / signals.extracted_characters > 0.10
    )
    return sparse_raster or corrupt_ratio


class DocumentParser(Protocol):
    async def parse(self, document_id: UUID, source: bytes) -> CanonicalDocument:
        """Return bounded canonical data; implementations must isolate untrusted input."""
        ...
