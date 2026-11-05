from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from time import monotonic

from bleak.exc import BleakError

from greg_mitchell.pwn_my_sign.desktop.config import DesktopSettings
from greg_mitchell.pwn_my_sign.desktop.instance import DesktopInstance
from greg_mitchell.pwn_my_sign.desktop.machine import (
    DesktopState,
    Effect,
    Event,
    EventKind,
    Failure,
    PollResult,
    transition,
)
from greg_mitchell.pwn_my_sign.desktop.protocol import Action, ActionKind, NotificationKind, Phase
from greg_mitchell.pwn_my_sign.desktop.reminders import ReminderStore
from greg_mitchell.pwn_my_sign.desktop.session import DesktopSession
from greg_mitchell.pwn_my_sign.device.events import UploadEvent
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadOutcome, UploadSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations

ACTION_EVENTS = {ActionKind.CHECK: EventKind.CHECK, ActionKind.UPLOAD: EventKind.UPLOAD}
UPLOAD_EVENTS = {UploadEvent.WAITING_FOR_BUTTON: EventKind.BUTTON_READY, UploadEvent.SENDING: EventKind.SENDING}
UPLOAD_RESULTS = {UploadOutcome.COMPLETED: EventKind.UPLOAD_COMPLETED, UploadOutcome.SKIPPED: EventKind.UPLOAD_SKIPPED}
RESULT_NOTIFICATIONS = {
    Phase.COMPLETED: (NotificationKind.COMPLETED, "Sign transfer completed"),
    Phase.SKIPPED: (NotificationKind.COMPLETED, "Sign is up to date"),
    Phase.UPLOAD_FAILED: (NotificationKind.FAILED, "Sign upload failed"),
}


def wall_time() -> datetime:
    """Record successful checks independently of monotonic scheduling deadlines."""
    return datetime.now(UTC)


class DesktopController:
    """Execute the state machine's effects with acknowledged native notifications."""

    def __init__(
        self,
        workflow: WorkflowOperations,
        session: DesktopSession,
        reminders: ReminderStore,
        instance: DesktopInstance,
        report: Callable[[str], None],
        clock: Callable[[], float] = monotonic,
        now: Callable[[], datetime] = wall_time,
    ) -> None:
        self._workflow = workflow
        self._session = session
        self._reminders = reminders
        self._instance = instance
        self._report = report
        self._clock = clock
        self._now = now
        self._state = DesktopState()
        self._deadline = 0.0
        self._effects: dict[Effect, Callable[[DesktopSettings], None]] = {
            Effect.POLL: self._poll,
            Effect.READ_REMINDER: self._read_reminder,
            Effect.REMEMBER: self._remember,
            Effect.NOTIFY_UPDATE: self._notify_update,
            Effect.UPLOAD: self._upload,
            Effect.NOTIFY_BUTTON: self._notify_button,
            Effect.NOTIFY_RESULT: self._notify_result,
            Effect.SCHEDULE: self._schedule,
            Effect.CHECK_AGAIN: self._check,
            Effect.REPORT: self._report_error,
            Effect.REPORT_POLL: self._report_poll_error,
            Effect.REPORT_UPLOAD: self._report_upload_error,
        }

    def run(self, settings: DesktopSettings) -> None:
        """Poll until parent EOF or interruption unwinds active work and its locks."""
        with self._instance.hold():
            try:
                self._present()
                self._check(settings)
                while True:
                    message = self._session.reader.receive(max(0, self._deadline - self._clock()))
                    if message is None:
                        self._check(settings)
                        continue
                    if isinstance(message, Action) and message.revision == self._session.view.revision:
                        kind = ACTION_EVENTS[message.action]
                        if kind == EventKind.CHECK:
                            self._discard_ready()
                        self._dispatch(Event(kind=kind), settings)
            except EOFError:
                return

    def on_upload_event(self, event: UploadEvent, settings: DesktopSettings) -> None:
        """Keep device progress in the same state machine and gate discovery on its notification."""
        self._dispatch(Event(kind=UPLOAD_EVENTS[event]), settings)

    def _dispatch(self, event: Event, settings: DesktopSettings) -> None:
        decision = transition(self._state, event)
        self._state = decision.state
        if decision.publish:
            self._present()
        for effect in decision.effects:
            self._effects[effect](settings)

    def _present(self) -> None:
        state = self._state
        self._session.show(
            state.phase,
            state.message,
            upload_available=state.upload_available,
            retained=state.retained,
            last_check=state.last_check,
            last_result=state.last_result,
            error=state.error,
        )

    def _discard_ready(self) -> None:
        # Check EOF before new work, even if stale actions were queued during the last operation.
        while self._session.reader.receive(0) is not None:
            pass

    def _check(self, settings: DesktopSettings) -> None:
        self._discard_ready()
        self._dispatch(Event(kind=EventKind.CHECK), settings)

    def _poll(self, settings: DesktopSettings) -> None:
        try:
            self._workflow.poll(PollSettings(command=settings.command))
            image = self._workflow.state.pending()
            sent = self._workflow.state.is_sent(image)
        except (OSError, ValueError) as error:
            event: Event = Failure(kind=EventKind.POLL_FAILED, error=str(error), retained=self._retained_available())
        else:
            event = PollResult(
                kind=EventKind.POLL_SENT if sent else EventKind.POLL_UNSENT,
                checked_at=self._now().isoformat(),
                fingerprint=None if sent else sha256(image).hexdigest(),
            )
        self._dispatch(event, settings)

    def _retained_available(self) -> bool:
        try:
            return not self._workflow.state.is_sent(self._workflow.state.pending())
        except (OSError, ValueError) as error:
            self._report(f"Retained image is unavailable: {error}")
            return False

    def _read_reminder(self, settings: DesktopSettings) -> None:
        try:
            known = self._reminders.fingerprint() == self._state.fingerprint
        except (OSError, ValueError) as error:
            event: Event = Failure(kind=EventKind.HISTORY_FAILED, error=f"Reminder history failed: {error}")
        else:
            event = Event(kind=EventKind.REMINDER_KNOWN if known else EventKind.REMINDER_NEEDED)
        self._dispatch(event, settings)

    def _remember(self, settings: DesktopSettings) -> None:
        try:
            self._reminders.remember(self._state.fingerprint)
        except (OSError, ValueError) as error:
            self._presentation_error(f"Reminder history failed: {error}", settings)

    def _notify_update(self, settings: DesktopSettings) -> None:
        try:
            self._session.notify(
                NotificationKind.UPDATE_AVAILABLE,
                "Sign update available",
                "An unsent image is ready. Use Upload in the sign menu.",
            )
        except (OSError, ValueError) as error:
            event: Event = Failure(kind=EventKind.UPDATE_NOTIFICATION_FAILED, error=f"Notification failed: {error}")
        else:
            event = Event(kind=EventKind.UPDATE_NOTIFIED)
        self._dispatch(event, settings)

    def _upload(self, settings: DesktopSettings) -> None:
        try:
            outcome = self._workflow.upload(UploadSettings(device=settings.device))
        except (OSError, ValueError, BleakError) as error:
            event: Event = Failure(kind=EventKind.UPLOAD_FAILED, error=str(error))
        else:
            event = Event(kind=UPLOAD_RESULTS[outcome])
        self._dispatch(event, settings)

    def _notify_button(self, settings: DesktopSettings) -> None:
        # Submission failure must propagate through the upload observer before discovery begins.
        self._session.notify(NotificationKind.BUTTON, "Sign ready to upload", "Press the sign's button now.")

    def _notify_result(self, settings: DesktopSettings) -> None:
        kind, title = RESULT_NOTIFICATIONS[self._state.phase]
        try:
            self._session.notify(kind, title, self._state.last_result or self._state.message)
        except (OSError, ValueError) as error:
            self._presentation_error(f"Notification failed: {error}", settings)

    def _presentation_error(self, error: str, settings: DesktopSettings) -> None:
        self._dispatch(Failure(kind=EventKind.PRESENTATION_FAILED, error=error), settings)

    def _schedule(self, settings: DesktopSettings) -> None:
        self._deadline = self._clock() + settings.interval

    def _report_error(self, settings: DesktopSettings) -> None:
        self._report(self._state.error or "")

    def _report_poll_error(self, settings: DesktopSettings) -> None:
        self._report(f"Polling failed: {self._state.error}")

    def _report_upload_error(self, settings: DesktopSettings) -> None:
        self._report(self._state.last_result or "")
