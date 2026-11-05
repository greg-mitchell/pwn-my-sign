from collections.abc import Callable
from io import BytesIO
from unittest.mock import Mock

import pytest

from greg_mitchell.pwn_my_sign.desktop.channel import MessageReader, MessageWriter
from greg_mitchell.pwn_my_sign.desktop.protocol import (
    MAX_RECORD_BYTES,
    Acknowledgment,
    Action,
    ActionKind,
    Notification,
    NotificationKind,
    Phase,
    View,
)
from greg_mitchell.pwn_my_sign.desktop.session import DesktopSession, NotificationError
from greg_mitchell.pwn_my_sign.device.events import UploadEvent


@pytest.fixture
def reader() -> Mock:
    return Mock(
        spec=MessageReader, **{"receive.return_value": Acknowledgment(version=1, id="request-1", submitted=True)}
    )


@pytest.fixture
def writer() -> Mock:
    return Mock(spec=MessageWriter)


@pytest.fixture
def session(reader: Mock, writer: Mock) -> DesktopSession:
    return DesktopSession(reader, writer, 15, clock=Mock(spec=Callable, return_value=0), identify=lambda: "request-1")


def test_show_when_state_changes_calls_writer_with_complete_view(session: DesktopSession, writer: Mock) -> None:
    session.show(Phase.UPDATE_AVAILABLE, "An unsent image is available.", upload_available=True)

    writer.send.assert_called_once_with(
        View(revision=0, phase=Phase.UPDATE_AVAILABLE, message="An unsent image is available.", upload_available=True)
    )


def test_show_when_state_unchanged_calls_writer_only_once(session: DesktopSession, writer: Mock) -> None:
    session.show(Phase.UPDATE_AVAILABLE, "An unsent image is available.", upload_available=True)

    session.show(Phase.UPDATE_AVAILABLE, "An unsent image is available.", upload_available=True)

    assert writer.send.call_count == 1


def test_show_when_visible_state_changes_returns_increasing_revision(session: DesktopSession) -> None:
    session.show(Phase.CHECKING, "Checking.")

    session.show(Phase.UPDATE_AVAILABLE, "An unsent image is available.", upload_available=True)

    assert session.view.revision == 1


def test_show_when_error_contains_controls_and_unicode_returns_bounded_record(reader: Mock) -> None:
    stream = BytesIO()
    session = DesktopSession(reader, MessageWriter(stream), 15)

    session.show(Phase.POLL_FAILED, "\x00" * 1000, last_result="\t" * 1000, error="🪧" * 1000)

    assert len(stream.getvalue()) <= MAX_RECORD_BYTES


def test_notify_when_ack_matches_calls_writer_with_notification(session: DesktopSession, writer: Mock) -> None:
    session.notify(NotificationKind.BUTTON, "Sign ready to upload", "Press the sign's button now.")

    writer.send.assert_called_once_with(
        Notification(
            id="request-1",
            kind=NotificationKind.BUTTON,
            title="Sign ready to upload",
            body="Press the sign's button now.",
        )
    )


def test_notify_when_waiting_calls_reader_with_bounded_timeout(session: DesktopSession, reader: Mock) -> None:
    session.notify(NotificationKind.BUTTON, "Ready", "Press the button.")

    reader.receive.assert_called_once_with(15)


def test_notify_when_old_ack_and_action_arrive_calls_reader_until_matching_ack(
    session: DesktopSession, reader: Mock
) -> None:
    reader.receive.side_effect = [
        Acknowledgment(version=1, id="old-request", submitted=True),
        Action(version=1, action=ActionKind.UPLOAD, revision=0),
        Acknowledgment(version=1, id="request-1", submitted=True),
    ]

    session.notify(NotificationKind.BUTTON, "Ready", "Press the button.")

    assert reader.receive.call_count == 3


def test_notify_when_submission_denied_raises_notification_error(session: DesktopSession, reader: Mock) -> None:
    reader.receive.return_value = Acknowledgment(
        version=1, id="request-1", submitted=False, error="Notifications disabled"
    )

    with pytest.raises(NotificationError, match="Notifications disabled"):
        session.notify(NotificationKind.BUTTON, "Ready", "Press the button.")


def test_notify_when_ack_absent_raises_timeout_error(session: DesktopSession, reader: Mock) -> None:
    reader.receive.return_value = None

    with pytest.raises(TimeoutError, match="did not acknowledge"):
        session.notify(NotificationKind.BUTTON, "Ready", "Press the button.")


def test_notify_when_unmatched_messages_exhaust_deadline_raises_timeout_error(reader: Mock, writer: Mock) -> None:
    reader.receive.return_value = Acknowledgment(version=1, id="old-request", submitted=True)
    session = DesktopSession(reader, writer, 15, clock=Mock(spec=Callable, side_effect=[0, 0, 16]))

    with pytest.raises(TimeoutError, match="did not acknowledge"):
        session.notify(NotificationKind.BUTTON, "Ready", "Press the button.")


def test_notify_when_parent_closes_raises_eof_error(session: DesktopSession, reader: Mock) -> None:
    reader.receive.side_effect = EOFError

    with pytest.raises(EOFError):
        session.notify(NotificationKind.BUTTON, "Ready", "Press the button.")


def test_on_upload_event_when_waiting_returns_button_phase(session: DesktopSession) -> None:
    session.on_upload_event(UploadEvent.WAITING_FOR_BUTTON)

    assert session.view.phase == Phase.WAITING_FOR_BUTTON


def test_on_upload_event_when_button_notification_fails_raises_error(session: DesktopSession, reader: Mock) -> None:
    reader.receive.return_value = Acknowledgment(version=1, id="request-1", submitted=False, error="Permission denied")

    with pytest.raises(NotificationError, match="Permission denied"):
        session.on_upload_event(UploadEvent.WAITING_FOR_BUTTON)


def test_on_upload_event_when_connected_returns_sending_phase(session: DesktopSession) -> None:
    session.on_upload_event(UploadEvent.SENDING)

    assert session.view.phase == Phase.SENDING
