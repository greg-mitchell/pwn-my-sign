import json
from contextlib import AbstractContextManager
from email.message import Message
from http.client import IncompleteRead
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, Mock
from urllib.error import HTTPError, URLError

import pytest

from greg_mitchell.pwn_my_sign.github.interpretation import status_code
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
from greg_mitchell.pwn_my_sign.github.policy import IndicatorPolicy, ServicePolicy
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
        (("operational", "operational", "operational"), "none", "ok"),
        (("partial_outage", "operational", "operational"), "critical", "actions-outage"),
        (("major_outage", "operational", "operational"), "critical", "actions-outage"),
        (("major_outage", "degraded_performance", "operational"), "major", "actions-outage"),
        (("operational", "major_outage", "operational"), "major", "degraded"),
        (("partial_outage", "major_outage", "operational"), "major", "widespread-outage"),
        (("operational", "partial_outage", "major_outage"), "critical", "widespread-outage"),
        (("operational", "operational", "operational"), "critical", "degraded"),
        (("operational", "degraded_performance", "operational"), "none", "degraded"),
        (("operational", "under_maintenance", "operational"), "none", "degraded"),
    ),
)
def test_status_code_when_services_report_health_returns_policy_code(
    summary: Summary, service_policy: ServicePolicy, states: tuple[str, ...], rollup: str, expected: str
) -> None:
    components = tuple(
        component.model_copy(update={"status": ComponentStatus(state)})
        for component, state in zip(summary.components, states, strict=True)
    )
    summary = summary.model_copy(update={"components": components, "status": Status(indicator=Rollup(rollup))})

    result = status_code(summary, service_policy)

    assert result == expected


@pytest.mark.parametrize(("showcase", "group"), ((False, False), (True, True)))
def test_status_code_when_outage_is_hidden_or_group_returns_priority_outage(
    summary: Summary, service_policy: ServicePolicy, showcase: bool, group: bool
) -> None:
    actions = summary.components[0].model_copy(update={"status": ComponentStatus.MAJOR_OUTAGE})
    other = Component(id="hidden", status=ComponentStatus.MAJOR_OUTAGE, showcase=showcase, group=group)
    summary = summary.model_copy(update={"components": (actions, other)})

    result = status_code(summary, service_policy)

    assert result == "actions-outage"


@pytest.mark.parametrize(("showcase", "group"), ((False, False), (True, True)))
def test_status_code_when_only_hidden_or_group_service_is_impaired_returns_healthy(
    summary: Summary, service_policy: ServicePolicy, showcase: bool, group: bool
) -> None:
    other = Component(id="hidden", status=ComponentStatus.MAJOR_OUTAGE, showcase=showcase, group=group)
    summary = summary.model_copy(update={"components": (*summary.components, other)})

    result = status_code(summary, service_policy)

    assert result == "ok"


@pytest.mark.parametrize("state", (IncidentStatus.INVESTIGATING, IncidentStatus.IDENTIFIED, IncidentStatus.MONITORING))
def test_status_code_when_incident_is_open_with_none_rollup_returns_degraded(
    summary: Summary, service_policy: ServicePolicy, state: IncidentStatus
) -> None:
    incident = Incident(id="incident", status=state, impact=Rollup.CRITICAL)
    summary = summary.model_copy(update={"incidents": (incident,)})

    result = status_code(summary, service_policy)

    assert result == "degraded"


@pytest.mark.parametrize("state", (IncidentStatus.RESOLVED, IncidentStatus.POSTMORTEM))
def test_status_code_when_incident_is_closed_returns_healthy(
    summary: Summary, service_policy: ServicePolicy, state: IncidentStatus
) -> None:
    incident = Incident(id="incident", status=state, impact=Rollup.MAJOR)
    summary = summary.model_copy(update={"incidents": (incident,)})

    result = status_code(summary, service_policy)

    assert result == "ok"


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (MaintenanceStatus.SCHEDULED, "ok"),
        (MaintenanceStatus.IN_PROGRESS, "degraded"),
        (MaintenanceStatus.VERIFYING, "degraded"),
        (MaintenanceStatus.COMPLETED, "ok"),
    ),
)
def test_status_code_when_maintenance_is_reported_returns_code_for_activity(
    summary: Summary, service_policy: ServicePolicy, state: MaintenanceStatus, expected: str
) -> None:
    summary = summary.model_copy(update={"scheduled_maintenances": (Maintenance(id="maintenance", status=state),)})

    result = status_code(summary, service_policy)

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


def test_github_source_fetch_when_called_calls_opener_with_only_accept_header(document: bytes) -> None:
    opener = Mock(spec=SummaryOpener, return_value=BytesIO(document))
    source = GitHubSource(opener)

    source.fetch()

    assert dict(opener.call_args.args[0].header_items()) == {"Accept": "application/json"}


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
def test_status_code_when_priority_service_is_not_visible_leaf_raises_error(
    document: bytes, service_policy: ServicePolicy, field: str, value: bool
) -> None:
    payload = json.loads(document)
    payload["components"][0][field] = value
    summary = Summary.model_validate_json(json.dumps(payload))

    with pytest.raises(ValueError, match="visible leaf"):
        status_code(summary, service_policy)


def test_github_source_read_when_actions_is_absent_returns_provider_summary(document: bytes) -> None:
    payload = json.loads(document)
    payload["components"] = [payload["components"][1]]
    source = GitHubSource()

    result = source.read(BytesIO(json.dumps(payload).encode()))

    assert tuple(component.id for component in result.components) == ("example-api",)


@pytest.mark.parametrize("rollup", tuple(Rollup))
def test_status_code_when_default_policy_is_used_returns_provider_indicator(summary: Summary, rollup: Rollup) -> None:
    summary = summary.model_copy(update={"status": Status(indicator=rollup)})
    policy = IndicatorPolicy()

    result = status_code(summary, policy)

    assert result == rollup


def test_status_code_when_indicator_has_no_actions_returns_provider_indicator(summary: Summary) -> None:
    summary = summary.model_copy(update={"components": summary.components[1:]})
    policy = IndicatorPolicy()

    result = status_code(summary, policy)

    assert result == "none"


@pytest.mark.parametrize(("field", "value"), (("showcase", False), ("group", True)))
def test_status_code_when_indicator_has_hidden_priority_service_returns_provider_indicator(
    summary: Summary, field: str, value: bool
) -> None:
    actions = summary.components[0].model_copy(update={field: value})
    summary = summary.model_copy(update={"components": (actions, *summary.components[1:])})
    policy = IndicatorPolicy()

    result = status_code(summary, policy)

    assert result == "none"


def test_status_code_when_configured_priority_is_missing_raises_error(
    summary: Summary, service_policy: ServicePolicy
) -> None:
    policy = service_policy.model_copy(update={"priority_service_ids": ("absent",)})

    with pytest.raises(ValueError, match="absent"):
        status_code(summary, policy)


def test_status_code_when_any_configured_priority_is_missing_raises_error(
    summary: Summary, service_policy: ServicePolicy
) -> None:
    policy = service_policy.model_copy(update={"priority_service_ids": ("example-api", "absent")})

    with pytest.raises(ValueError, match="absent"):
        status_code(summary, policy)


def test_status_code_when_later_configured_priority_has_outage_returns_priority_code(
    summary: Summary, service_policy: ServicePolicy
) -> None:
    outage = summary.components[2].model_copy(update={"status": ComponentStatus.PARTIAL_OUTAGE})
    summary = summary.model_copy(update={"components": (*summary.components[:2], outage)})
    policy = service_policy.model_copy(update={"priority_service_ids": ("example-api", "example-pages")})

    result = status_code(summary, policy)

    assert result == "actions-outage"


def test_status_code_when_threshold_is_raised_returns_priority_before_widespread(
    summary: Summary, service_policy: ServicePolicy
) -> None:
    components = tuple(
        component.model_copy(update={"status": ComponentStatus.MAJOR_OUTAGE}) if index < 2 else component
        for index, component in enumerate(summary.components)
    )
    summary = summary.model_copy(update={"components": components})
    policy = service_policy.model_copy(update={"outage_threshold": 3})

    result = status_code(summary, policy)

    assert result == "actions-outage"


def test_status_code_when_priorities_are_disabled_returns_degraded_for_single_outage(
    summary: Summary, service_policy: ServicePolicy
) -> None:
    actions = summary.components[0].model_copy(update={"status": ComponentStatus.MAJOR_OUTAGE})
    summary = summary.model_copy(update={"components": (actions, *summary.components[1:])})
    policy = service_policy.model_copy(update={"priority_service_ids": ()})

    result = status_code(summary, policy)

    assert result == "degraded"


def test_status_code_when_priorities_are_disabled_returns_healthy_for_arbitrary_services(
    summary: Summary, service_policy: ServicePolicy
) -> None:
    summary = summary.model_copy(update={"components": summary.components[1:]})
    policy = service_policy.model_copy(update={"priority_service_ids": ()})

    result = status_code(summary, policy)

    assert result == "ok"


def test_status_code_when_degraded_code_is_configured_returns_custom_code(
    summary: Summary, service_policy: ServicePolicy
) -> None:
    summary = summary.model_copy(update={"status": Status(indicator=Rollup.MINOR)})
    policy = service_policy.model_copy(
        update={"codes": service_policy.codes.model_copy(update={"degraded": "impaired"})}
    )

    result = status_code(summary, policy)

    assert result == "impaired"


def test_status_code_when_service_policy_has_no_visible_leaves_raises_error(
    summary: Summary, service_policy: ServicePolicy
) -> None:
    components = tuple(component.model_copy(update={"showcase": False}) for component in summary.components)
    summary = summary.model_copy(update={"components": components})
    policy = service_policy.model_copy(update={"priority_service_ids": ()})

    with pytest.raises(ValueError, match="at least one visible leaf"):
        status_code(summary, policy)
