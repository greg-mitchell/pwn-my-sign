from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from time import monotonic

from bleak.exc import BleakError

from greg_mitchell.pwn_my_sign.desktop.config import DesktopSettings
from greg_mitchell.pwn_my_sign.desktop.instance import DesktopInstance
from greg_mitchell.pwn_my_sign.desktop.protocol import Action, ActionKind, NotificationKind, Phase
from greg_mitchell.pwn_my_sign.desktop.reminders import ReminderStore
from greg_mitchell.pwn_my_sign.desktop.session import DesktopSession
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadOutcome, UploadSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations


def wall_time() -> datetime:
    """Record successful checks independently of monotonic scheduling deadlines."""
    return datetime.now(UTC)


class DesktopController:
    """Run one desktop workflow with explicit actions and acknowledged notifications."""

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
        self._last_check: str | None = None
        self._last_result: str | None = None
        self._deadline = 0.0

    def run(self, settings: DesktopSettings) -> None:
        """Poll until the native parent closes or interruption unwinds active work."""
        with self._instance.hold():
            try:
                self._show(Phase.STARTING, "Starting sign workflow.")
                self._discard_ready()
                self._poll(settings)
                while True:
                    message = self._session.reader.receive(max(0, self._deadline - self._clock()))
                    if message is None:
                        self._discard_ready()
                        self._poll(settings)
                    elif isinstance(message, Action) and message.revision == self._session.view.revision:
                        if message.action == ActionKind.UPLOAD and self._session.view.upload_available:
                            self._upload(settings)
                            self._discard_ready()
                            self._poll(settings)
                        elif message.action == ActionKind.CHECK:
                            self._discard_ready()
                            self._poll(settings)
            except EOFError:
                return

    def _discard_ready(self) -> None:
        # Drain buffered actions before new work so a vanished parent cannot keep polling.
        while self._session.reader.receive(0) is not None:
            pass

    def _poll(self, settings: DesktopSettings) -> None:
        self._show(Phase.CHECKING, "Checking desired image.")
        try:
            self._workflow.poll(PollSettings(command=settings.command))
            image = self._workflow.state.pending()
            sent = self._workflow.state.is_sent(image)
        except (OSError, ValueError) as error:
            self._report(f"Polling failed: {error}")
            retained = self._retained_available()
            self._show(
                Phase.POLL_FAILED,
                "Polling failed; retained image is available for manual upload." if retained else "Polling failed.",
                upload_available=retained,
                retained=retained,
                error=str(error),
            )
        else:
            self._last_check = self._now().isoformat()
            if sent:
                self._show(Phase.UP_TO_DATE, "The latest desired image has already been sent.")
                self._remember(None)
            else:
                fingerprint = sha256(image).hexdigest()
                try:
                    notified = self._reminders.fingerprint() == fingerprint
                except (OSError, ValueError) as error:
                    self._presentation_error(f"Reminder history failed: {error}")
                else:
                    if not notified and self._notify(
                        NotificationKind.UPDATE_AVAILABLE,
                        "Sign update available",
                        "An unsent image is ready. Use Upload in the sign menu.",
                    ):
                        self._remember(fingerprint)
                self._show(
                    Phase.UPDATE_AVAILABLE,
                    "An unsent image is available.",
                    upload_available=True,
                    error=self._session.view.error,
                )
        self._deadline = self._clock() + settings.interval

    def _retained_available(self) -> bool:
        try:
            return not self._workflow.state.is_sent(self._workflow.state.pending())
        except (OSError, ValueError) as error:
            self._report(f"Retained image is unavailable: {error}")
            return False

    def _upload(self, settings: DesktopSettings) -> None:
        self._show(Phase.PREPARING_UPLOAD, "Preparing the pending image for upload.")
        try:
            outcome = self._workflow.upload(UploadSettings(device=settings.device))
        except (OSError, ValueError, BleakError) as error:
            self._last_result = f"Upload failed: {error}"[:1000]
            self._show(
                Phase.UPLOAD_FAILED, "Upload failed; use Upload to retry after the next check.", error=str(error)
            )
            self._report(self._last_result)
            self._notify(NotificationKind.FAILED, "Sign upload failed", self._last_result)
        else:
            if outcome == UploadOutcome.COMPLETED:
                self._last_result = "Transfer calls completed; check the sign to confirm its image."
                self._show(Phase.COMPLETED, self._last_result)
                self._notify(NotificationKind.COMPLETED, "Sign transfer completed", self._last_result)
            else:
                self._last_result = "The latest desired image has already been sent."
                self._show(Phase.SKIPPED, self._last_result)
                self._notify(NotificationKind.COMPLETED, "Sign is up to date", self._last_result)

    def _remember(self, fingerprint: str | None) -> None:
        try:
            self._reminders.remember(fingerprint)
        except (OSError, ValueError) as error:
            self._presentation_error(f"Reminder history failed: {error}")

    def _notify(self, kind: NotificationKind, title: str, body: str) -> bool:
        try:
            self._session.notify(kind, title, body)
        except (OSError, ValueError) as error:
            self._presentation_error(f"Notification failed: {error}")
            return False
        return True

    def _presentation_error(self, error: str) -> None:
        self._report(error)
        view = self._session.view
        self._show(
            view.phase, view.message, upload_available=view.upload_available, retained=view.retained, error=error
        )

    def _show(
        self,
        phase: Phase,
        message: str,
        *,
        upload_available: bool = False,
        retained: bool = False,
        error: str | None = None,
    ) -> None:
        self._session.show(
            phase,
            message,
            upload_available=upload_available,
            retained=retained,
            last_check=self._last_check,
            last_result=self._last_result,
            error=error,
        )
