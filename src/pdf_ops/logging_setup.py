"""JSON-lines logging to stdout - the operator interface of the container.

One JSON object per line; a workflow engine (e.g. Argo) captures stdout as the
step log. The log message is a stable machine-readable event token; structured
detail is passed via ``extra`` and merged into the payload.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_LOGGER_NAME = "pdf_ops"

# Attributes present on every LogRecord; anything not listed here arrived via
# ``extra`` and belongs in the JSON payload.
_RESERVED = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_type"] = record.exc_info[0].__name__
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def emit_terminal(
    logger: logging.Logger,
    level: int,
    event: str,
    fields: dict[str, Any],
    *,
    include_exc_info: bool = False,
) -> None:
    """Emit a terminal event, bypassing the logger's level filter.

    The operator contract guarantees exactly one terminal event per run
    (``operation_complete`` | ``operation_failed``) regardless of
    PDFOPS_LOG_LEVEL - level filtering applies only to lifecycle and
    diagnostic events. ``Logger.handle`` skips the level check by design.
    """
    exc_info = sys.exc_info() if include_exc_info else None
    record = logger.makeRecord(
        logger.name, level, "(terminal)", 0, event, (), exc_info, extra=fields
    )
    logger.handle(record)


class _ThirdPartyEventFilter(logging.Filter):
    """Rewrite a third-party log record into our event schema.

    The original message moves to ``detail`` and the emitting logger to
    ``source``, so ``event`` stays a stable, greppable token.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.detail = record.getMessage()
        record.source = record.name
        record.msg = "pdf_library_message"
        record.args = ()
        return True


# Loggers whose records must reach stdout as JSON instead of falling through
# to logging.lastResort on stderr: the PDF library's recoverable-corruption
# warnings, and Python warnings (via logging.captureWarnings below). Anything
# on stderr would break the JSON-only/empty-stderr operator contract.
_THIRD_PARTY_LOGGERS = ("pypdf", "py.warnings")


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the application logger.

    Replaces any existing handler so the stream always points at the current
    ``sys.stdout`` (keeps repeated in-process runs, and pytest capture, honest).
    Also routes third-party library records and captured warnings into the
    same JSON stream.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    _replace_handlers(logger, handler)

    logging.captureWarnings(True)
    for name in _THIRD_PARTY_LOGGERS:
        third_party = logging.getLogger(name)
        third_party.setLevel(logging.WARNING)
        third_party.propagate = False
        third_party_handler = logging.StreamHandler(sys.stdout)
        third_party_handler.setFormatter(JsonFormatter())
        third_party_handler.addFilter(_ThirdPartyEventFilter())
        _replace_handlers(third_party, third_party_handler)

    return logger


def _replace_handlers(logger: logging.Logger, handler: logging.Handler) -> None:
    for old in list(logger.handlers):
        logger.removeHandler(old)
        old.close()
    logger.addHandler(handler)
