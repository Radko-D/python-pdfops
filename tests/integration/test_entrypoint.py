"""The ``python -m pdf_ops`` entrypoint glue, exercised as a real subprocess.

Pins that the module is runnable, that ``os.environ`` (an ``os._Environ``,
not a dict) is accepted by the parsing layer, and that the process exit code
and stdout/stderr split match the documented contract.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration


def run_module(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # A minimal, controlled environment: no inherited PDFOPS_* noise.
    env = {"PATH": "/usr/bin:/bin"}
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "pdf_ops"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_invalid_config_exits_2_with_json_only_stdout() -> None:
    result = run_module({"PDFOPS_OPERATION": "bogus"})
    assert result.returncode == 2
    assert result.stderr == ""
    lines = result.stdout.strip().splitlines()
    events = [json.loads(line) for line in lines]
    assert events[-1]["event"] == "operation_failed"
    assert events[-1]["error_code"] == "INVALID_OPERATION"


def test_merge_without_inputs_exits_2() -> None:
    result = run_module({"PDFOPS_OPERATION": "merge"})
    assert result.returncode == 2
    events = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert events[-1]["error_code"] == "MISSING_VAR"


def test_extract_without_required_vars_exits_2() -> None:
    result = run_module({"PDFOPS_OPERATION": "extract"})
    assert result.returncode == 2
    assert result.stderr == ""
    events = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert events[-1]["error_code"] == "MISSING_VAR"
