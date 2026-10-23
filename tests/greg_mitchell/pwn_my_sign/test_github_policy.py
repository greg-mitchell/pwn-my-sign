from io import BytesIO
from unittest.mock import Mock

import pytest

from greg_mitchell.pwn_my_sign.github.policy import (
    MAX_POLICY_BYTES,
    IndicatorPolicy,
    OutputCodes,
    PolicyMode,
    ServicePolicy,
    read_policy,
)


def test_read_policy_when_indicator_mode_is_explicit_returns_indicator_policy() -> None:
    result = read_policy(BytesIO(b'mode = "indicator"'))

    assert result == IndicatorPolicy()


def test_read_policy_when_shipped_policy_is_selected_returns_explicit_actions_settings(
    service_policy_document: bytes,
) -> None:
    result = read_policy(BytesIO(service_policy_document))

    assert result == ServicePolicy(
        mode=PolicyMode.SERVICES,
        priority_service_ids=("br0l2tvcx85d",),
        outage_threshold=2,
        codes=OutputCodes(
            healthy="ok", degraded="degraded", priority_outage="actions-outage", widespread_outage="widespread-outage"
        ),
    )


@pytest.mark.parametrize("document", (b"", b'[codes]\nhealthy = "ready"'))
def test_read_policy_when_mode_is_omitted_raises_error(document: bytes) -> None:
    with pytest.raises(ValueError, match="mode"):
        read_policy(BytesIO(document))


def test_read_policy_when_settings_are_supplied_returns_configured_policy() -> None:
    document = b'''
mode = "services"
priority_service_ids = ["service-a", "service-b"]
outage_threshold = 3
[codes]
healthy = "ready"
degraded = "impaired"
priority_outage = "priority-down"
widespread_outage = "many-down"
'''

    result = read_policy(BytesIO(document))

    assert result == ServicePolicy(
        mode=PolicyMode.SERVICES,
        priority_service_ids=("service-a", "service-b"),
        outage_threshold=3,
        codes=OutputCodes(
            healthy="ready", degraded="impaired", priority_outage="priority-down", widespread_outage="many-down"
        ),
    )


def test_read_policy_when_priorities_are_empty_returns_disabled_priority_settings(
    service_policy_document: bytes,
) -> None:
    document = service_policy_document.replace(b'priority_service_ids = ["br0l2tvcx85d"]', b"priority_service_ids = []")

    result = read_policy(BytesIO(document))

    assert isinstance(result, ServicePolicy) and result.priority_service_ids == ()


@pytest.mark.parametrize(
    ("original", "replacement"),
    (
        (b'mode = "services"', b'mode = "unknown"'),
        (b"outage_threshold = 2", b"outage_threshold = 0"),
        (b"outage_threshold = 2", b"outage_threshold = -1"),
        (b"outage_threshold = 2", b"outage_threshold = 2.5"),
        (b"outage_threshold = 2", b"outage_threshold = true"),
        (b"outage_threshold = 2", b'outage_threshold = "2"'),
        (b'priority_service_ids = ["br0l2tvcx85d"]', b'priority_service_ids = [""]'),
        (b'priority_service_ids = ["br0l2tvcx85d"]', b'priority_service_ids = [" "]'),
        (b'priority_service_ids = ["br0l2tvcx85d"]', b'priority_service_ids = ["a", "a"]'),
        (b'priority_service_ids = ["br0l2tvcx85d"]', b"priority_service_ids = [1]"),
        (b"outage_threshold", b"outage_threshhold"),
        (b'healthy = "ok"', b'healthy = ""'),
        (b'healthy = "ok"', b'healthy = "two words"'),
        (b'healthy = "ok"', b'healthy = "line\\nbreak"'),
        (b'healthy = "ok"', b'healthy = "ready\\n"'),
        (b'healthy = "ok"', b'healthy = "degraded"'),
        (b'healthy = "ok"', b'unknown = "ready"'),
        (b"[codes]", b'codes = "ready"'),
    ),
    ids=(
        "mode",
        "zero-threshold",
        "negative-threshold",
        "float-threshold",
        "bool-threshold",
        "string-threshold",
        "empty-id",
        "blank-id",
        "duplicate-id",
        "nonstring-id",
        "unknown-key",
        "empty-code",
        "spaced-code",
        "multiline-code",
        "trailing-newline-code",
        "duplicate-code",
        "unknown-code",
        "invalid-codes-table",
    ),
)
def test_read_policy_when_settings_are_invalid_raises_error(
    service_policy_document: bytes, original: bytes, replacement: bytes
) -> None:
    document = service_policy_document.replace(original, replacement)

    with pytest.raises(ValueError):
        read_policy(BytesIO(document))


@pytest.mark.parametrize("document", (b"not toml", b"\xff"))
def test_read_policy_when_document_is_malformed_raises_error(document: bytes) -> None:
    with pytest.raises(ValueError):
        read_policy(BytesIO(document))


@pytest.mark.parametrize(
    "settings", (b"priority_service_ids = []", b"outage_threshold = 2", b'[codes]\nhealthy = "ready"')
)
def test_read_policy_when_indicator_file_contains_service_settings_raises_error(settings: bytes) -> None:
    document = b'mode = "indicator"\n' + settings

    with pytest.raises(ValueError):
        read_policy(BytesIO(document))


def test_read_policy_when_stream_fails_raises_read_error() -> None:
    stream = Mock(spec=BytesIO)
    stream.read.side_effect = OSError("policy read failed")

    with pytest.raises(OSError, match="policy read failed"):
        read_policy(stream)


def test_read_policy_when_stream_returns_partial_chunks_returns_complete_policy() -> None:
    stream = Mock(spec=BytesIO)
    stream.read.side_effect = (b'mode = "', b'indicator"', b"")

    result = read_policy(stream)

    assert result == IndicatorPolicy()


def test_read_policy_when_document_fills_limit_returns_policy() -> None:
    document = b'mode = "indicator"\n'
    padded = document + b" " * (MAX_POLICY_BYTES - len(document))

    result = read_policy(BytesIO(padded))

    assert result == IndicatorPolicy()


def test_read_policy_when_document_exceeds_limit_raises_error() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        read_policy(BytesIO(b" " * (MAX_POLICY_BYTES + 1)))


def test_read_policy_when_document_exceeds_limit_calls_bounded_reader() -> None:
    stream = Mock(spec=BytesIO)
    stream.read.return_value = b" " * (MAX_POLICY_BYTES + 1)

    with pytest.raises(ValueError):
        read_policy(stream)

    stream.read.assert_called_once_with(MAX_POLICY_BYTES + 1)


def test_read_policy_when_service_setting_is_omitted_raises_error(incomplete_service_policy_document: bytes) -> None:
    with pytest.raises(ValueError):
        read_policy(BytesIO(incomplete_service_policy_document))
