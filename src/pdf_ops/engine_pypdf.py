"""pypdf-backed engine implementation.

The only module that imports pypdf. Translates pypdf's failure modes into the
application taxonomy so callers never see library-specific errors.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pypdf import PdfReader, PdfWriter
from pypdf.errors import DependencyError, PyPdfError

from pdf_ops.engine import Attachment, MergeStats
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

# Raised while decoding streams whose filter pypdf does not implement
# (NotImplementedError, e.g. an unknown /Filter) or needs an unavailable
# external capability for (DependencyError, e.g. jbig2dec). Permanent,
# data-dependent conditions - never internal errors.
_UNSUPPORTED_FEATURES = (DependencyError, NotImplementedError)


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
            except _UNSUPPORTED_FEATURES as err:
                raise _unsupported(path, err) from err
            except _PARSE_FAILURES as err:
                raise _corrupt(path, err) from err

        with destination.open("wb") as handle:
            writer.write(handle)
        return MergeStats(pages_per_input=tuple(pages_per_input))

    def list_attachments(self, source: Path) -> list[Attachment]:
        reader = _open_reader(source)
        try:
            # attachment_list walks the document-level /Names/EmbeddedFiles
            # tree in name order and preserves duplicate names.
            items = list(reader.attachment_list)
        except _UNSUPPORTED_FEATURES as err:
            raise _unsupported(source, err) from err
        except _PARSE_FAILURES as err:
            raise _corrupt(source, err) from err

        attachments: list[Attachment] = []
        for item in items:
            try:
                # pypdf annotates name as str, but raw name trees can yield
                # byte strings at runtime - keep the defensive type.
                raw_name = cast("str | bytes", item.name)
                content = item.content
            except _UNSUPPORTED_FEATURES as err:
                raise _unsupported(source, err) from err
            except _PARSE_FAILURES as err:
                raise _corrupt(source, err) from err
            # Spec-legal name trees can carry non-UTF-8 byte strings; the
            # sanitizer downstream expects str, so decode lossily rather than
            # letting one odd entry abort the run.
            name = (
                raw_name
                if isinstance(raw_name, str)
                else bytes(raw_name).decode("utf-8", errors="replace")
            )
            attachments.append(Attachment(name=name, data=bytes(content)))
        return attachments


def _open_reader(path: Path) -> PdfReader:
    try:
        reader = PdfReader(path)
    except DependencyError as err:
        # At construction time this means auto-decryption of an AES-encrypted
        # file needed the cryptography backend this build does not ship.
        raise PasswordError(
            f"{path} uses encryption this build cannot process",
            error_code="UNSUPPORTED_ENCRYPTION",
            context={"input": str(path)},
        ) from err
    except NotImplementedError as err:
        raise _unsupported(path, err) from err
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
    except _UNSUPPORTED_FEATURES as err:
        raise _unsupported(path, err) from err
    except _PARSE_FAILURES as err:
        raise _corrupt(path, err) from err
    return reader


def _corrupt(path: Path, err: Exception) -> InvalidPdfError:
    return InvalidPdfError(
        f"cannot parse {path} as a PDF: {err}",
        error_code="CORRUPT_PDF",
        context={"input": str(path)},
    )


def _unsupported(path: Path, err: Exception) -> InvalidPdfError:
    return InvalidPdfError(
        f"{path} uses a PDF feature this build cannot process: {err}",
        error_code="UNSUPPORTED_PDF_FEATURE",
        context={"input": str(path)},
    )
