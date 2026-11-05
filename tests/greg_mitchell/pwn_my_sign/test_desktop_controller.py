from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from itertools import count
from pathlib import Path
from unittest.mock import Mock

import pytest

from greg_mitchell.pwn_my_sign.desktop.channel import MessageReader, MessageWriter
from greg_mitchell.pwn_my_sign.desktop.config import DesktopSettings
from greg_mitchell.pwn_my_sign.desktop.controller import DesktopController
from greg_mitchell.pwn_my_sign.desktop.instance import DesktopInstance
from greg_mitchell.pwn_my_sign.desktop.protocol import (
    Acknowledgment,
    Action,
    ActionKind,
    Incoming,
    Notification,
    NotificationKind,
    Phase,
    View,
)
from greg_mitchell.pwn_my_sign.desktop.reminders import ReminderStore
from greg_mitchell.pwn_my_sign.desktop.session import DesktopSession
from greg_mitchell.pwn_my_sign.device.events import UploadEvent
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.sender import SnapshotSender
from greg_mitchell.pwn_my_sign.workflow.source import ImageSource
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState


class DesktopHarness:
    """Arrange in-process workflow state and scripted native input without real waits."""

    def __init__(self, directory: Path) -> None:
        self.messages: list[Incoming | None | BaseException | Callable[[], Incoming]] = []
        self.ticks = 0.0
        self.reader = Mock(spec=MessageReader, **{"receive.side_effect": self.receive})
        self.writer = Mock(spec=MessageWriter)
        identifiers = count(1)
        self.session = DesktopSession(
            self.reader, self.writer, 15, clock=lambda: self.ticks, identify=lambda: f"notice-{next(identifiers)}"
        )
        self.report = Mock(spec=Callable)
        self.state = WorkflowState(directory)
        self.source = Mock(spec=ImageSource, **{"image.return_value": b"desired image"})
        self.sender = Mock(spec=SnapshotSender, **{"send.side_effect": self.send})
        self.workflow = WorkflowOperations(self.state, self.source, self.sender, self.report)
        self.reminders = ReminderStore(directory)
        self.controller = DesktopController(
            self.workflow,
            self.session,
            self.reminders,
            DesktopInstance(self.state),
            self.report,
            clock=lambda: self.ticks,
            now=lambda: datetime(2026, 11, 5, 12, tzinfo=UTC),
        )
        self.settings = DesktopSettings(
            command=("/explicit/producer", "literal argument"),
            working_directory=directory,
            state_directory=directory,
            device="test sign",
            interval=30,
        )

    def receive(self, timeout: float) -> Incoming | None:
        if not self.messages:
            raise EOFError
        message = self.messages.pop(0)
        if isinstance(message, BaseException):
            raise message
        if message is None or isinstance(message, (Action, Acknowledgment)):
            return message
        return message()

    def send(self, image: bytes, settings: UploadSettings, report: Callable[[str], None]) -> None:
        self.session.on_upload_event(UploadEvent.WAITING_FOR_BUTTON)
        self.session.on_upload_event(UploadEvent.SENDING)

    def notifications(self) -> tuple[Notification, ...]:
        return tuple(item.args[0] for item in self.writer.send.call_args_list if isinstance(item.args[0], Notification))

    def views(self) -> tuple[View, ...]:
        return tuple(item.args[0] for item in self.writer.send.call_args_list if isinstance(item.args[0], View))

    def ack(self, submitted: bool = True) -> Acknowledgment:
        return Acknowledgment(
            version=1,
            id=self.notifications()[-1].id,
            submitted=submitted,
            error=None if submitted else "Notifications disabled",
        )

    def upload(self) -> Action:
        return Action(version=1, action=ActionKind.UPLOAD, revision=self.session.view.revision)

    def check(self) -> Action:
        return Action(version=1, action=ActionKind.CHECK, revision=self.session.view.revision)


@pytest.fixture
def desktop(tmp_path: Path) -> DesktopHarness:
    return DesktopHarness(tmp_path)


def test_run_when_parent_present_calls_poll_immediately(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    desktop.source.image.assert_called_once_with(PollSettings(command=("/explicit/producer", "literal argument")))


def test_run_when_desired_already_sent_returns_up_to_date_view(desktop: DesktopHarness) -> None:
    desktop.state.record_sent(b"desired image")
    desktop.messages = [None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.session.view.phase == Phase.UP_TO_DATE


def test_run_when_new_unsent_image_calls_update_notification(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    assert tuple(notification.kind for notification in desktop.notifications()) == (NotificationKind.UPDATE_AVAILABLE,)


def test_run_when_update_notification_accepted_returns_persisted_fingerprint(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.reminders.fingerprint() == sha256(b"desired image").hexdigest()


def test_run_when_restarted_with_notified_image_calls_no_notification(desktop: DesktopHarness) -> None:
    desktop.reminders.remember(sha256(b"desired image").hexdigest())
    desktop.messages = [None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.notifications() == ()


def test_run_when_up_to_date_returns_cleared_notification_history(desktop: DesktopHarness) -> None:
    desktop.reminders.remember(sha256(b"desired image").hexdigest())
    desktop.state.record_sent(b"desired image")
    desktop.messages = [None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.reminders.fingerprint() is None


def test_run_when_new_image_replaces_notified_image_calls_new_notification(desktop: DesktopHarness) -> None:
    desktop.reminders.remember(sha256(b"old desired image").hexdigest())
    desktop.messages = [None, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    assert tuple(notification.body for notification in desktop.notifications()) == (
        "An unsent image is ready. Use Upload in the sign menu.",
    )


def test_run_when_update_notification_denied_returns_unchanged_history(desktop: DesktopHarness) -> None:
    desktop.reminders.remember(sha256(b"older image").hexdigest())
    desktop.messages = [None, lambda: desktop.ack(False), EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.reminders.fingerprint() == sha256(b"older image").hexdigest()


def test_run_when_denied_notification_retried_returns_accepted_history(desktop: DesktopHarness) -> None:
    desktop.messages = [None, lambda: desktop.ack(False), None, None, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.reminders.fingerprint() == sha256(b"desired image").hexdigest()


def test_run_when_poll_fails_returns_contextual_retained_upload_view(desktop: DesktopHarness) -> None:
    desktop.state.publish(b"retained image")
    desktop.source.image.side_effect = OSError("Producer failed")
    desktop.messages = [None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.session.view == View(
        revision=2,
        phase=Phase.POLL_FAILED,
        message="Polling failed; retained image is available for manual upload.",
        upload_available=True,
        retained=True,
        error="Producer failed",
    )


def test_run_when_poll_fails_calls_no_fresh_update_notification(desktop: DesktopHarness) -> None:
    desktop.state.publish(b"retained image")
    desktop.source.image.side_effect = OSError("Producer failed")
    desktop.messages = [None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.notifications() == ()


def test_run_when_later_poll_fails_returns_last_successful_check(desktop: DesktopHarness) -> None:
    desktop.source.image.side_effect = [b"desired image", OSError("Producer failed")]
    desktop.messages = [None, desktop.ack, None, None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.session.view.last_check == "2026-11-05T12:00:00+00:00"


def test_run_when_failed_poll_recovers_returns_fresh_update_view(desktop: DesktopHarness) -> None:
    desktop.source.image.side_effect = [OSError("Producer failed"), b"desired image"]
    desktop.messages = [None, None, None, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.session.view.phase == Phase.UPDATE_AVAILABLE


def test_run_when_retained_upload_explicitly_selected_calls_sender_with_retained_snapshot(
    desktop: DesktopHarness,
) -> None:
    desktop.state.publish(b"retained image")
    desktop.source.image.side_effect = OSError("Producer failed")
    desktop.messages = [None, desktop.upload, desktop.ack, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    desktop.sender.send.assert_called_once_with(b"retained image", UploadSettings(device="test sign"), desktop.report)


def test_run_when_stale_upload_selected_calls_no_sender(desktop: DesktopHarness) -> None:
    desktop.messages = [
        None,
        desktop.ack,
        lambda: Action(version=1, action=ActionKind.UPLOAD, revision=desktop.session.view.revision - 1),
        EOFError(),
    ]

    desktop.controller.run(desktop.settings)

    desktop.sender.send.assert_not_called()


def test_run_when_duplicate_actions_follow_failure_calls_sender_only_once(desktop: DesktopHarness) -> None:
    actions: list[Action] = []

    def first_upload() -> Action:
        action = desktop.upload()
        actions.append(action)
        return action

    desktop.sender.send.side_effect = OSError("Transfer failed")
    desktop.messages = [
        None,
        desktop.ack,
        first_upload,
        desktop.ack,
        lambda: actions[0],
        None,
        lambda: actions[0],
        EOFError(),
    ]

    desktop.controller.run(desktop.settings)

    assert desktop.sender.send.call_count == 1


@pytest.mark.parametrize("button_reply", ["denied", "timeout"])
def test_run_when_button_prompt_unacknowledged_returns_previous_sent_image(
    desktop: DesktopHarness, button_reply: str
) -> None:
    desktop.state.record_sent(b"previous sent image")
    desktop.messages = [
        None,
        desktop.ack,
        desktop.upload,
        (lambda: desktop.ack(False)) if button_reply == "denied" else None,
        desktop.ack,
        EOFError(),
    ]

    desktop.controller.run(desktop.settings)

    assert (desktop.state.directory / "last-sent.png").read_bytes() == b"previous sent image"


def test_run_when_parent_closes_during_button_prompt_returns_released_workflow_locks(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, desktop.upload, EOFError()]

    desktop.controller.run(desktop.settings)

    assert list(desktop.state.directory.glob("*.lock")) == []


def test_run_when_transfer_completes_returns_recorded_snapshot(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, desktop.upload, desktop.ack, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.state.is_sent(b"desired image")


def test_run_when_transfer_completes_calls_notification_after_sending_view(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, desktop.upload, desktop.ack, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    assert tuple(view.phase for view in desktop.views()) == (
        Phase.STARTING,
        Phase.CHECKING,
        Phase.UPDATE_AVAILABLE,
        Phase.PREPARING_UPLOAD,
        Phase.WAITING_FOR_BUTTON,
        Phase.SENDING,
        Phase.COMPLETED,
    )


def test_run_when_completed_notification_fails_returns_completed_result(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, desktop.upload, desktop.ack, lambda: desktop.ack(False), EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.session.view.last_result == "Transfer calls completed; check the sign to confirm its image."


def test_run_when_completed_notification_fails_returns_recorded_snapshot(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, desktop.upload, desktop.ack, lambda: desktop.ack(False), EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.state.is_sent(b"desired image")


def test_run_when_another_uploader_already_sent_returns_skipped_phase(desktop: DesktopHarness) -> None:
    def select_upload_after_other_transfer() -> Action:
        desktop.state.record_sent(b"desired image")
        return desktop.upload()

    desktop.messages = [None, desktop.ack, select_upload_after_other_transfer, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.session.view.phase == Phase.SKIPPED


def test_run_when_upload_finishes_calls_poll_before_offering_next_image(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, desktop.upload, desktop.ack, desktop.ack, None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert tuple(view.phase for view in desktop.views())[-3:] == (Phase.COMPLETED, Phase.CHECKING, Phase.UP_TO_DATE)


def test_run_when_parent_already_closed_calls_no_producer(desktop: DesktopHarness) -> None:
    desktop.messages = [EOFError()]

    desktop.controller.run(desktop.settings)

    desktop.source.image.assert_not_called()


def test_run_when_parent_closes_at_poll_deadline_calls_no_second_poll(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.source.image.call_count == 1


def test_run_when_poll_completes_calls_input_with_interval_after_completion(desktop: DesktopHarness) -> None:
    def produce(settings: PollSettings) -> bytes:
        desktop.ticks = 19
        return b"desired image"

    desktop.source.image.side_effect = produce
    desktop.messages = [None, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.reader.receive.call_args.args == (30,)


def test_run_when_check_selected_calls_producer_again(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, desktop.check, None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.source.image.call_count == 2


def test_run_when_reminder_history_unreadable_returns_visible_error(desktop: DesktopHarness) -> None:
    (desktop.state.directory / "desktop-reminder.json").mkdir()
    desktop.messages = [None, EOFError()]

    desktop.controller.run(desktop.settings)

    assert desktop.session.view.error is not None and desktop.session.view.error.startswith("Reminder history failed:")


def test_run_when_update_notification_pending_returns_nonactionable_checking_view(desktop: DesktopHarness) -> None:
    waiting_views: list[tuple[Phase, bool]] = []

    def acknowledge_update() -> Acknowledgment:
        waiting_views.append((desktop.session.view.phase, desktop.session.view.upload_available))
        return desktop.ack()

    desktop.messages = [None, acknowledge_update, EOFError()]

    desktop.controller.run(desktop.settings)

    assert waiting_views == [(Phase.CHECKING, False)]


def test_run_when_update_notification_acknowledged_calls_selected_upload(desktop: DesktopHarness) -> None:
    desktop.messages = [None, desktop.ack, desktop.upload, desktop.ack, desktop.ack, EOFError()]

    desktop.controller.run(desktop.settings)

    desktop.sender.send.assert_called_once_with(b"desired image", UploadSettings(device="test sign"), desktop.report)
