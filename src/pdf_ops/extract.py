"""The extract operation: attachment names are untrusted input.

Names come straight out of the PDF and are written to a mounted filesystem,
so every name passes through ``sanitize_attachment_name`` - a pure function
designed for exhaustive table testing - and the resolved target of every
write is verified to stay inside the output directory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pdf_ops.config import ExtractConfig, Secrets
from pdf_ops.engine import Attachment, get_engine
from pdf_ops.errors import InputError, OutputError
from pdf_ops.merge import validate_inputs
from pdf_ops.output import atomic_output, check_output_dir

# Filesystem NAME_MAX is 255 bytes on the relevant filesystems; leave room
# for collision suffixes and the atomic-write temp prefix.
_MAX_NAME_BYTES = 200

FALLBACK_PREFIX = "attachment_"


def run_extract(config: ExtractConfig, secrets: Secrets, logger: logging.Logger) -> dict[str, Any]:
    validate_inputs([config.input])
    check_output_dir(config.output_dir)

    engine = get_engine()
    opened = engine.open_input(config.input, secrets.password)
    logger.info(
        "input_opened",
        extra={
            "input": str(config.input),
            "pages": opened.pages,
            "encrypted": opened.encrypted,
            "algorithm": opened.algorithm,
            "password_type": opened.password_type,
        },
    )
    if secrets.password is not None and not opened.encrypted:
        logger.warning(
            "password_unused",
            extra={"detail": "a password was supplied but the input is not encrypted"},
        )

    attachments = engine.list_attachments(opened)
    if not attachments:
        if config.fail_on_no_attachments:
            raise InputError(
                f"{config.input} contains no embedded attachments "
                "(failing because PDFOPS_FAIL_ON_NO_ATTACHMENTS=true)",
                error_code="NO_ATTACHMENTS",
                context={"input": str(config.input)},
            )
        return {"attachments_extracted": 0, "bytes_written": 0}

    planned = _plan_targets(attachments)

    # All-or-nothing conflict check BEFORE anything is written: a retry after
    # a partial failure must not silently mix old and new files. lexists-style
    # check so a pre-existing symlink (even dangling) counts as a conflict.
    conflicts = sorted(
        str(p.name)
        for p in planned
        if (target := config.output_dir / p.name).is_symlink() or target.exists()
    )
    if conflicts:
        raise OutputError(
            f"{len(conflicts)} file(s) already exist in {config.output_dir}: "
            f"{', '.join(conflicts)} (refusing to overwrite)",
            error_code="OUTPUT_EXISTS",
            context={"output_dir": str(config.output_dir), "conflicts": conflicts},
        )

    resolved_root = config.output_dir.resolve()
    bytes_written = 0
    for item in planned:
        target = config.output_dir / item.name
        if not target.resolve().parent.is_relative_to(resolved_root):
            # Unreachable if the sanitizer holds; a violation is a bug worth
            # crashing loudly on, never worth writing through.
            raise RuntimeError(f"sanitization invariant violated for {item.original!r}")
        with atomic_output(target) as tmp_path:
            tmp_path.write_bytes(item.data)
        bytes_written += len(item.data)
        logger.info(
            "attachment_extracted",
            extra={
                "attachment": item.name,
                "original_name": item.original if item.original != item.name else None,
                "bytes": len(item.data),
            },
        )

    return {"attachments_extracted": len(planned), "bytes_written": bytes_written}


@dataclass(frozen=True, slots=True)
class _PlannedFile:
    name: str
    original: str
    data: bytes


def _plan_targets(attachments: list[Attachment]) -> list[_PlannedFile]:
    """Sanitized, collision-suffixed target names in extraction order.

    Collisions are detected on casefolded names: the output directory is a
    mounted volume that may be case-insensitive (macOS, SMB), where two names
    differing only in case are one file - suffixing keeps every payload on
    every filesystem, and the plan stays identical everywhere (determinism).
    """
    used: set[str] = set()
    next_suffix: dict[str, int] = {}
    planned: list[_PlannedFile] = []
    for index, attachment in enumerate(attachments):
        name = _dedupe(sanitize_attachment_name(attachment.name, index), used, next_suffix)
        used.add(name.casefold())
        planned.append(_PlannedFile(name=name, original=attachment.name, data=attachment.data))
    return planned


def sanitize_attachment_name(raw: str, index: int) -> str:
    """Reduce an untrusted attachment name to a safe basename.

    Normalizes both separator conventions (a name written on Windows may
    carry backslashes), takes the last path component, strips control
    characters and surrounding whitespace, and falls back to a deterministic
    ``attachment_<index>`` when nothing safe remains. Pure function - no
    filesystem access - so the whole behavior is table-testable.
    """
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    # Drop C0 controls (incl. NUL), DEL, and the C1 range - every Unicode
    # "Cc" character. Printable Unicode passes through untouched.
    name = "".join(ch for ch in name if ord(ch) >= 32 and not (0x7F <= ord(ch) <= 0x9F))
    name = name.strip()
    if name in ("", ".", ".."):
        return f"{FALLBACK_PREFIX}{index}"
    while len(name.encode()) > _MAX_NAME_BYTES:
        name = name[:-1]
    return name


def _dedupe(name: str, used: set[str], next_suffix: dict[str, int]) -> str:
    """Deterministic collision suffixes: report.txt, report-1.txt, ...

    ``used`` holds casefolded taken names; ``next_suffix`` remembers the next
    counter per colliding base so N duplicates resolve in O(N), not O(N^2).
    """
    key = name.casefold()
    if key not in used:
        return name
    if "." in name.lstrip("."):
        stem, dot, suffix = name.rpartition(".")
        candidate_format = f"{stem}-{{}}{dot}{suffix}"
    else:
        candidate_format = f"{name}-{{}}"
    counter = next_suffix.get(key, 1)
    while (candidate := candidate_format.format(counter)).casefold() in used:
        counter += 1
    next_suffix[key] = counter + 1
    return candidate
