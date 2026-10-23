from io import BytesIO
from unittest.mock import Mock

import pytest

from greg_mitchell.pwn_my_sign.github.policy import MAX_POLICY_BYTES, OutputCodes, PolicyMode, StatusPolicy, read_policy


def test_read_policy_when_settings_are_empty_returns_indicator_defaults() -> None:
    result = read_policy(BytesIO(b""))

    assert result == StatusPolicy()


def test_read_policy_when_service_mode_is_selected_returns_service_defaults() -> None:
    result = read_policy(BytesIO(b'mode = "services"'))

    assert result == StatusPolicy(mode=PolicyMode.SERVICES)


def test_read_policy_when_codes_are_set_without_mode_returns_indicator_mode() -> None:
    result = read_policy(BytesIO(b'[codes]\nhealthy = "ready"'))

    assert result.mode == PolicyMode.INDICATOR


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

    assert result == StatusPolicy(
        mode=PolicyMode.SERVICES,
        priority_service_ids=("service-a", "service-b"),
        outage_threshold=3,
        codes=OutputCodes(
            healthy="ready", degraded="impaired", priority_outage="priority-down", widespread_outage="many-down"
        ),
    )


def test_read_policy_when_priorities_are_empty_returns_disabled_priority_settings() -> None:
    result = read_policy(BytesIO(b'mode = "services"\npriority_service_ids = []'))

    assert result.priority_service_ids == ()


@pytest.mark.parametrize(
    "document",
    (
        b"not toml",
        b"\xff",
        b'mode = "unknown"',
        b"outage_threshold = 0",
        b"outage_threshold = -1",
        b"outage_threshold = 2.5",
        b"outage_threshold = true",
        b'outage_threshold = "2"',
        b'priority_service_ids = [""]',
        b'priority_service_ids = [" "]',
        b'priority_service_ids = ["a", "a"]',
        b"priority_service_ids = [1]",
        b"outage_threshhold = 2",
        b'[codes]\nhealthy = ""',
        b'[codes]\nhealthy = "two words"',
        b'[codes]\nhealthy = "line\\nbreak"',
        b'[codes]\nhealthy = "ready\\n"',
        b'[codes]\nhealthy = "degraded"',
        b'[codes]\nunknown = "ready"',
        b'codes = "ready"',
    ),
    ids=(
        "malformed",
        "encoding",
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
def test_read_policy_when_settings_are_invalid_raises_error(document: bytes) -> None:
    with pytest.raises(ValueError):
        read_policy(BytesIO(document))


def test_read_policy_when_stream_fails_raises_read_error() -> None:
    stream = Mock(spec=BytesIO)
    stream.read.side_effect = OSError("policy read failed")

    with pytest.raises(OSError, match="policy read failed"):
        read_policy(stream)


def test_read_policy_when_stream_returns_partial_chunks_returns_complete_policy() -> None:
    stream = Mock(spec=BytesIO)
    stream.read.side_effect = (b'mode = "', b'services"', b"")

    result = read_policy(stream)

    assert result == StatusPolicy(mode=PolicyMode.SERVICES)


def test_read_policy_when_document_fills_limit_returns_policy() -> None:
    result = read_policy(BytesIO(b" " * MAX_POLICY_BYTES))

    assert result == StatusPolicy()


def test_read_policy_when_document_exceeds_limit_raises_error() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        read_policy(BytesIO(b" " * (MAX_POLICY_BYTES + 1)))


def test_read_policy_when_document_exceeds_limit_calls_bounded_reader() -> None:
    stream = Mock(spec=BytesIO)
    stream.read.return_value = b" " * (MAX_POLICY_BYTES + 1)

    with pytest.raises(ValueError):
        read_policy(stream)

    stream.read.assert_called_once_with(MAX_POLICY_BYTES + 1)
