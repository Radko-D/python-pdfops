"""The structure-walk translation net: a builtin exception raised while
walking a document's structure is a data problem, never an internal error."""

from pathlib import Path

import pytest

from pdf_ops.engine_pikepdf import (
    _STRUCTURE_FAILURES,
    _translating,
)
from pdf_ops.errors import ErrorCode, ExitCode, InvalidPdfError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("exc_type", _STRUCTURE_FAILURES)
def test_builtin_failure_inside_a_walk_classifies_as_corrupt(
    exc_type: type[Exception],
) -> None:
    with pytest.raises(InvalidPdfError) as caught, _translating(Path("hostile.pdf")):
        raise exc_type("hostile shape")
    assert caught.value.error_code == ErrorCode.CORRUPT_PDF
    assert caught.value.exit_code == ExitCode.INVALID_PDF
