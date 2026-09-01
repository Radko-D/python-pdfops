"""Environment-variable configuration parsing.

``parse_config`` is a pure function over a mapping so tests drive it with
plain dicts; the real ``os.environ`` is touched only in ``__main__``. All
validation happens here, before any file is opened - invalid configuration
must fail fast with exit code 2. Deliberately filesystem-free: existence and
readability of paths are operation-stage concerns, not configuration ones.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from pdf_ops.errors import ConfigError

ENV_PREFIX = "PDFOPS_"

VAR_OPERATION = "PDFOPS_OPERATION"
VAR_LOG_LEVEL = "PDFOPS_LOG_LEVEL"
VAR_INPUTS = "PDFOPS_INPUTS"
VAR_OUTPUT = "PDFOPS_OUTPUT"
VAR_INPUT = "PDFOPS_INPUT"
VAR_OUTPUT_DIR = "PDFOPS_OUTPUT_DIR"
VAR_FAIL_ON_NO_ATTACHMENTS = "PDFOPS_FAIL_ON_NO_ATTACHMENTS"

# Every variable the application understands. Any other PDFOPS_-prefixed
# variable is rejected as a probable typo (a silently ignored misspelling like
# PDFOPS_INPUTS_ would otherwise surface as a confusing downstream error).
KNOWN_VARS = frozenset(
    {
        VAR_OPERATION,
        VAR_LOG_LEVEL,
        VAR_INPUTS,
        VAR_OUTPUT,
        VAR_INPUT,
        VAR_OUTPUT_DIR,
        VAR_FAIL_ON_NO_ATTACHMENTS,
    }
)

MERGE_ONLY_VARS = frozenset({VAR_INPUTS, VAR_OUTPUT})
EXTRACT_ONLY_VARS = frozenset({VAR_INPUT, VAR_OUTPUT_DIR, VAR_FAIL_ON_NO_ATTACHMENTS})

# The list separator for PDFOPS_INPUTS: os.pathsep (":" on POSIX), the same
# convention as PATH. Colons in mounted file paths are effectively unheard of;
# commas and spaces are not.
INPUTS_SEPARATOR = os.pathsep

_LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}
DEFAULT_LOG_LEVEL = logging.INFO


class Operation(StrEnum):
    MERGE = "merge"
    EXTRACT = "extract"


@dataclass(frozen=True, slots=True)
class MergeConfig:
    operation: ClassVar[Literal[Operation.MERGE]] = Operation.MERGE
    log_level: int
    inputs: tuple[Path, ...]
    output: Path


@dataclass(frozen=True, slots=True)
class ExtractConfig:
    operation: ClassVar[Literal[Operation.EXTRACT]] = Operation.EXTRACT
    log_level: int
    input: Path
    output_dir: Path
    fail_on_no_attachments: bool


type Config = MergeConfig | ExtractConfig


def parse_config(env: Mapping[str, str]) -> Config:
    """Validate ``env`` and freeze it into an operation config.

    Raises ConfigError (exit code 2) on any missing, invalid, unknown, or
    inapplicable variable.
    """
    _reject_unknown_vars(env)
    operation = _parse_operation(env)
    log_level = _parse_log_level(env)
    match operation:
        case Operation.MERGE:
            _reject_inapplicable_vars(env, operation, EXTRACT_ONLY_VARS)
            return MergeConfig(
                log_level=log_level,
                inputs=_parse_inputs(env),
                output=_parse_output(env),
            )
        case Operation.EXTRACT:
            _reject_inapplicable_vars(env, operation, MERGE_ONLY_VARS)
            return ExtractConfig(
                log_level=log_level,
                input=_parse_single_path(env, VAR_INPUT, "the PDF to extract from"),
                output_dir=_parse_single_path(
                    env, VAR_OUTPUT_DIR, "the directory receiving the attachments"
                ),
                fail_on_no_attachments=_parse_flag(env, VAR_FAIL_ON_NO_ATTACHMENTS),
            )


def _reject_unknown_vars(env: Mapping[str, str]) -> None:
    unknown = sorted(k for k in env if k.startswith(ENV_PREFIX) and k not in KNOWN_VARS)
    if unknown:
        raise ConfigError(
            f"unknown environment variable(s): {', '.join(unknown)}; "
            f"accepted: {', '.join(sorted(KNOWN_VARS))}",
            error_code="UNKNOWN_VAR",
            context={"unknown_vars": unknown},
        )


def _reject_inapplicable_vars(
    env: Mapping[str, str], operation: Operation, inapplicable: frozenset[str] | set[str]
) -> None:
    # A merge-only variable on an extract run (or vice versa) is the same
    # class of workflow-templating bug as a typo: fail loudly, don't ignore.
    present = sorted(k for k in inapplicable if k in env)
    if present:
        raise ConfigError(
            f"variable(s) not applicable to operation '{operation.value}': {', '.join(present)}",
            error_code="INAPPLICABLE_VAR",
            context={"operation": operation.value, "inapplicable_vars": present},
        )


def _parse_operation(env: Mapping[str, str]) -> Operation:
    raw = env.get(VAR_OPERATION, "").strip()
    if not raw:
        raise ConfigError(
            f"{VAR_OPERATION} is required (accepted values: merge, extract)",
            error_code="MISSING_VAR",
            context={"var": VAR_OPERATION},
        )
    try:
        return Operation(raw)
    except ValueError:
        raise ConfigError(
            f"{VAR_OPERATION} has invalid value {raw!r} (accepted values: merge, extract)",
            error_code="INVALID_OPERATION",
            context={"var": VAR_OPERATION, "value": raw},
        ) from None


def _parse_log_level(env: Mapping[str, str]) -> int:
    raw = env.get(VAR_LOG_LEVEL, "").strip()
    if not raw:
        return DEFAULT_LOG_LEVEL
    level = _LOG_LEVELS.get(raw.upper())
    if level is None:
        raise ConfigError(
            f"{VAR_LOG_LEVEL} has invalid value {raw!r} "
            f"(accepted values: {', '.join(_LOG_LEVELS).lower()}, case-insensitive)",
            error_code="INVALID_LOG_LEVEL",
            context={"var": VAR_LOG_LEVEL, "value": raw},
        )
    return level


def _parse_inputs(env: Mapping[str, str]) -> tuple[Path, ...]:
    raw = env.get(VAR_INPUTS, "").strip()
    if not raw:
        raise ConfigError(
            f"{VAR_INPUTS} is required for merge "
            f"(ordered file paths separated by {INPUTS_SEPARATOR!r})",
            error_code="MISSING_VAR",
            context={"var": VAR_INPUTS},
        )
    parts = [part.strip() for part in raw.split(INPUTS_SEPARATOR)]
    if any(not part for part in parts):
        raise ConfigError(
            f"{VAR_INPUTS} contains an empty path component "
            f"(check for stray {INPUTS_SEPARATOR!r} separators)",
            error_code="INVALID_INPUTS",
            context={"var": VAR_INPUTS, "value": raw},
        )
    paths = [Path(part) for part in parts]
    # Duplicates are detected on the parsed Path objects, not the raw strings:
    # '/in/a.pdf', '/in/./a.pdf' and '/in//a.pdf' are the same file spelled
    # three ways, and a repeated merge input is almost always a templating bug
    # that would silently duplicate content in the output document. (Aliasing
    # through symlinks can't be caught here - config parsing stays
    # filesystem-free by design.)
    duplicated_paths = {p for p in paths if paths.count(p) > 1}
    if duplicated_paths:
        duplicates = sorted({part for part in parts if Path(part) in duplicated_paths})
        raise ConfigError(
            f"{VAR_INPUTS} lists the same path more than once: {', '.join(duplicates)}",
            error_code="DUPLICATE_INPUTS",
            context={"var": VAR_INPUTS, "duplicates": duplicates},
        )
    return tuple(paths)


def _parse_output(env: Mapping[str, str]) -> Path:
    raw = env.get(VAR_OUTPUT, "").strip()
    if not raw:
        raise ConfigError(
            f"{VAR_OUTPUT} is required for merge (path of the output PDF)",
            error_code="MISSING_VAR",
            context={"var": VAR_OUTPUT},
        )
    return Path(raw)


def _parse_single_path(env: Mapping[str, str], var: str, purpose: str) -> Path:
    raw = env.get(var, "").strip()
    if not raw:
        raise ConfigError(
            f"{var} is required for extract ({purpose})",
            error_code="MISSING_VAR",
            context={"var": var},
        )
    return Path(raw)


def _parse_flag(env: Mapping[str, str], var: str, *, default: bool = False) -> bool:
    raw = env.get(var, "").strip()
    if not raw:
        return default
    normalized = raw.lower()
    if normalized in ("true", "false"):
        return normalized == "true"
    raise ConfigError(
        f"{var} has invalid value {raw!r} (accepted values: true, false, case-insensitive)",
        error_code="INVALID_FLAG",
        context={"var": var, "value": raw},
    )
