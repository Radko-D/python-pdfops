"""pypdf-backed engine implementation.

The only module that imports pypdf. Translates pypdf's failure modes into the
application taxonomy so callers never see library-specific errors.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import DependencyError, PyPdfError

from pdf_ops.engine import MergeStats
from pdf_ops.errors import InvalidPdfError, PasswordError

# pypdf leaks builtin exceptions (AttributeError, KeyError, ...) on some
# pathological files whose header and xref are valid - e.g. a catalog with no
# /Pages raises AttributeError deep in page-tree flattening. These catches
# wrap ONLY pypdf calls, so a builtin exception here means a file pypdf cannot
# process, not a bug in our code. OSError deliberately excluded: I/O failures
# must keep their own classification.
_PARSE_FAILURES = (
    PyPdfError,
    AttributeError,
    KeyError,
    IndexError,
    TypeError,
    ValueError,
    RecursionError,
)


class PypdfEngine:
    def merge(self, inputs: Sequence[Path], destination: Path) -> MergeStats:
        # Open (and thereby parse) every input before writing a single byte:
        # a corrupt later input must not waste work or leave partial state.
        readers: list[PdfReader] = []
        for path in inputs:
            readers.append(_open_reader(path))

        writer = PdfWriter()
        pages_per_input: list[int] = []
        for path, reader in zip(inputs, readers, strict=True):
            try:
                writer.append(reader)
                pages_per_input.append(len(reader.pages))
            except _PARSE_FAILURES as err:
                raise _corrupt(path, err) from err

        with destination.open("wb") as handle:
            writer.write(handle)
        return MergeStats(pages_per_input=tuple(pages_per_input))


def _open_reader(path: Path) -> PdfReader:
    try:
        reader = PdfReader(path)
    except DependencyError as err:
        # Raised while auto-decrypting AES-encrypted files: the required
        # cryptography backend is not part of this build.
        raise PasswordError(
            f"{path} uses encryption this build cannot process",
            error_code="UNSUPPORTED_ENCRYPTION",
            context={"input": str(path)},
        ) from err
    except _PARSE_FAILURES as err:
        raise _corrupt(path, err) from err

    if reader.is_encrypted:
        # Encrypted inputs are refused until password support lands; treating
        # them as corrupt would misdirect the operator (and retry policies).
        raise PasswordError(
            f"{path} is encrypted; password support is not implemented yet",
            error_code="PASSWORD_REQUIRED",
            context={"input": str(path)},
        )

    try:
        # Force xref/page-tree resolution now; pypdf parses lazily and would
        # otherwise surface corruption mid-write.
        _ = len(reader.pages)
    except _PARSE_FAILURES as err:
        raise _corrupt(path, err) from err
    return reader


def _corrupt(path: Path, err: Exception) -> InvalidPdfError:
    return InvalidPdfError(
        f"cannot parse {path} as a PDF: {err}",
        error_code="CORRUPT_PDF",
        context={"input": str(path)},
    )
