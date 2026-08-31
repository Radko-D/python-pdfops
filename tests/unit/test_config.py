"""Table-driven tests for the env-var configuration contract."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from pdf_ops.config import ExtractConfig, MergeConfig, Operation, parse_config
from pdf_ops.errors import ConfigError

pytestmark = pytest.mark.unit

MERGE_ENV = {
    "PDFOPS_OPERATION": "merge",
    "PDFOPS_INPUTS": "/in/a.pdf",
    "PDFOPS_OUTPUT": "/out/m.pdf",
}


class TestOperation:
    def test_merge_parses_to_merge_config(self) -> None:
        config = parse_config(MERGE_ENV)
        assert isinstance(config, MergeConfig)
        assert config.operation is Operation.MERGE

    def test_extract_parses_to_extract_config(self) -> None:
        config = parse_config({"PDFOPS_OPERATION": "extract"})
        assert isinstance(config, ExtractConfig)
        assert config.operation is Operation.EXTRACT

    def test_surrounding_whitespace_is_tolerated(self) -> None:
        # Templated env values (workflow parameters, shell heredocs) often
        # carry stray whitespace; stripping it is the predictable choice.
        assert isinstance(parse_config({"PDFOPS_OPERATION": " extract\n"}), ExtractConfig)

    @pytest.mark.parametrize("env", [{}, {"PDFOPS_OPERATION": ""}, {"PDFOPS_OPERATION": "   "}])
    def test_missing_or_empty_operation(self, env: dict[str, str]) -> None:
        with pytest.raises(ConfigError) as exc_info:
            parse_config(env)
        assert exc_info.value.error_code == "MISSING_VAR"

    @pytest.mark.parametrize("value", ["bogus", "MERGE", "Merge", "merge,extract", "both"])
    def test_invalid_operation_value(self, value: str) -> None:
        with pytest.raises(ConfigError) as exc_info:
            parse_config({"PDFOPS_OPERATION": value})
        assert exc_info.value.error_code == "INVALID_OPERATION"
        # The operator reading the failure event must see what IS accepted.
        assert "merge" in exc_info.value.message
        assert "extract" in exc_info.value.message


class TestLogLevel:
    def test_defaults_to_info(self) -> None:
        assert parse_config({"PDFOPS_OPERATION": "extract"}).log_level == logging.INFO

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("DEBUG", logging.DEBUG),
            ("debug", logging.DEBUG),
            ("Info", logging.INFO),
            ("WARNING", logging.WARNING),
            ("error", logging.ERROR),
        ],
    )
    def test_accepted_levels_case_insensitive(self, value: str, expected: int) -> None:
        env = {"PDFOPS_OPERATION": "extract", "PDFOPS_LOG_LEVEL": value}
        assert parse_config(env).log_level == expected

    @pytest.mark.parametrize("value", ["verbose", "TRACE", "42"])
    def test_invalid_level_is_config_error(self, value: str) -> None:
        with pytest.raises(ConfigError) as exc_info:
            parse_config({"PDFOPS_OPERATION": "extract", "PDFOPS_LOG_LEVEL": value})
        assert exc_info.value.error_code == "INVALID_LOG_LEVEL"


class TestMergeVars:
    def test_inputs_split_on_pathsep_in_order(self) -> None:
        env = MERGE_ENV | {"PDFOPS_INPUTS": os.pathsep.join(["/in/b.pdf", "/in/a.pdf"])}
        config = parse_config(env)
        assert isinstance(config, MergeConfig)
        assert config.inputs == (Path("/in/b.pdf"), Path("/in/a.pdf"))
        assert config.output == Path("/out/m.pdf")

    def test_component_whitespace_is_stripped(self) -> None:
        env = MERGE_ENV | {"PDFOPS_INPUTS": f" /in/a.pdf {os.pathsep} /in/b.pdf\n"}
        config = parse_config(env)
        assert isinstance(config, MergeConfig)
        assert config.inputs == (Path("/in/a.pdf"), Path("/in/b.pdf"))

    @pytest.mark.parametrize("var", ["PDFOPS_INPUTS", "PDFOPS_OUTPUT"])
    def test_merge_requires_inputs_and_output(self, var: str) -> None:
        env = dict(MERGE_ENV)
        del env[var]
        with pytest.raises(ConfigError) as exc_info:
            parse_config(env)
        assert exc_info.value.error_code == "MISSING_VAR"
        assert var in exc_info.value.message

    @pytest.mark.parametrize(
        "value",
        [
            f"/in/a.pdf{os.pathsep}",
            f"{os.pathsep}/in/a.pdf",
            f"/in/a.pdf{os.pathsep}{os.pathsep}/b",
        ],
    )
    def test_empty_path_component_rejected(self, value: str) -> None:
        with pytest.raises(ConfigError) as exc_info:
            parse_config(MERGE_ENV | {"PDFOPS_INPUTS": value})
        assert exc_info.value.error_code == "INVALID_INPUTS"

    def test_duplicate_inputs_rejected(self) -> None:
        # A repeated merge input is almost always a templating bug that would
        # silently duplicate content in the output document.
        value = os.pathsep.join(["/in/a.pdf", "/in/b.pdf", "/in/a.pdf"])
        with pytest.raises(ConfigError) as exc_info:
            parse_config(MERGE_ENV | {"PDFOPS_INPUTS": value})
        assert exc_info.value.error_code == "DUPLICATE_INPUTS"
        assert exc_info.value.context["duplicates"] == ["/in/a.pdf"]

    @pytest.mark.parametrize(
        "alias",
        ["/in/./a.pdf", "/in//a.pdf", "/in/a.pdf/"],
    )
    def test_duplicate_detection_sees_through_path_spelling(self, alias: str) -> None:
        # The same file spelled two ways must not slip past the check -
        # Path-level comparison catches dot segments, doubled and trailing
        # slashes (symlink aliasing is out of scope: parsing stays
        # filesystem-free).
        value = os.pathsep.join(["/in/a.pdf", alias])
        with pytest.raises(ConfigError) as exc_info:
            parse_config(MERGE_ENV | {"PDFOPS_INPUTS": value})
        assert exc_info.value.error_code == "DUPLICATE_INPUTS"

    @pytest.mark.parametrize("var", ["PDFOPS_INPUTS", "PDFOPS_OUTPUT"])
    def test_merge_vars_inapplicable_to_extract(self, var: str) -> None:
        env = {"PDFOPS_OPERATION": "extract", var: "/some/path"}
        with pytest.raises(ConfigError) as exc_info:
            parse_config(env)
        assert exc_info.value.error_code == "INAPPLICABLE_VAR"
        assert var in exc_info.value.message


class TestUnknownVars:
    def test_unknown_prefixed_var_is_rejected(self) -> None:
        env = {"PDFOPS_OPERATION": "extract", "PDFOPS_OPERATOIN": "merge"}
        with pytest.raises(ConfigError) as exc_info:
            parse_config(env)
        assert exc_info.value.error_code == "UNKNOWN_VAR"
        assert "PDFOPS_OPERATOIN" in exc_info.value.message
        assert exc_info.value.context["unknown_vars"] == ["PDFOPS_OPERATOIN"]

    def test_multiple_unknown_vars_all_reported(self) -> None:
        env = {
            "PDFOPS_OPERATION": "extract",
            "PDFOPS_ZZZ": "1",
            "PDFOPS_AAA": "2",
        }
        with pytest.raises(ConfigError) as exc_info:
            parse_config(env)
        assert exc_info.value.context["unknown_vars"] == ["PDFOPS_AAA", "PDFOPS_ZZZ"]

    def test_unprefixed_vars_are_ignored(self) -> None:
        # The container inherits PATH, HOME, etc. - only our namespace is policed.
        env = {"PDFOPS_OPERATION": "extract", "PATH": "/usr/bin", "HOME": "/home/x"}
        assert isinstance(parse_config(env), ExtractConfig)
