"""Top-level orchestration: the single error boundary and operation dispatch."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from pdf_ops.config import Config, ExtractConfig, MergeConfig, parse_config
from pdf_ops.errors import ExitCode, PdfOpsError
from pdf_ops.logging_setup import emit_terminal, setup_logging
from pdf_ops.merge import run_merge


def run(env: Mapping[str, str]) -> int:
    """Execute the one operation described by ``env``; return the exit code.

    This is the application's only error boundary: every predictable failure
    is a PdfOpsError carrying its exit code and error code; anything else
    exits UNEXPECTED (1) with a logged traceback. No other module logs-and-
    swallows or exits. Terminal events are emitted through ``emit_terminal``
    so PDFOPS_LOG_LEVEL can never suppress them.
    """
    logger = setup_logging()
    try:
        config = parse_config(env)
        logger.setLevel(config.log_level)
        logger.info(
            "config_loaded",
            extra={
                "operation": config.operation.value,
                "log_level": logging.getLevelName(config.log_level).lower(),
            },
        )
        result = _dispatch(config, logger)
        emit_terminal(
            logger,
            logging.INFO,
            "operation_complete",
            {
                "operation": config.operation.value,
                "exit_code": int(ExitCode.SUCCESS),
                **(result or {}),
            },
        )
        return int(ExitCode.SUCCESS)
    except PdfOpsError as err:
        emit_terminal(
            logger,
            logging.ERROR,
            "operation_failed",
            {
                "error_code": err.error_code,
                "error_message": err.message,
                "exit_code": int(err.exit_code),
                "context": err.context,
            },
        )
        return int(err.exit_code)
    except Exception:
        emit_terminal(
            logger,
            logging.ERROR,
            "operation_failed",
            {
                "error_code": "UNEXPECTED_ERROR",
                "exit_code": int(ExitCode.UNEXPECTED),
            },
            include_exc_info=True,
        )
        return int(ExitCode.UNEXPECTED)


def _dispatch(config: Config, logger: logging.Logger) -> dict[str, Any] | None:
    logger.info("operation_started", extra={"operation": config.operation.value})
    match config:
        case MergeConfig():
            return run_merge(config, logger)
        case ExtractConfig():
            raise NotImplementedError("extract is not implemented yet")
