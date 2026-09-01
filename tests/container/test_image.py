"""Container-contract tests: build the image and assert what an operator sees.

Excluded from the default pytest run (see addopts); run with
``uv run pytest -m container``. Requires a Docker daemon.

Volume-mount tests place their host directories under ``/tmp`` (override with
PDFOPS_TEST_MOUNT_DIR) because Docker Desktop on macOS only shares selected
host paths, and pytest's default tmp dir is not among them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

pytestmark = [pytest.mark.container, pytest.mark.slow]

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE = "pdf-ops:test"


@pytest.fixture(scope="session")
def image() -> str:
    subprocess.run(
        ["docker", "build", "-q", "-t", IMAGE, "."],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return IMAGE


@pytest.fixture
def mount_dir() -> Iterator[Path]:
    base = os.environ.get("PDFOPS_TEST_MOUNT_DIR", "/tmp")
    path = Path(tempfile.mkdtemp(prefix="pdf-ops-test-", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def docker_run(
    image: str,
    env: dict[str, str],
    *,
    volumes: dict[Path, str] | None = None,
    entrypoint: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "run", "--rm"]
    for key, value in env.items():
        cmd += ["-e", f"{key}={value}"]
    for host, spec in (volumes or {}).items():
        cmd += ["-v", f"{host}:{spec}"]
    if entrypoint:
        cmd += ["--entrypoint", entrypoint[0], image, *entrypoint[1:]]
    else:
        cmd.append(image)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def test_invalid_config_exits_2_with_json_only_stdout(image: str) -> None:
    result = docker_run(image, {"PDFOPS_OPERATION": "bogus"})
    assert result.returncode == 2
    assert result.stderr == ""
    events = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert events[-1]["event"] == "operation_failed"
    assert events[-1]["error_code"] == "INVALID_OPERATION"


def test_golden_extract_via_mounted_volumes(image: str, mount_dir: Path) -> None:
    in_dir = mount_dir / "in"
    out_dir = mount_dir / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    out_dir.chmod(0o777)

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.add_attachment("data.csv", b"a,b\n1,2\n")
    writer.add_attachment("../../evil.txt", b"traverse")
    with (in_dir / "carrier.pdf").open("wb") as handle:
        writer.write(handle)

    result = docker_run(
        image,
        {
            "PDFOPS_OPERATION": "extract",
            "PDFOPS_INPUT": "/in/carrier.pdf",
            "PDFOPS_OUTPUT_DIR": "/out",
        },
        volumes={in_dir: "/in:ro", out_dir: "/out"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    events = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert events[-1]["event"] == "operation_complete"
    assert events[-1]["attachments_extracted"] == 2
    # sanitized names only, nothing outside the mounted output dir
    assert sorted(p.name for p in out_dir.iterdir()) == ["data.csv", "evil.txt"]
    assert (out_dir / "data.csv").read_bytes() == b"a,b\n1,2\n"
    assert not (mount_dir / "evil.txt").exists()


def test_runs_as_non_root_uid_10001(image: str) -> None:
    result = docker_run(image, {}, entrypoint=["python", "-c", "import os; print(os.getuid())"])
    assert result.returncode == 0
    assert result.stdout.strip() == "10001"


def test_golden_merge_via_mounted_volumes(image: str, mount_dir: Path) -> None:
    in_dir = mount_dir / "in"
    out_dir = mount_dir / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    # The container runs as UID 10001; the mounted output dir must be writable
    # for it (on a real cluster this is fsGroup's job).
    out_dir.chmod(0o777)

    for name, pages in (("a.pdf", 1), ("b.pdf", 2)):
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=200, height=300)
        with (in_dir / name).open("wb") as handle:
            writer.write(handle)

    result = docker_run(
        image,
        {
            "PDFOPS_OPERATION": "merge",
            "PDFOPS_INPUTS": "/in/a.pdf:/in/b.pdf",
            "PDFOPS_OUTPUT": "/out/merged.pdf",
        },
        volumes={in_dir: "/in:ro", out_dir: "/out"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    events = [json.loads(line) for line in result.stdout.strip().splitlines()]
    terminal = events[-1]
    assert terminal["event"] == "operation_complete"
    assert terminal["pages"] == 3

    merged = out_dir / "merged.pdf"
    assert merged.exists()
    assert len(PdfReader(merged).pages) == 3


def test_golden_encrypted_merge_with_mounted_password_file(image: str, mount_dir: Path) -> None:
    in_dir = mount_dir / "in"
    out_dir = mount_dir / "out"
    secret_dir = mount_dir / "secret"
    for directory in (in_dir, out_dir, secret_dir):
        directory.mkdir()
    out_dir.chmod(0o777)

    password = "container-test-pw"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.encrypt(user_password=password, algorithm="AES-256")
    with (in_dir / "locked.pdf").open("wb") as handle:
        writer.write(handle)
    (secret_dir / "pw").write_text(password + "\n")

    result = docker_run(
        image,
        {
            "PDFOPS_OPERATION": "merge",
            "PDFOPS_INPUTS": "/in/locked.pdf",
            "PDFOPS_OUTPUT": "/out/merged.pdf",
            "PDFOPS_PASSWORD_FILE": "/secret/pw",
            "PDFOPS_OUTPUT_ENCRYPTION": "inherit",
        },
        volumes={in_dir: "/in:ro", secret_dir: "/secret:ro", out_dir: "/out"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert password not in result.stdout
    assert password not in result.stderr
    events = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert events[-1]["output_encrypted"] is True

    reader = PdfReader(out_dir / "merged.pdf")
    assert reader.is_encrypted
    assert reader.decrypt(password) != 0
    from typing import Any, cast

    encrypt_dict = cast("Any", reader.trailer["/Encrypt"]).get_object()
    assert int(encrypt_dict["/V"]) == 5  # AES-256, not legacy RC4


def test_skip_makes_a_retry_a_no_op(image: str, mount_dir: Path) -> None:
    in_dir = mount_dir / "in"
    out_dir = mount_dir / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    out_dir.chmod(0o777)

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    with (in_dir / "a.pdf").open("wb") as handle:
        writer.write(handle)

    env = {
        "PDFOPS_OPERATION": "merge",
        "PDFOPS_INPUTS": "/in/a.pdf",
        "PDFOPS_OUTPUT": "/out/merged.pdf",
        "PDFOPS_ON_EXISTS": "skip",
    }
    volumes = {in_dir: "/in:ro", out_dir: "/out"}

    first = docker_run(image, env, volumes=volumes)
    assert first.returncode == 0, first.stdout + first.stderr
    original = (out_dir / "merged.pdf").read_bytes()

    second = docker_run(image, env, volumes=volumes)
    assert second.returncode == 0, second.stdout + second.stderr
    events = [json.loads(line) for line in second.stdout.strip().splitlines()]
    assert events[-1]["skipped"] is True
    assert (out_dir / "merged.pdf").read_bytes() == original
