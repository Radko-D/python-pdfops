"""The merge operation: validate everything, then write once, atomically."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pdf_ops.config import MergeConfig, OutputEncryption, Secrets
from pdf_ops.engine import OpenedInput, get_engine
from pdf_ops.errors import ConfigError, InputError, InvalidPdfError, PdfOpsError
from pdf_ops.output import atomic_output, check_output_path
from pdf_ops.secret import Secret

PDF_MAGIC = b"%PDF-"

# Problem kinds found during input validation, in exit-code class order.
_INPUT_PROBLEMS = frozenset({"INPUT_MISSING", "INPUT_IS_DIRECTORY", "INPUT_UNREADABLE"})


def run_merge(config: MergeConfig, secrets: Secrets, logger: logging.Logger) -> dict[str, Any]:
    validate_inputs(config.inputs)
    check_output_path(config.output)

    engine = get_engine()
    opened: list[OpenedInput] = []
    for path in config.inputs:
        one = engine.open_input(path, secrets.password)
        opened.append(one)
        logger.info(
            "input_opened",
            extra={
                "input": str(path),
                "pages": one.pages,
                "encrypted": one.encrypted,
                "algorithm": one.algorithm,
                "password_type": one.password_type,
            },
        )

    encrypted_count = sum(1 for one in opened if one.encrypted)
    output_password, password_source = _choose_output_password(config, secrets, encrypted_count)
    if (
        secrets.password is not None
        and encrypted_count == 0
        and password_source != "input-fallback"
    ):
        # Not warned when the input password was consumed as the
        # output-encryption fallback - it was used, just not for decryption.
        logger.warning(
            "password_unused",
            extra={"detail": "a password was supplied but no input is encrypted"},
        )
    if output_password is None and encrypted_count > 0:
        # never-mode with encrypted inputs: the merge proceeds, but the
        # confidentiality downgrade must be impossible to miss in the log.
        logger.warning(
            "security_downgrade",
            extra={
                "encrypted_inputs": encrypted_count,
                "detail": "encrypted input(s) merged into an unencrypted output "
                "(PDFOPS_OUTPUT_ENCRYPTION=never)",
            },
        )

    with atomic_output(config.output) as tmp_path:
        engine.merge_to(opened, tmp_path, output_password)

    if output_password is not None:
        logger.info(
            "output_encrypted",
            extra={"algorithm": "AES-256", "password_source": password_source},
        )
    logger.info(
        "merge_written",
        extra={
            "output_path": str(config.output),
            "pages_per_input": [one.pages for one in opened],
            "output_encrypted": output_password is not None,
        },
    )
    return {
        "inputs_merged": len(config.inputs),
        "pages": sum(one.pages for one in opened),
        "bytes_written": config.output.stat().st_size,
        "output_path": str(config.output),
        "output_encrypted": output_password is not None,
    }


def _choose_output_password(
    config: MergeConfig, secrets: Secrets, encrypted_count: int
) -> tuple[Secret | None, str | None]:
    """Apply the output-encryption policy; returns (password, source-label).

    The fallback to the input password uses only an *explicitly supplied*
    one - inputs opened via the empty auto-try carry no real secret, and
    encrypting the output with an empty password would be a lock made of
    paper.
    """
    mode = config.output_encryption
    if mode is OutputEncryption.NEVER:
        return None, None
    if mode is OutputEncryption.INHERIT and encrypted_count == 0:
        return None, None
    if secrets.output_password is not None:
        return secrets.output_password, "output"
    if secrets.password is not None:
        return secrets.password, "input-fallback"
    raise ConfigError(
        f"output encryption is required (PDFOPS_OUTPUT_ENCRYPTION={mode.value}) but no "
        "explicit password is available - the encrypted input(s) opened with the empty "
        "password; supply PDFOPS_OUTPUT_PASSWORD_FILE or PDFOPS_OUTPUT_PASSWORD",
        error_code="MISSING_OUTPUT_PASSWORD",
        context={"output_encryption": mode.value},
    )


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
