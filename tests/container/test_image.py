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


def test_unimplemented_operation_exits_1(image: str) -> None:
    result = docker_run(image, {"PDFOPS_OPERATION": "extract"})
    assert result.returncode == 1  # extract is not implemented yet
    events = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert [e["event"] for e in events] == [
        "config_loaded",
        "operation_started",
        "operation_failed",
    ]


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
