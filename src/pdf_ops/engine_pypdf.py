"""pypdf-backed engine implementation.

The only module that imports pypdf. Translates pypdf's failure modes into the
application taxonomy so callers never see library-specific errors, and is the
only code that calls ``Secret.reveal()``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from pypdf import PasswordType, PdfReader, PdfWriter
from pypdf.errors import DependencyError, PyPdfError

from pdf_ops.engine import Attachment, OpenedInput
from pdf_ops.errors import InvalidPdfError, PasswordError
from pdf_ops.secret import Secret

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
    def open_input(self, path: Path, password: Secret | None) -> OpenedInput:
        try:
            reader = PdfReader(path)
        except DependencyError as err:
            # At construction time this means auto-decryption needed a
            # cryptography capability this build does not ship.
            raise PasswordError(
                f"{path} uses encryption this build cannot process",
                error_code="UNSUPPORTED_ENCRYPTION",
                context={"input": str(path)},
            ) from err
        except NotImplementedError as err:
            if _mentions_encryption(path):
                # Certificate security handlers, exotic /V values, etc.: an
                # encryption problem, not a malformed file - the operator
                # remedy lives in the password class.
                raise PasswordError(
                    f"{path} uses an encryption scheme this build cannot process",
                    error_code="UNSUPPORTED_ENCRYPTION",
                    context={"input": str(path)},
                ) from err
            raise _unsupported(path, err) from err
        except _PARSE_FAILURES as err:
            raise _corrupt(path, err) from err

        encrypted = bool(reader.is_encrypted)
        algorithm: str | None = None
        password_type: str | None = None
        if encrypted:
            # The /Encrypt dictionary is plaintext: the algorithm is known
            # before any password attempt.
            algorithm = _describe_encryption(reader)
            password_type = _decrypt(reader, path, password, algorithm)

        try:
            # Force xref/page-tree resolution now; pypdf parses lazily and
            # would otherwise surface corruption mid-write.
            pages = len(reader.pages)
        except _UNSUPPORTED_FEATURES as err:
            raise _unsupported(path, err) from err
        except _PARSE_FAILURES as err:
            raise _corrupt(path, err) from err

        return OpenedInput(
            path=path,
            handle=reader,
            pages=pages,
            encrypted=encrypted,
            algorithm=algorithm,
            password_type=password_type,
        )

    def merge_to(
        self,
        inputs: Sequence[OpenedInput],
        destination: Path,
        output_password: Secret | None,
    ) -> None:
        writer = PdfWriter()
        for opened in inputs:
            reader = cast(PdfReader, opened.handle)
            try:
                writer.append(reader)
            except _UNSUPPORTED_FEATURES as err:
                raise _unsupported(opened.path, err) from err
            except _PARSE_FAILURES as err:
                raise _corrupt(opened.path, err) from err

        if output_password is not None:
            # algorithm passed explicitly: pypdf's default is legacy RC4 for
            # backwards compatibility - never acceptable for new output.
            writer.encrypt(user_password=output_password.reveal(), algorithm="AES-256")

        with destination.open("wb") as handle:
            writer.write(handle)

    def list_attachments(self, opened: OpenedInput) -> list[Attachment]:
        reader = cast(PdfReader, opened.handle)
        try:
            # attachment_list walks the document-level /Names/EmbeddedFiles
            # tree in name order and preserves duplicate names.
            items = list(reader.attachment_list)
        except _UNSUPPORTED_FEATURES as err:
            raise _unsupported(opened.path, err) from err
        except _PARSE_FAILURES as err:
            raise _corrupt(opened.path, err) from err

        attachments: list[Attachment] = []
        for item in items:
            try:
                # pypdf annotates name as str, but raw name trees can yield
                # byte strings at runtime - keep the defensive type.
                raw_name = cast("str | bytes", item.name)
                content = item.content
            except _UNSUPPORTED_FEATURES as err:
                raise _unsupported(opened.path, err) from err
            except _PARSE_FAILURES as err:
                raise _corrupt(opened.path, err) from err
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


def _decrypt(reader: PdfReader, path: Path, password: Secret | None, algorithm: str | None) -> str:
    """Decrypt with the supplied password, or the spec-standard empty try.

    Returns how the file opened: ``user``/``owner``/``empty``. pypdf's
    ``decrypt()`` reports failure through its return value, not an exception -
    the check must be explicit.
    """
    supplied = password.reveal() if password is not None else ""
    try:
        result = reader.decrypt(supplied)
    except DependencyError as err:
        raise PasswordError(
            f"{path} uses encryption this build cannot process ({algorithm})",
            error_code="UNSUPPORTED_ENCRYPTION",
            context={"input": str(path), "algorithm": algorithm},
        ) from err
    except _PARSE_FAILURES as err:
        raise _corrupt(path, err) from err

    if result == PasswordType.NOT_DECRYPTED:
        if password is None:
            raise PasswordError(
                f"{path} is encrypted ({algorithm}) and requires a password",
                error_code="PASSWORD_REQUIRED",
                context={"input": str(path), "algorithm": algorithm},
            )
        # The supplied password failed - but this input may not need it at
        # all (a permissions-locked file among user-locked ones in a merge).
        # The spec-standard empty try still applies before giving up.
        try:
            empty_result = reader.decrypt("")
        except _PARSE_FAILURES as err:
            raise _corrupt(path, err) from err
        if empty_result != PasswordType.NOT_DECRYPTED:
            return "empty"
        raise PasswordError(
            f"the supplied password does not open {path} ({algorithm})",
            error_code="WRONG_PASSWORD",
            context={"input": str(path), "algorithm": algorithm},
        )
    if not supplied:
        return "empty"
    return "owner" if result == PasswordType.OWNER_PASSWORD else "user"


def _describe_encryption(reader: PdfReader) -> str:
    """Best-effort human label for the /Encrypt dictionary (plaintext
    metadata - readable before any password attempt)."""
    try:
        encrypt_obj: Any = reader.trailer.get("/Encrypt")
        if encrypt_obj is None:
            return "unknown"
        encrypt: Any = encrypt_obj.get_object()
        version = int(encrypt.get("/V", 0))
        length = int(encrypt.get("/Length", 40))
        if version == 5:
            return "AES-256"
        if version == 4:
            crypt_filters: Any = encrypt.get("/CF")
            if crypt_filters is not None and "/AESV2" in str(crypt_filters):
                return "AES-128"
            return f"RC4-{length}"
        if version == 2:
            return f"RC4-{length}"
        if version == 1:
            return "RC4-40"
        return f"V{version}"
    except Exception:
        return "unknown"


def _mentions_encryption(path: Path) -> bool:
    """Best-effort check whether a file that pypdf refused to construct a
    reader for carries an /Encrypt dictionary (it lives near the trailer)."""
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - 8192))
            return b"/Encrypt" in handle.read()
    except OSError:
        return False


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
