"""The PDF engine seam.

Everything library-specific lives behind this Protocol, and library exceptions
are translated into the application taxonomy inside the implementing module -
one seam, so replacing the PDF library is a single-module change and the rest
of the application never imports it directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MergeStats:
    """Per-input page counts, in input order."""

    pages_per_input: tuple[int, ...]

    @property
    def pages_total(self) -> int:
        return sum(self.pages_per_input)


@dataclass(frozen=True, slots=True)
class Attachment:
    """One embedded file as stored in the PDF.

    ``name`` is UNTRUSTED input straight from the document - it may contain
    path separators, control characters, or be empty, and names are not
    unique. Callers must sanitize before touching a filesystem.
    """

    name: str
    data: bytes


class PdfEngine(Protocol):
    def merge(self, inputs: Sequence[Path], destination: Path) -> MergeStats:
        """Merge ``inputs`` (in order) into a PDF written at ``destination``.

        ``destination`` is a temp path provided by the atomic-write layer.
        Raises InvalidPdfError for inputs the library cannot parse.
        """
        ...

    def list_attachments(self, source: Path) -> list[Attachment]:
        """Embedded files of ``source``, in the document's name-tree order
        (deterministic across runs). Duplicate names are preserved.

        Raises InvalidPdfError for files the library cannot parse.
        """
        ...


def get_engine() -> PdfEngine:
    """The single swap point for the PDF library backing the operations."""
    from pdf_ops.engine_pypdf import PypdfEngine

    return PypdfEngine()
