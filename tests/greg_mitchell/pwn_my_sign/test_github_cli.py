from http.client import IncompleteRead
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError

import pytest
from click.testing import CliRunner

from greg_mitchell.pwn_my_sign.cli.mysign import main as mysign
from greg_mitchell.pwn_my_sign.github.models import ComponentStatus, Rollup, Status, Summary
from greg_mitchell.pwn_my_sign.github.source import MAX_SUMMARY_BYTES, GitHubSource, SummaryOpener


@pytest.fixture
def document() -> bytes:
    return Path("tests/fixtures/github/healthy.json").read_bytes()


@pytest.fixture
def operations(document: bytes) -> Mock:
    source = Mock(spec=GitHubSource)
    source.fetch.return_value = Summary.model_validate_json(document)
    source.read.return_value = Summary.model_validate_json(document)
    return source


@pytest.mark.parametrize("rollup", tuple(Rollup))
def test_github_status_when_no_policy_is_supplied_returns_provider_indicator(operations: Mock, rollup: Rollup) -> None:
    operations.fetch.return_value = operations.fetch.return_value.model_copy(
        update={"status": Status(indicator=rollup)}
    )

    result = CliRunner().invoke(mysign, ["github", "status"], obj=operations, catch_exceptions=False)

    assert result.stdout == f"{rollup}\n"


def test_github_status_when_service_policy_is_supplied_returns_policy_code(operations: Mock) -> None:
    result = CliRunner().invoke(
        mysign,
        ["github", "status", "--policy", "tests/fixtures/github/default-services.toml"],
        obj=operations,
        catch_exceptions=False,
    )

    assert result.stdout == "ok\n"


def test_github_status_when_default_timeout_is_used_calls_fetch_with_default(operations: Mock) -> None:
    CliRunner().invoke(mysign, ["github", "status"], obj=operations, catch_exceptions=False)

    operations.fetch.assert_called_once_with(15)


def test_github_status_when_timeout_is_selected_calls_fetch_with_timeout(operations: Mock) -> None:
    CliRunner().invoke(mysign, ["github", "status", "--timeout", "2.5"], obj=operations, catch_exceptions=False)

    operations.fetch.assert_called_once_with(2.5)


@pytest.mark.parametrize("input_name", ("tests/fixtures/github/healthy.json", "-"))
def test_github_status_when_offline_input_is_used_returns_validated_code(document: bytes, input_name: str) -> None:
    source = GitHubSource(Mock(spec=SummaryOpener))

    result = CliRunner().invoke(
        mysign, ["github", "status", "--input", input_name], input=document, obj=source, catch_exceptions=False
    )

    assert result.stdout == "none\n"


@pytest.mark.parametrize("input_name", ("tests/fixtures/github/healthy.json", "-"))
def test_github_status_when_offline_input_is_used_calls_no_fetch(document: bytes, input_name: str) -> None:
    opener = Mock(spec=SummaryOpener)
    source = GitHubSource(opener)

    CliRunner().invoke(
        mysign, ["github", "status", "--input", input_name], input=document, obj=source, catch_exceptions=False
    )

    opener.assert_not_called()


def test_github_status_when_stdin_is_selected_calls_reader_with_input_stream(operations: Mock) -> None:
    CliRunner().invoke(mysign, ["github", "status", "--input", "-"], input=b"saved summary", obj=operations)

    assert operations.read.call_args.args[0].getvalue() == b"saved summary"


@pytest.mark.parametrize(
    "arguments",
    (
        ["--unknown"],
        ["--timeout", "0"],
        ["--timeout", "-1"],
        ["--timeout", "nan"],
        ["--timeout", "inf"],
        ["--timeout", "-inf"],
    ),
)
def test_github_status_when_options_are_invalid_returns_usage_error(arguments: list[str], operations: Mock) -> None:
    result = CliRunner().invoke(mysign, ["github", "status", *arguments], obj=operations)

    assert result.exit_code == 2


@pytest.mark.parametrize("timeout", ("0", "-1", "nan", "inf", "-inf"))
def test_github_status_when_timeout_is_invalid_calls_no_operations(timeout: str, operations: Mock) -> None:
    CliRunner().invoke(mysign, ["github", "status", "--timeout", timeout], obj=operations)

    assert operations.mock_calls == []


@pytest.mark.parametrize("arguments", (["--help"], ["github", "--help"], ["github", "status", "--help"]))
def test_github_status_when_help_is_requested_calls_no_operations(arguments: list[str], operations: Mock) -> None:
    CliRunner().invoke(mysign, arguments, obj=operations, catch_exceptions=False)

    assert operations.mock_calls == []


@pytest.mark.parametrize(
    "error", (OSError("read failed"), TimeoutError("timed out"), URLError("DNS failed"), IncompleteRead(b"partial"))
)
def test_github_status_when_fetch_fails_returns_nonzero(operations: Mock, error: Exception) -> None:
    operations.fetch.side_effect = error

    result = CliRunner().invoke(mysign, ["github", "status"], obj=operations)

    assert result.exit_code == 1


@pytest.mark.parametrize("operation", ("fetch", "read"))
def test_github_status_when_source_fails_returns_no_code(operations: Mock, operation: str) -> None:
    getattr(operations, operation).side_effect = ValueError("invalid summary")
    arguments = ["github", "status", *(["--input", "-"] if operation == "read" else [])]

    result = CliRunner().invoke(mysign, arguments, obj=operations, input=b"data")

    assert result.stdout == ""


def test_github_status_when_source_fails_returns_error_on_stderr(operations: Mock) -> None:
    operations.fetch.side_effect = OSError("read failed")

    result = CliRunner().invoke(mysign, ["github", "status"], obj=operations)

    assert result.stderr == "Error: Cannot read GitHub status: read failed\n"


@pytest.mark.parametrize(
    "policy_arguments", ((), ("--policy", "tests/fixtures/github/default-services.toml")), ids=("indicator", "services")
)
@pytest.mark.parametrize(
    "document",
    (b"not json", b'{"status":{"indicator":"none"}}', b" " * (MAX_SUMMARY_BYTES + 1)),
    ids=("malformed", "incomplete", "oversize"),
)
def test_github_status_when_offline_summary_is_invalid_returns_no_code(
    policy_arguments: tuple[str, ...], document: bytes
) -> None:
    source = GitHubSource(Mock(spec=SummaryOpener))

    result = CliRunner().invoke(
        mysign, ["github", "status", *policy_arguments, "--input", "-"], obj=source, input=document
    )

    assert (result.exit_code, result.stdout) == (1, "")


def test_github_status_when_file_is_missing_returns_no_code(tmp_path: Path) -> None:
    result = CliRunner().invoke(mysign, ["github", "status", "--input", str(tmp_path / "missing.json")])

    assert (result.exit_code, result.stdout) == (2, "")


def test_github_status_when_fetch_is_incomplete_returns_no_code() -> None:
    opener = Mock(spec=SummaryOpener, return_value=BytesIO(b'{"status":{"indicator":"none"}}'))
    source = GitHubSource(opener)

    result = CliRunner().invoke(mysign, ["github", "status"], obj=source)

    assert (result.exit_code, result.stdout) == (1, "")


@pytest.mark.parametrize(
    ("name", "expected"),
    (
        ("healthy", "ok"),
        ("actions-only", "actions-outage"),
        ("unrelated-outage", "degraded"),
        ("simultaneous-outages", "widespread-outage"),
        ("widespread-outages", "widespread-outage"),
        ("maintenance", "degraded"),
    ),
)
def test_github_status_when_synthetic_example_is_selected_returns_policy_code(name: str, expected: str) -> None:
    source = GitHubSource(Mock(spec=SummaryOpener))

    result = CliRunner().invoke(
        mysign,
        [
            "github",
            "status",
            "--policy",
            "tests/fixtures/github/default-services.toml",
            "--input",
            f"tests/fixtures/github/{name}.json",
        ],
        obj=source,
        catch_exceptions=False,
    )

    assert result.stdout == f"{expected}\n"


@pytest.mark.parametrize(
    "config",
    (
        'mode = "services"\n[codes]\nhealthy = "ready"\n',
        'mode = "indicator"\n',
        '[codes]\nhealthy = "ready"\n',
    ),
    ids=("services", "explicit-indicator", "default-indicator"),
)
def test_github_status_when_policy_is_supplied_with_stdin_returns_configured_code(
    document: bytes, tmp_path: Path, config: str
) -> None:
    policy_file = tmp_path / "policy.toml"
    policy_file.write_text(config)
    source = GitHubSource(Mock(spec=SummaryOpener))

    result = CliRunner().invoke(
        mysign, ["github", "status", "--policy", str(policy_file), "--input", "-"], obj=source, input=document
    )

    assert result.stdout == ("ready\n" if 'mode = "services"' in config else "none\n")


@pytest.mark.parametrize(
    "config", (b"not toml", b"\xff", b'mode = "unknown"', b"outage_threshold = 0", b"unknown = true")
)
def test_github_status_when_policy_is_invalid_returns_no_code(operations: Mock, tmp_path: Path, config: bytes) -> None:
    policy_file = tmp_path / "policy.toml"
    policy_file.write_bytes(config)

    result = CliRunner().invoke(mysign, ["github", "status", "--policy", str(policy_file)], obj=operations)

    assert (result.exit_code, result.stdout) == (1, "")


@pytest.mark.parametrize("config", (b"not toml", b'mode = "unknown"', b"outage_threshold = 0"))
def test_github_status_when_policy_is_invalid_calls_no_source(operations: Mock, tmp_path: Path, config: bytes) -> None:
    policy_file = tmp_path / "policy.toml"
    policy_file.write_bytes(config)

    CliRunner().invoke(mysign, ["github", "status", "--policy", str(policy_file)], obj=operations)

    assert operations.mock_calls == []


def test_github_status_when_policy_file_is_missing_calls_no_source(operations: Mock, tmp_path: Path) -> None:
    CliRunner().invoke(mysign, ["github", "status", "--policy", str(tmp_path / "missing.toml")], obj=operations)

    assert operations.mock_calls == []


def test_github_status_when_policy_file_is_missing_returns_no_code(operations: Mock, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        mysign, ["github", "status", "--policy", str(tmp_path / "missing.toml")], obj=operations
    )

    assert (result.exit_code, result.stdout) == (2, "")


def test_github_status_when_priority_service_is_missing_returns_no_code(document: bytes, tmp_path: Path) -> None:
    policy_file = tmp_path / "policy.toml"
    policy_file.write_text('mode = "services"\npriority_service_ids = ["absent"]\n')
    source = GitHubSource(Mock(spec=SummaryOpener))

    result = CliRunner().invoke(
        mysign, ["github", "status", "--policy", str(policy_file), "--input", "-"], obj=source, input=document
    )

    assert (result.exit_code, result.stdout) == (1, "")


@pytest.mark.parametrize(
    ("config", "outage_index", "expected"),
    (
        (
            'mode = "services"\npriority_service_ids = ["example-api"]\n[codes]\npriority_outage = "api-down"\n',
            1,
            "api-down",
        ),
        ('mode = "services"\noutage_threshold = 1\n[codes]\nwidespread_outage = "many-down"\n', 0, "many-down"),
        ('mode = "services"\n[codes]\nhealthy = "ready"\n', None, "ready"),
    ),
    ids=("custom-priority", "custom-threshold", "custom-code"),
)
def test_github_status_when_supplied_policy_changes_classification_returns_configured_code(
    operations: Mock, tmp_path: Path, config: str, outage_index: int | None, expected: str
) -> None:
    policy_file = tmp_path / "policy.toml"
    policy_file.write_text(config)
    summary = operations.fetch.return_value
    if outage_index is not None:
        components = tuple(
            component.model_copy(update={"status": ComponentStatus.MAJOR_OUTAGE})
            if index == outage_index
            else component
            for index, component in enumerate(summary.components)
        )
        operations.fetch.return_value = summary.model_copy(update={"components": components})

    result = CliRunner().invoke(mysign, ["github", "status", "--policy", str(policy_file)], obj=operations)

    assert result.stdout == f"{expected}\n"
