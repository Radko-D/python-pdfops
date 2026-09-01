"""Shared fixtures: the invariant-checking app runner and PDF fixture factories.

Fixture files are generated programmatically - no binaries in the repo - so
each test states exactly what property its file has, and fixtures never drift
from the library version.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfWriter

from pdf_ops.main import run

TERMINAL_EVENTS = {"operation_complete", "operation_failed"}

RunApp = Callable[[dict[str, str]], tuple[int, list[dict[str, Any]]]]


@pytest.fixture
def run_app(capsys: pytest.CaptureFixture[str]) -> RunApp:
    """Run the app in-process and enforce the cross-cutting contract invariants:

    stderr stays empty, every stdout line is valid JSON, and exactly one
    terminal event is emitted - as the last line.
    """

    def _run(env: dict[str, str]) -> tuple[int, list[dict[str, Any]]]:
        code = run(env)
        captured = capsys.readouterr()
        assert captured.err == "", f"stderr must stay empty, got: {captured.err!r}"
        events = [json.loads(line) for line in captured.out.strip().splitlines()]
        terminal = [e for e in events if e["event"] in TERMINAL_EVENTS]
        assert len(terminal) == 1, f"expected exactly one terminal event, got {terminal}"
        assert events[-1] is terminal[0], "the terminal event must be the last line"
        return code, events

    return _run


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    """A valid PDF with ``pages`` blank pages of ``page_width`` points.

    Distinct page widths let tests verify merge ordering by inspecting the
    mediabox of each page in the merged output.
    """

    def _make(name: str = "doc.pdf", pages: int = 1, page_width: float = 200.0) -> Path:
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=page_width, height=300.0)
        path = tmp_path / name
        with path.open("wb") as handle:
            writer.write(handle)
        return path

    return _make


@pytest.fixture
def make_non_pdf(tmp_path: Path) -> Callable[..., Path]:
    """A file that is not a PDF at all (regardless of its extension)."""

    def _make(name: str = "fake.pdf", content: bytes = b"plain text, not a pdf\n") -> Path:
        path = tmp_path / name
        path.write_bytes(content)
        return path

    return _make


@pytest.fixture
def make_corrupt_pdf(make_pdf: Callable[..., Path], tmp_path: Path) -> Callable[..., Path]:
    """A file with a valid ``%PDF-`` header that fails to parse.

    ``truncate`` cuts the file in half (destroys xref + EOF marker);
    ``mangle-xref`` corrupts the cross-reference section in place.
    """

    def _make(name: str = "corrupt.pdf", mode: str = "truncate") -> Path:
        source = make_pdf(name=f"pristine-{name}", pages=2)
        data = source.read_bytes()
        if mode == "truncate":
            data = data[: len(data) // 2]
        elif mode == "mangle-xref":
            data = data.replace(b"xref", b"xrfx", 1)
        else:  # pragma: no cover - guard against typos in tests
            raise ValueError(f"unknown corruption mode: {mode}")
        path = tmp_path / name
        path.write_bytes(data)
        return path

    return _make


def _build_raw_pdf(objects: list[str | bytes]) -> bytes:
    """Minimal hand-assembled PDF with a correct xref - for structural cases
    the writer API refuses to produce (dangling references, missing /Pages,
    raw name-tree bytes)."""
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        body_bytes = body if isinstance(body, bytes) else body.encode()
        out += f"{number} 0 obj\n".encode() + body_bytes + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


@pytest.fixture
def make_encrypted_pdf(tmp_path: Path) -> Callable[..., Path]:
    """An encrypted one-page PDF.

    Default: RC4 with a user password. ``algorithm="AES-256"`` for the modern
    scheme; ``user_password=""`` with an ``owner_password`` builds the common
    permissions-locked file that every viewer opens without a prompt.
    """

    def _make(
        name: str = "locked.pdf",
        password: str = "secret",
        owner_password: str | None = None,
        algorithm: str | None = None,
    ) -> Path:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        if algorithm is not None:
            writer.encrypt(
                user_password=password, owner_password=owner_password, algorithm=algorithm
            )
        else:
            writer.encrypt(user_password=password, owner_password=owner_password)
        path = tmp_path / name
        with path.open("wb") as handle:
            writer.write(handle)
        return path

    return _make


@pytest.fixture
def make_dangling_ref_pdf(tmp_path: Path) -> Callable[..., Path]:
    """A parseable PDF whose page /Contents points at a missing object -
    pypdf merges it successfully but logs a recoverable-corruption warning."""

    def _make(name: str = "dangling.pdf") -> Path:
        path = tmp_path / name
        path.write_bytes(
            _build_raw_pdf(
                [
                    "<< /Type /Catalog /Pages 2 0 R >>",
                    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Contents 9 0 R >>",
                ]
            )
        )
        return path

    return _make


@pytest.fixture
def make_pathological_pdf(tmp_path: Path) -> Callable[..., Path]:
    """Valid header and xref, but a catalog with no /Pages - pypdf raises a
    builtin AttributeError instead of its own exception type."""

    def _make(name: str = "pathological.pdf") -> Path:
        path = tmp_path / name
        path.write_bytes(_build_raw_pdf(["<< /Type /Catalog >>"]))
        return path

    return _make


@pytest.fixture
def make_pdf_with_attachments(tmp_path: Path) -> Callable[..., Path]:
    """A one-page PDF carrying the given embedded files.

    pypdf writes names verbatim into the name tree, so hostile names
    (traversal, separators, empty) and duplicates survive the roundtrip -
    exactly what the sanitizer tests need. Extraction order is the PDF
    name-tree order (sorted by name), not insertion order.
    """

    def _make(attachments: list[tuple[str, bytes]], name: str = "carrier.pdf") -> Path:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        for attachment_name, data in attachments:
            writer.add_attachment(attachment_name, data)
        path = tmp_path / name
        with path.open("wb") as handle:
            writer.write(handle)
        return path

    return _make


@pytest.fixture
def make_raw_attachment_pdf(tmp_path: Path) -> Callable[..., Path]:
    """An attachment built directly in the /Names/EmbeddedFiles tree, with the
    name given as a raw PDF string literal - reaches name shapes (UTF-16,
    non-UTF-8 bytes) and stream filters the writer API can't produce."""

    def _make(
        name_literal: bytes,
        stream: bytes = b"payload",
        filter_entry: bytes = b"",
        name: str = "raw-carrier.pdf",
    ) -> Path:
        length = str(len(stream)).encode()
        filter_part = (b" /Filter " + filter_entry) if filter_entry else b""
        path = tmp_path / name
        path.write_bytes(
            _build_raw_pdf(
                [
                    b"<< /Type /Catalog /Pages 2 0 R /Names << /EmbeddedFiles "
                    b"<< /Names [ " + name_literal + b" 4 0 R ] >> >> >>",
                    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] >>",
                    b"<< /Type /Filespec /F " + name_literal + b" /EF << /F 5 0 R >> >>",
                    b"<< /Length "
                    + length
                    + filter_part
                    + b" >>\nstream\n"
                    + stream
                    + b"\nendstream",
                ]
            )
        )
        return path

    return _make
