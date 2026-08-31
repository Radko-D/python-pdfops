"""Error taxonomy and exit codes.

The process exit code is the application's external API toward the workflow
engine: each error class maps to exactly one code, defined up front because
renumbering later would break workflow retry policies built on top of it.
Fine-grained detail travels in the machine-readable ``error_code`` string
carried by every raised error and emitted in the terminal log event.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    """Exit codes a workflow engine can branch on (e.g. Argo retryStrategy)."""

    SUCCESS = 0
    UNEXPECTED = 1
    CONFIG = 2
    INPUT = 3
    INVALID_PDF = 4
    PASSWORD = 5
    OUTPUT = 6


class PdfOpsError(Exception):
    """Base class for every predictable failure.

    ``error_code`` is a stable machine-readable token (e.g. ``MISSING_VAR``);
    ``context`` holds structured detail for the failure log event. Neither may
    ever contain secret material - messages carry paths and names, not values.
    """

    exit_code: ExitCode = ExitCode.UNEXPECTED

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context: dict[str, Any] = context or {}


class ConfigError(PdfOpsError):
    """Invalid or missing environment configuration."""

    exit_code = ExitCode.CONFIG


class InputError(PdfOpsError):
    """Input file missing, unreadable, or not a regular file."""

    exit_code = ExitCode.INPUT


class InvalidPdfError(PdfOpsError):
    """Input exists but is not a valid PDF (corrupt, truncated, wrong type)."""

    exit_code = ExitCode.INVALID_PDF


class PasswordError(PdfOpsError):
    """Password required, wrong, or the encryption scheme is unsupported."""

    exit_code = ExitCode.PASSWORD


class OutputError(PdfOpsError):
    """Output conflict or output location not usable (exists, missing dir, full disk)."""

    exit_code = ExitCode.OUTPUT
