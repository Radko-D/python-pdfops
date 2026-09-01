"""Top-level orchestration: the single error boundary and operation dispatch."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from pdf_ops.config import (
    Config,
    ExtractConfig,
    MergeConfig,
    Secrets,
    describe_secret,
    parse_config,
    resolve_secrets,
)
from pdf_ops.errors import ExitCode, PdfOpsError
from pdf_ops.extract import run_extract
from pdf_ops.logging_setup import emit_terminal, register_secret_value, setup_logging
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
        secrets = resolve_secrets(config)
        for secret in (secrets.password, secrets.output_password):
            if secret is not None and not register_secret_value(secret.reveal()):
                logger.warning(
                    "redaction_degraded",
                    extra={
                        "detail": "a supplied secret is too short for defense-in-depth "
                        "log scrubbing; the structural no-leak layers still apply"
                    },
                )
        logger.info("config_loaded", extra=_config_echo(config))
        result = _dispatch(config, secrets, logger)
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


def _config_echo(config: Config) -> dict[str, Any]:
    """The config_loaded payload: secrets appear as presence only, never value."""
    echo: dict[str, Any] = {
        "operation": config.operation.value,
        "log_level": logging.getLevelName(config.log_level).lower(),
        "password": describe_secret(config.password),
    }
    if isinstance(config, MergeConfig):
        echo["output_encryption"] = config.output_encryption.value
        echo["output_password"] = describe_secret(config.output_password)
    return echo


def _dispatch(config: Config, secrets: Secrets, logger: logging.Logger) -> dict[str, Any] | None:
    logger.info("operation_started", extra={"operation": config.operation.value})
    match config:
        case MergeConfig():
            return run_merge(config, secrets, logger)
        case ExtractConfig():
            return run_extract(config, secrets, logger)
