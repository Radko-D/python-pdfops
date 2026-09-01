"""End-to-end extract runs through run(env): the extract operator contract.

Attachment names are untrusted input; several tests here are security tests
in disguise - nothing an attachment says may place a file outside
PDFOPS_OUTPUT_DIR.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

import pdf_ops.extract
from tests.conftest import RunApp

pytestmark = pytest.mark.integration


def extract_env(source: Path, output_dir: Path, **extra: str) -> dict[str, str]:
    return {
        "PDFOPS_OPERATION": "extract",
        "PDFOPS_INPUT": str(source),
        "PDFOPS_OUTPUT_DIR": str(output_dir),
        **extra,
    }


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    path = tmp_path / "out"
    path.mkdir()
    return path


class TestExtractSuccess:
    def test_attachments_extracted_with_contents(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        carrier = make_pdf_with_attachments([("data.csv", b"a,b\n1,2\n"), ("notes.txt", b"hello")])
        code, events = run_app(extract_env(carrier, out_dir))

        assert code == 0
        terminal = events[-1]
        assert terminal["event"] == "operation_complete"
        assert terminal["attachments_extracted"] == 2
        assert terminal["bytes_written"] == len(b"a,b\n1,2\n") + len(b"hello")
        assert (out_dir / "data.csv").read_bytes() == b"a,b\n1,2\n"
        assert (out_dir / "notes.txt").read_bytes() == b"hello"
        assert sorted(p.name for p in out_dir.iterdir()) == ["data.csv", "notes.txt"]

        extracted_events = [e for e in events if e["event"] == "attachment_extracted"]
        assert [e["attachment"] for e in extracted_events] == ["data.csv", "notes.txt"]
        assert [e["bytes"] for e in extracted_events] == [8, 5]

    def test_duplicate_names_get_deterministic_suffixes(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        # The PDF name tree permits repeated names; extraction preserves every
        # payload under a deterministic, collision-suffixed filename.
        carrier = make_pdf_with_attachments(
            [("report.txt", b"one"), ("report.txt", b"two"), ("report.txt", b"three")]
        )
        code, _ = run_app(extract_env(carrier, out_dir))
        assert code == 0
        assert (out_dir / "report.txt").read_bytes() == b"one"
        assert (out_dir / "report-1.txt").read_bytes() == b"two"
        assert (out_dir / "report-2.txt").read_bytes() == b"three"

    def test_zero_attachments_is_success_with_count(
        self, make_pdf: Callable[..., Path], out_dir: Path, run_app: RunApp
    ) -> None:
        plain = make_pdf()
        code, events = run_app(extract_env(plain, out_dir))
        assert code == 0
        assert events[-1]["attachments_extracted"] == 0
        assert list(out_dir.iterdir()) == []

    def test_strict_flag_turns_zero_attachments_into_failure(
        self, make_pdf: Callable[..., Path], out_dir: Path, run_app: RunApp
    ) -> None:
        plain = make_pdf()
        env = extract_env(plain, out_dir, PDFOPS_FAIL_ON_NO_ATTACHMENTS="true")
        code, events = run_app(env)
        assert code == 3
        assert events[-1]["error_code"] == "NO_ATTACHMENTS"


class TestNameSecurity:
    def test_traversal_names_cannot_escape_the_output_dir(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        tmp_path: Path,
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        carrier = make_pdf_with_attachments(
            [("../../evil.txt", b"traverse"), ("/etc/passwd", b"abs"), ("a\\b.txt", b"win")]
        )
        code, _ = run_app(extract_env(carrier, out_dir))

        assert code == 0
        # everything landed INSIDE the output dir, under basenames only
        assert sorted(p.name for p in out_dir.iterdir()) == ["b.txt", "evil.txt", "passwd"]
        # and the traversal target outside the output dir does not exist
        assert not (tmp_path / "evil.txt").exists()
        assert not (out_dir.parent / "evil.txt").exists()

    def test_empty_name_falls_back_deterministically(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        carrier = make_pdf_with_attachments([("", b"anonymous")])
        code, events = run_app(extract_env(carrier, out_dir))
        assert code == 0
        assert (out_dir / "attachment_0").read_bytes() == b"anonymous"
        extracted = [e for e in events if e["event"] == "attachment_extracted"]
        assert extracted[0]["original_name"] == ""

    def test_original_name_logged_when_sanitization_changed_it(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        carrier = make_pdf_with_attachments([("../../evil.txt", b"x")])
        code, events = run_app(extract_env(carrier, out_dir))
        assert code == 0
        extracted = [e for e in events if e["event"] == "attachment_extracted"]
        assert extracted[0]["attachment"] == "evil.txt"
        assert extracted[0]["original_name"] == "../../evil.txt"


class TestExtractFailures:
    def test_missing_input_exits_3(self, tmp_path: Path, out_dir: Path, run_app: RunApp) -> None:
        code, events = run_app(extract_env(tmp_path / "nope.pdf", out_dir))
        assert code == 3
        assert events[-1]["error_code"] == "INPUT_MISSING"

    def test_non_pdf_exits_4(
        self, make_non_pdf: Callable[..., Path], out_dir: Path, run_app: RunApp
    ) -> None:
        code, events = run_app(extract_env(make_non_pdf(), out_dir))
        assert code == 4
        assert events[-1]["error_code"] == "NOT_A_PDF"

    def test_corrupt_pdf_exits_4(
        self, make_corrupt_pdf: Callable[..., Path], out_dir: Path, run_app: RunApp
    ) -> None:
        code, events = run_app(extract_env(make_corrupt_pdf(), out_dir))
        assert code == 4
        assert events[-1]["error_code"] == "CORRUPT_PDF"

    def test_encrypted_input_exits_5(
        self, make_encrypted_pdf: Callable[..., Path], out_dir: Path, run_app: RunApp
    ) -> None:
        code, events = run_app(extract_env(make_encrypted_pdf(), out_dir))
        assert code == 5
        assert events[-1]["error_code"] == "PASSWORD_REQUIRED"

    def test_missing_output_dir_exits_6(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        tmp_path: Path,
        run_app: RunApp,
    ) -> None:
        carrier = make_pdf_with_attachments([("a.txt", b"x")])
        code, events = run_app(extract_env(carrier, tmp_path / "no-such-dir"))
        assert code == 6
        assert events[-1]["error_code"] == "OUTPUT_DIR_MISSING"

    def test_existing_file_conflict_writes_nothing(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        # All-or-nothing: one conflicting name refuses the whole run before
        # any file is written, so a retry can't mix old and new content.
        carrier = make_pdf_with_attachments([("fresh.txt", b"new"), ("taken.txt", b"new")])
        (out_dir / "taken.txt").write_bytes(b"pre-existing")

        code, events = run_app(extract_env(carrier, out_dir))

        assert code == 6
        terminal = events[-1]
        assert terminal["error_code"] == "OUTPUT_EXISTS"
        assert terminal["context"]["conflicts"] == ["taken.txt"]
        assert (out_dir / "taken.txt").read_bytes() == b"pre-existing"
        assert not (out_dir / "fresh.txt").exists(), "nothing may be written on conflict"

    def test_preexisting_symlink_counts_as_conflict(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        tmp_path: Path,
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        carrier = make_pdf_with_attachments([("linked.txt", b"payload")])
        (out_dir / "linked.txt").symlink_to(tmp_path / "elsewhere.txt")  # dangling

        code, events = run_app(extract_env(carrier, out_dir))

        assert code == 6
        assert events[-1]["error_code"] == "OUTPUT_EXISTS"
        assert not (tmp_path / "elsewhere.txt").exists()


class TestDeterminism:
    def test_extraction_order_is_name_tree_order_and_stable(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        tmp_path: Path,
        run_app: RunApp,
    ) -> None:
        # Insertion order deliberately differs from name order; the name tree
        # (sorted) is the extraction order, identical on every run.
        carrier = make_pdf_with_attachments(
            [("zebra.txt", b"zzz"), ("alpha.txt", b"aaa"), ("mid.txt", b"mmm")]
        )
        sequences: list[list[str]] = []
        for run_number in (1, 2):
            out = tmp_path / f"run-{run_number}"
            out.mkdir()
            code, events = run_app(extract_env(carrier, out))
            assert code == 0
            sequences.append(
                [e["attachment"] for e in events if e["event"] == "attachment_extracted"]
            )
            assert (out / "alpha.txt").read_bytes() == b"aaa"
            assert (out / "zebra.txt").read_bytes() == b"zzz"
        assert sequences[0] == ["alpha.txt", "mid.txt", "zebra.txt"]
        assert sequences[0] == sequences[1]

    def test_case_only_collision_suffixed_on_any_filesystem(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        # A case-insensitive output volume (macOS, SMB) would fold these into
        # one file; casefolded dedupe keeps both payloads everywhere.
        carrier = make_pdf_with_attachments([("Report.txt", b"UPPER"), ("report.txt", b"lower")])
        code, events = run_app(extract_env(carrier, out_dir))
        assert code == 0
        assert events[-1]["attachments_extracted"] == 2
        assert (out_dir / "Report.txt").read_bytes() == b"UPPER"
        assert (out_dir / "report-1.txt").read_bytes() == b"lower"

    def test_conflict_check_covers_deduped_names(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        # The suffixed name is a real target: a pre-existing file there must
        # refuse the run exactly like a direct name conflict.
        carrier = make_pdf_with_attachments([("report.txt", b"one"), ("report.txt", b"two")])
        (out_dir / "report-1.txt").write_bytes(b"sentinel")

        code, events = run_app(extract_env(carrier, out_dir))

        assert code == 6
        assert events[-1]["error_code"] == "OUTPUT_EXISTS"
        assert events[-1]["context"]["conflicts"] == ["report-1.txt"]
        assert not (out_dir / "report.txt").exists(), "nothing may be written on conflict"
        assert (out_dir / "report-1.txt").read_bytes() == b"sentinel"


class TestRawNameTreeShapes:
    def test_utf16_traversal_name_stays_contained(
        self,
        make_raw_attachment_pdf: Callable[..., Path],
        tmp_path: Path,
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        utf16_hex = "../../sneak.txt".encode("utf-16-be").hex().upper().encode()
        carrier = make_raw_attachment_pdf(b"<FEFF" + utf16_hex + b">")
        code, _ = run_app(extract_env(carrier, out_dir))
        assert code == 0
        assert sorted(p.name for p in out_dir.iterdir()) == ["sneak.txt"]
        assert not (tmp_path / "sneak.txt").exists()

    def test_non_utf8_name_bytes_extract_inside_output_dir(
        self,
        make_raw_attachment_pdf: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        carrier = make_raw_attachment_pdf(b"(bad\xffname.txt)")
        code, events = run_app(extract_env(carrier, out_dir))
        assert code == 0
        assert events[-1]["attachments_extracted"] == 1
        files = list(out_dir.iterdir())
        assert len(files) == 1
        assert files[0].read_bytes() == b"payload"

    def test_unknown_stream_filter_is_unprocessable_not_internal(
        self,
        make_raw_attachment_pdf: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        # pypdf raises NotImplementedError for a filter it doesn't implement;
        # that must classify as a data problem (exit 4), never exit 1.
        carrier = make_raw_attachment_pdf(b"(ok.txt)", filter_entry=b"/FooBar")
        code, events = run_app(extract_env(carrier, out_dir))
        assert code == 4
        assert events[-1]["error_code"] == "UNSUPPORTED_PDF_FEATURE"
        assert list(out_dir.iterdir()) == []


class TestInvariants:
    def test_containment_recheck_refuses_a_broken_sanitizer(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        # Defense in depth: if the sanitizer ever regressed to pass a
        # traversal name through, the write loop must refuse (exit 1) rather
        # than write outside the output dir.
        def broken_sanitizer(raw: str, index: int) -> str:
            return "../escaped.txt"

        monkeypatch.setattr(pdf_ops.extract, "sanitize_attachment_name", broken_sanitizer)
        carrier = make_pdf_with_attachments([("x.txt", b"x")])
        code, events = run_app(extract_env(carrier, out_dir))
        assert code == 1
        assert events[-1]["error_code"] == "UNEXPECTED_ERROR"
        assert not (tmp_path / "escaped.txt").exists()
        assert not (out_dir / ".." / "escaped.txt").resolve().exists()

    def test_zero_attachments_full_terminal_shape(
        self, make_pdf: Callable[..., Path], out_dir: Path, run_app: RunApp
    ) -> None:
        code, events = run_app(extract_env(make_pdf(), out_dir))
        assert code == 0
        assert events[-1]["bytes_written"] == 0
        assert events[-1]["attachments_extracted"] == 0

    def test_unchanged_name_logs_null_original(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        carrier = make_pdf_with_attachments([("plain.txt", b"x")])
        code, events = run_app(extract_env(carrier, out_dir))
        assert code == 0
        extracted = [e for e in events if e["event"] == "attachment_extracted"]
        assert extracted[0]["original_name"] is None

    def test_terminal_event_survives_error_level_on_real_extract(
        self,
        make_pdf_with_attachments: Callable[..., Path],
        out_dir: Path,
        run_app: RunApp,
    ) -> None:
        carrier = make_pdf_with_attachments([("a.txt", b"x")])
        env = extract_env(carrier, out_dir, PDFOPS_LOG_LEVEL="error")
        code, events = run_app(env)
        assert code == 0
        assert [e["event"] for e in events] == ["operation_complete"]
        assert events[-1]["attachments_extracted"] == 1
