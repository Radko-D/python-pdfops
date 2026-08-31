"""The exception-to-exit-code mapping is the external API - pin it."""

from __future__ import annotations

import pytest

from pdf_ops.errors import (
    ConfigError,
    ExitCode,
    InputError,
    InvalidPdfError,
    OutputError,
    PasswordError,
    PdfOpsError,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("error_class", "expected_code"),
    [
        (ConfigError, 2),
        (InputError, 3),
        (InvalidPdfError, 4),
        (PasswordError, 5),
        (OutputError, 6),
    ],
)
def test_error_class_maps_to_exit_code(error_class: type[PdfOpsError], expected_code: int) -> None:
    err = error_class("boom", error_code="SOME_CODE")
    assert int(err.exit_code) == expected_code


def test_exit_code_values_are_stable() -> None:
    assert [c.value for c in ExitCode] == [0, 1, 2, 3, 4, 5, 6]


def test_error_carries_code_message_and_context() -> None:
    err = ConfigError("bad value", error_code="INVALID_OPERATION", context={"var": "X"})
    assert err.message == "bad value"
    assert err.error_code == "INVALID_OPERATION"
    assert err.context == {"var": "X"}
    assert str(err) == "bad value"


def test_context_defaults_to_empty_dict() -> None:
    err = InputError("missing", error_code="INPUT_MISSING")
    assert err.context == {}
