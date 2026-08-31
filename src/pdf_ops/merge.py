"""The merge operation: validate everything, then write once, atomically."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pdf_ops.config import MergeConfig
from pdf_ops.engine import get_engine
from pdf_ops.errors import InputError, InvalidPdfError, PdfOpsError
from pdf_ops.output import atomic_output, check_output_path

PDF_MAGIC = b"%PDF-"

# Problem kinds found during input validation, in exit-code class order.
_INPUT_PROBLEMS = frozenset({"INPUT_MISSING", "INPUT_IS_DIRECTORY", "INPUT_UNREADABLE"})


def run_merge(config: MergeConfig, logger: logging.Logger) -> dict[str, Any]:
    validate_inputs(config.inputs)
    check_output_path(config.output)

    with atomic_output(config.output) as tmp_path:
        stats = get_engine().merge(config.inputs, tmp_path)

    logger.info(
        "merge_written",
        extra={
            "output_path": str(config.output),
            "pages_per_input": list(stats.pages_per_input),
        },
    )
    return {
        "inputs_merged": len(config.inputs),
        "pages": stats.pages_total,
        "bytes_written": config.output.stat().st_size,
        "output_path": str(config.output),
    }


def validate_inputs(inputs: Sequence[Path]) -> None:
    """Check every input up front and report all problems in one failure.

    An operator fixing a broken workflow should learn about every bad input
    from a single run, not one per retry. The raised error's class (and thus
    the exit code) follows the first problem in input order; the full list
    travels in ``context``.
    """
    problems: list[dict[str, str]] = []
    for path in inputs:
        code = _check_one(path)
        if code is not None:
            problems.append({"input": str(path), "error_code": code})
    if not problems:
        return

    first = problems[0]
    error_class: type[PdfOpsError] = (
        InputError if first["error_code"] in _INPUT_PROBLEMS else InvalidPdfError
    )
    raise error_class(
        f"{len(problems)} of {len(inputs)} input(s) unusable; "
        f"first: {first['input']} ({first['error_code']})",
        error_code=first["error_code"],
        context={"problems": problems},
    )


def _check_one(path: Path) -> str | None:
    if path.is_dir():
        return "INPUT_IS_DIRECTORY"
    if not path.is_file():
        return "INPUT_MISSING"
    try:
        with path.open("rb") as handle:
            head = handle.read(len(PDF_MAGIC))
    except OSError:
        return "INPUT_UNREADABLE"
    if not head.startswith(PDF_MAGIC):
        return "NOT_A_PDF"
    return None
