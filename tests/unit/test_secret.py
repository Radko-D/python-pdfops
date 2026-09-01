"""The Secret wrapper and the log-redaction layer - the no-leak machinery."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator

import pytest

from pdf_ops.logging_setup import (
    JsonFormatter,
    clear_registered_secrets,
    register_secret_value,
)
from pdf_ops.secret import Secret

pytestmark = pytest.mark.unit


class TestSecret:
    def test_never_leaks_through_repr_str_or_format(self) -> None:
        secret = Secret("hunter2")
        assert repr(secret) == "***"
        assert str(secret) == "***"
        assert f"password is {secret}" == "password is ***"
        assert "hunter2" not in f"{secret!r}{secret!s}"

    def test_reveal_is_the_only_way_in(self) -> None:
        assert Secret("hunter2").reveal() == "hunter2"

    def test_bool_reflects_emptiness(self) -> None:
        assert Secret("x")
        assert not Secret("")


class TestRedactionFilter:
    @pytest.fixture(autouse=True)
    def _clean_registry(self) -> Generator[None]:
        clear_registered_secrets()
        yield
        clear_registered_secrets()

    def format_record(self, **extra: object) -> dict[str, object]:
        record = logging.LogRecord(
            name="pdf_ops",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="an_event",
            args=None,
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return json.loads(JsonFormatter().format(record))

    def test_registered_value_scrubbed_from_string_fields(self) -> None:
        register_secret_value("hunter2")
        payload = self.format_record(detail="failed with password hunter2 somewhere")
        assert "hunter2" not in json.dumps(payload)
        assert payload["detail"] == "failed with password *** somewhere"

    def test_scrub_recurses_into_context_dicts_and_lists(self) -> None:
        register_secret_value("hunter2")
        payload = self.format_record(context={"inputs": ["a hunter2 b"], "note": "hunter2"})
        serialized = json.dumps(payload)
        assert "hunter2" not in serialized
        assert "***" in serialized

    def test_traceback_payloads_are_scrubbed(self) -> None:
        register_secret_value("hunter2")
        try:
            raise RuntimeError("boom hunter2")
        except RuntimeError:
            import sys

            record = logging.LogRecord(
                name="pdf_ops",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="operation_failed",
                args=None,
                exc_info=sys.exc_info(),
            )
        payload = json.loads(JsonFormatter().format(record))
        assert "hunter2" not in json.dumps(payload)
        assert "boom ***" in str(payload["traceback"])


class TestScrubIntegrity:
    @pytest.fixture(autouse=True)
    def _clean(self) -> Generator[None]:
        clear_registered_secrets()
        yield
        clear_registered_secrets()

    def make_payload(self, **extra: object) -> dict[str, object]:
        record = logging.LogRecord(
            name="pdf_ops",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="merge_written",
            args=None,
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return json.loads(JsonFormatter().format(record))

    def test_token_fields_never_scrubbed(self) -> None:
        # A password equal to a known token ("merge") must not rewrite
        # code-controlled fields: doing so both breaks workflow-engine
        # matching and acts as a password oracle.
        register_secret_value("merge")
        payload = self.make_payload(operation="merge", error_code="MERGE_FAILED")
        assert payload["event"] == "merge_written"
        assert payload["operation"] == "merge"
        assert payload["error_code"] == "MERGE_FAILED"

    def test_free_text_fields_are_scrubbed(self) -> None:
        register_secret_value("merge")
        payload = self.make_payload(detail="library said merge is wrong")
        assert payload["detail"] == "library said *** is wrong"

    def test_overlapping_secrets_scrub_longest_first(self) -> None:
        register_secret_value("Spring2026")
        register_secret_value("Spring2026!x9")
        payload = self.make_payload(detail="bad key 'Spring2026!x9' rejected")
        assert payload["detail"] == "bad key '***' rejected"
        assert "!x9" not in str(payload["detail"])

    def test_repr_escaped_variant_also_scrubbed(self) -> None:
        register_secret_value("back\\slash-pw")
        # a library embedding the value via %r doubles the backslash
        payload = self.make_payload(detail="rejected 'back\\\\slash-pw' here")
        assert "slash-pw" not in str(payload["detail"])

    def test_too_short_secrets_are_not_registered(self) -> None:
        assert register_secret_value("abc") is False
        payload = self.make_payload(detail="abc appears here")
        assert payload["detail"] == "abc appears here"
