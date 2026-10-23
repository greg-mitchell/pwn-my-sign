import json
from contextlib import AbstractContextManager
from email.message import Message
from http.client import IncompleteRead
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, Mock
from urllib.error import HTTPError, URLError

import pytest

from greg_mitchell.pwn_my_sign.github.interpretation import TeamStatus, team_status
from greg_mitchell.pwn_my_sign.github.models import (
    Component,
    ComponentStatus,
    Incident,
    IncidentStatus,
    Maintenance,
    MaintenanceStatus,
    Rollup,
    Status,
    Summary,
)
from greg_mitchell.pwn_my_sign.github.source import MAX_SUMMARY_BYTES, SUMMARY_URL, GitHubSource, SummaryOpener


@pytest.fixture
def document() -> bytes:
    return Path("tests/fixtures/github/healthy.json").read_bytes()


@pytest.fixture
def summary(document: bytes) -> Summary:
    return Summary.model_validate_json(document)


@pytest.mark.parametrize(
    ("states", "rollup", "expected"),
    (
        (("operational", "operational", "operational"), "none", TeamStatus.OK),
        (("partial_outage", "operational", "operational"), "critical", TeamStatus.ACTIONS_OUTAGE),
        (("major_outage", "operational", "operational"), "critical", TeamStatus.ACTIONS_OUTAGE),
        (("major_outage", "degraded_performance", "operational"), "major", TeamStatus.ACTIONS_OUTAGE),
        (("operational", "major_outage", "operational"), "major", TeamStatus.DEGRADED),
        (("partial_outage", "major_outage", "operational"), "major", TeamStatus.WIDESPREAD_OUTAGE),
        (("operational", "partial_outage", "major_outage"), "critical", TeamStatus.WIDESPREAD_OUTAGE),
        (("operational", "operational", "operational"), "critical", TeamStatus.DEGRADED),
        (("operational", "degraded_performance", "operational"), "none", TeamStatus.DEGRADED),
        (("operational", "under_maintenance", "operational"), "none", TeamStatus.DEGRADED),
    ),
)
def test_team_status_when_services_report_health_returns_team_code(
    summary: Summary, states: tuple[str, ...], rollup: str, expected: TeamStatus
) -> None:
    components = tuple(
        component.model_copy(update={"status": ComponentStatus(state)})
        for component, state in zip(summary.components, states, strict=True)
    )
    summary = summary.model_copy(update={"components": components, "status": Status(indicator=Rollup(rollup))})

    result = team_status(summary)

    assert result == expected


@pytest.mark.parametrize(("showcase", "group"), ((False, False), (True, True)))
def test_team_status_when_outage_is_hidden_or_group_returns_actions_outage(
    summary: Summary, showcase: bool, group: bool
) -> None:
    actions = summary.components[0].model_copy(update={"status": ComponentStatus.MAJOR_OUTAGE})
    other = Component(id="hidden", status=ComponentStatus.MAJOR_OUTAGE, showcase=showcase, group=group)
    summary = summary.model_copy(update={"components": (actions, other)})

    result = team_status(summary)

    assert result == TeamStatus.ACTIONS_OUTAGE


@pytest.mark.parametrize(("showcase", "group"), ((False, False), (True, True)))
def test_team_status_when_only_hidden_or_group_service_is_impaired_returns_ok(
    summary: Summary, showcase: bool, group: bool
) -> None:
    other = Component(id="hidden", status=ComponentStatus.MAJOR_OUTAGE, showcase=showcase, group=group)
    summary = summary.model_copy(update={"components": (*summary.components, other)})

    result = team_status(summary)

    assert result == TeamStatus.OK


@pytest.mark.parametrize("state", (IncidentStatus.INVESTIGATING, IncidentStatus.IDENTIFIED, IncidentStatus.MONITORING))
def test_team_status_when_incident_is_open_with_none_rollup_returns_degraded(
    summary: Summary, state: IncidentStatus
) -> None:
    incident = Incident(id="incident", status=state, impact=Rollup.CRITICAL)
    summary = summary.model_copy(update={"incidents": (incident,)})

    result = team_status(summary)

    assert result == TeamStatus.DEGRADED


@pytest.mark.parametrize("state", (IncidentStatus.RESOLVED, IncidentStatus.POSTMORTEM))
def test_team_status_when_incident_is_closed_returns_ok(summary: Summary, state: IncidentStatus) -> None:
    incident = Incident(id="incident", status=state, impact=Rollup.MAJOR)
    summary = summary.model_copy(update={"incidents": (incident,)})

    result = team_status(summary)

    assert result == TeamStatus.OK


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (MaintenanceStatus.SCHEDULED, TeamStatus.OK),
        (MaintenanceStatus.IN_PROGRESS, TeamStatus.DEGRADED),
        (MaintenanceStatus.VERIFYING, TeamStatus.DEGRADED),
        (MaintenanceStatus.COMPLETED, TeamStatus.OK),
    ),
)
def test_team_status_when_maintenance_is_reported_returns_code_for_activity(
    summary: Summary, state: MaintenanceStatus, expected: TeamStatus
) -> None:
    summary = summary.model_copy(update={"scheduled_maintenances": (Maintenance(id="maintenance", status=state),)})

    result = team_status(summary)

    assert result == expected


def test_github_source_read_when_document_is_complete_returns_validated_summary(
    document: bytes, summary: Summary
) -> None:
    source = GitHubSource()

    result = source.read(BytesIO(document))

    assert result == summary


@pytest.mark.parametrize(
    "document",
    (
        b"not json",
        b"\xff",
        b"null",
        b"[]",
        b"{}",
        b'{"status":{"indicator":"none"}}',
    ),
)
def test_github_source_read_when_document_is_incomplete_or_malformed_raises_error(document: bytes) -> None:
    source = GitHubSource()

    with pytest.raises(ValueError):
        source.read(BytesIO(document))


@pytest.mark.parametrize("field", ("status", "components", "incidents", "scheduled_maintenances"))
def test_github_source_read_when_required_section_is_missing_raises_error(document: bytes, field: str) -> None:
    payload = json.loads(document)
    del payload[field]
    source = GitHubSource()

    with pytest.raises(ValueError):
        source.read(BytesIO(json.dumps(payload).encode()))


@pytest.mark.parametrize("field", ("id", "status", "showcase", "group"))
def test_github_source_read_when_component_metadata_is_missing_raises_error(document: bytes, field: str) -> None:
    payload = json.loads(document)
    del payload["components"][0][field]
    source = GitHubSource()

    with pytest.raises(ValueError):
        source.read(BytesIO(json.dumps(payload).encode()))


@pytest.mark.parametrize(
    ("section", "value"),
    (
        ("status", {"indicator": "unknown"}),
        ("status", {}),
        ("components", []),
        ("components", [{"id": "wrong", "status": "operational", "showcase": True, "group": False}]),
        ("incidents", [{}]),
        ("incidents", [{"id": "x", "status": "unknown", "impact": "none"}]),
        ("incidents", [{"id": "x", "status": "investigating", "impact": "unknown"}]),
        ("scheduled_maintenances", [{}]),
        ("scheduled_maintenances", [{"id": "x", "status": "unknown"}]),
    ),
)
def test_github_source_read_when_relevant_data_is_unknown_raises_error(
    document: bytes, section: str, value: object
) -> None:
    payload = json.loads(document)
    payload[section] = value
    source = GitHubSource()

    with pytest.raises(ValueError):
        source.read(BytesIO(json.dumps(payload).encode()))


@pytest.mark.parametrize(("field", "value"), (("status", "unknown"), ("showcase", "false"), ("group", 0)))
def test_github_source_read_when_component_metadata_is_invalid_raises_error(
    document: bytes, field: str, value: object
) -> None:
    payload = json.loads(document)
    payload["components"][0][field] = value
    source = GitHubSource()

    with pytest.raises(ValueError):
        source.read(BytesIO(json.dumps(payload).encode()))


def test_github_source_read_when_component_ids_are_duplicated_raises_error(document: bytes) -> None:
    payload = json.loads(document)
    payload["components"].append(payload["components"][0])
    source = GitHubSource()

    with pytest.raises(ValueError, match="unique"):
        source.read(BytesIO(json.dumps(payload).encode()))


def test_github_source_read_when_extra_metadata_is_present_returns_validated_summary(
    document: bytes, summary: Summary
) -> None:
    payload = json.loads(document)
    payload["page"] = {"updated_at": "synthetic"}
    payload["components"][0]["description"] = "Unused API metadata"
    source = GitHubSource()

    result = source.read(BytesIO(json.dumps(payload).encode()))

    assert result == summary


def test_github_source_read_when_document_fills_limit_returns_summary(document: bytes, summary: Summary) -> None:
    source = GitHubSource()
    padded = document + b" " * (MAX_SUMMARY_BYTES - len(document))

    result = source.read(BytesIO(padded))

    assert result == summary


def test_github_source_read_when_document_exceeds_limit_raises_error() -> None:
    source = GitHubSource()

    with pytest.raises(ValueError, match="exceeds"):
        source.read(BytesIO(b" " * (MAX_SUMMARY_BYTES + 1)))


def test_github_source_read_when_document_exceeds_limit_calls_bounded_reader() -> None:
    stream = Mock(spec=BytesIO)
    stream.read.return_value = b" " * (MAX_SUMMARY_BYTES + 1)
    source = GitHubSource()

    with pytest.raises(ValueError):
        source.read(stream)

    stream.read.assert_called_once_with(MAX_SUMMARY_BYTES + 1)


def test_github_source_read_when_stream_fails_raises_read_error() -> None:
    stream = Mock(spec=BytesIO)
    stream.read.side_effect = OSError("read failed")
    source = GitHubSource()

    with pytest.raises(OSError, match="read failed"):
        source.read(stream)


def test_github_source_read_when_stream_returns_partial_chunks_returns_complete_summary(
    document: bytes, summary: Summary
) -> None:
    stream = Mock(spec=BytesIO)
    stream.read.side_effect = (document[:10], document[10:], b"")
    source = GitHubSource()

    result = source.read(stream)

    assert result == summary


def test_github_source_fetch_when_response_is_valid_returns_summary(document: bytes, summary: Summary) -> None:
    opener = Mock(spec=SummaryOpener, return_value=BytesIO(document))
    source = GitHubSource(opener)

    result = source.fetch()

    assert result == summary


def test_github_source_fetch_when_timeout_is_selected_calls_opener_with_timeout(document: bytes) -> None:
    opener = Mock(spec=SummaryOpener, return_value=BytesIO(document))
    source = GitHubSource(opener)

    source.fetch(7)

    assert opener.call_args.kwargs == {"timeout": 7}


def test_github_source_fetch_when_called_calls_summary_endpoint(document: bytes) -> None:
    opener = Mock(spec=SummaryOpener, return_value=BytesIO(document))
    source = GitHubSource(opener)

    source.fetch()

    assert opener.call_args.args[0].full_url == SUMMARY_URL


def test_github_source_fetch_when_called_calls_opener_with_json_headers(document: bytes) -> None:
    opener = Mock(spec=SummaryOpener, return_value=BytesIO(document))
    source = GitHubSource(opener)

    source.fetch()

    assert dict(opener.call_args.args[0].header_items()) == {
        "Accept": "application/json",
        "User-agent": "pwn-my-sign/0.1",
    }


@pytest.mark.parametrize("document", (b"invalid", b" " * (MAX_SUMMARY_BYTES + 1)), ids=("malformed", "oversize"))
def test_github_source_fetch_when_document_is_invalid_calls_response_close(document: bytes) -> None:
    response = BytesIO(document)
    opener = Mock(spec=SummaryOpener, return_value=response)
    source = GitHubSource(opener)

    with pytest.raises(ValueError):
        source.fetch()

    assert response.closed


def test_github_source_fetch_when_document_is_valid_calls_response_close(document: bytes) -> None:
    response = BytesIO(document)
    opener = Mock(spec=SummaryOpener, return_value=response)
    source = GitHubSource(opener)

    source.fetch()

    assert response.closed


def test_github_source_fetch_when_read_fails_calls_response_close() -> None:
    response = Mock(spec=BytesIO)
    response.read.side_effect = OSError("failed")
    context = MagicMock(spec=AbstractContextManager)
    context.__enter__.return_value = response
    context.__exit__.return_value = False
    source = GitHubSource(Mock(spec=SummaryOpener, return_value=context))

    with pytest.raises(OSError):
        source.fetch()

    assert context.__exit__.call_count == 1


@pytest.mark.parametrize(
    "error",
    (
        TimeoutError("socket timed out"),
        URLError("DNS failed"),
        HTTPError(SUMMARY_URL, 503, "Unavailable", Message(), None),
        IncompleteRead(b"partial"),
    ),
)
def test_github_source_fetch_when_fetch_fails_raises_original_error(error: Exception) -> None:
    opener = Mock(spec=SummaryOpener, side_effect=error)
    source = GitHubSource(opener)

    with pytest.raises(type(error)):
        source.fetch()


def test_github_source_fetch_when_fetch_fails_calls_opener_without_retry() -> None:
    opener = Mock(spec=SummaryOpener, side_effect=TimeoutError("socket timed out"))
    source = GitHubSource(opener)

    with pytest.raises(TimeoutError):
        source.fetch()

    assert opener.call_count == 1


@pytest.mark.parametrize("timeout", (0, -1, float("nan"), float("inf"), float("-inf")))
def test_github_source_fetch_when_timeout_is_invalid_raises_error(timeout: float) -> None:
    source = GitHubSource(Mock(spec=SummaryOpener))

    with pytest.raises(ValueError, match="positive and finite"):
        source.fetch(timeout)


@pytest.mark.parametrize("timeout", (0, -1, float("nan"), float("inf"), float("-inf")))
def test_github_source_fetch_when_timeout_is_invalid_calls_no_opener(timeout: float) -> None:
    opener = Mock(spec=SummaryOpener)
    source = GitHubSource(opener)

    with pytest.raises(ValueError):
        source.fetch(timeout)

    opener.assert_not_called()


@pytest.mark.parametrize(("field", "value"), (("showcase", False), ("group", True)))
def test_github_source_read_when_actions_is_not_visible_leaf_raises_error(
    document: bytes, field: str, value: bool
) -> None:
    payload = json.loads(document)
    payload["components"][0][field] = value
    source = GitHubSource()

    with pytest.raises(ValueError, match="visible leaf"):
        source.read(BytesIO(json.dumps(payload).encode()))
