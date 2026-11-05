from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from greg_mitchell.pwn_my_sign.desktop.protocol import Phase


class EventKind(StrEnum):
    CHECK = "check"
    UPLOAD = "upload"
    POLL_SENT = "poll_sent"
    POLL_UNSENT = "poll_unsent"
    POLL_FAILED = "poll_failed"
    REMINDER_KNOWN = "reminder_known"
    REMINDER_NEEDED = "reminder_needed"
    UPDATE_NOTIFIED = "update_notified"
    UPDATE_NOTIFICATION_FAILED = "update_notification_failed"
    HISTORY_FAILED = "history_failed"
    BUTTON_READY = "button_ready"
    SENDING = "sending"
    UPLOAD_COMPLETED = "upload_completed"
    UPLOAD_SKIPPED = "upload_skipped"
    UPLOAD_FAILED = "upload_failed"
    PRESENTATION_FAILED = "presentation_failed"


class Effect(StrEnum):
    POLL = "poll"
    READ_REMINDER = "read_reminder"
    REMEMBER = "remember"
    NOTIFY_UPDATE = "notify_update"
    UPLOAD = "upload"
    NOTIFY_BUTTON = "notify_button"
    NOTIFY_RESULT = "notify_result"
    SCHEDULE = "schedule"
    CHECK_AGAIN = "check_again"
    REPORT = "report"
    REPORT_POLL = "report_poll"
    REPORT_UPLOAD = "report_upload"


MESSAGES = {
    Phase.STARTING: "Starting sign workflow.",
    Phase.CHECKING: "Checking desired image.",
    Phase.UP_TO_DATE: "The latest desired image has already been sent.",
    Phase.UPDATE_AVAILABLE: "An unsent image is available.",
    Phase.PREPARING_UPLOAD: "Preparing the pending image for upload.",
    Phase.WAITING_FOR_BUTTON: "Press the sign's button now.",
    Phase.SENDING: "Sending image to the sign.",
    Phase.COMPLETED: "Transfer calls completed; check the sign to confirm its image.",
    Phase.SKIPPED: "The latest desired image has already been sent.",
    Phase.POLL_FAILED: "Polling failed.",
    Phase.UPLOAD_FAILED: "Upload failed; use Upload to retry after the next check.",
}


class DesktopState(BaseModel):
    """Workflow facts, independent of the last view emitted to the native application."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Phase = Phase.STARTING
    last_check: str | None = None
    last_result: str | None = None
    error: str | None = None
    retained: bool = False
    fingerprint: str | None = None

    @property
    def upload_available(self) -> bool:
        """Offer uploads only for a current or explicitly retained unsent image."""
        return self.phase == Phase.UPDATE_AVAILABLE or (self.phase == Phase.POLL_FAILED and self.retained)

    @property
    def message(self) -> str:
        """Project workflow facts into the menu's status text."""
        if self.phase == Phase.POLL_FAILED and self.retained:
            return "Polling failed; retained image is available for manual upload."
        return MESSAGES[self.phase]


class Event(BaseModel):
    """A control event without operation-specific data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EventKind


class PollResult(Event):
    """A successful check's timestamp and optional unsent image fingerprint."""

    checked_at: str
    fingerprint: str | None = None


class Failure(Event):
    """An operation or presentation failure, optionally retaining an unsent image."""

    error: str
    retained: bool = False


@dataclass(frozen=True)
class Rule:
    """One allowed event, its destination, and ordered side effects."""

    sources: frozenset[Phase]
    event: EventKind
    target: Phase | None
    effects: tuple[Effect, ...] = ()
    publish: bool = True


IDLE = frozenset({Phase.UP_TO_DATE, Phase.UPDATE_AVAILABLE, Phase.POLL_FAILED})
UPLOADING = frozenset({Phase.PREPARING_UPLOAD, Phase.WAITING_FOR_BUTTON, Phase.SENDING})
FINISHED = frozenset({Phase.COMPLETED, Phase.SKIPPED, Phase.UPLOAD_FAILED})
CHECKING = frozenset({Phase.CHECKING})

RULES = (
    Rule(IDLE | FINISHED | {Phase.STARTING}, EventKind.CHECK, Phase.CHECKING, (Effect.POLL,)),
    Rule(IDLE, EventKind.UPLOAD, Phase.PREPARING_UPLOAD, (Effect.UPLOAD,)),
    Rule(CHECKING, EventKind.POLL_SENT, Phase.UP_TO_DATE, (Effect.REMEMBER, Effect.SCHEDULE)),
    Rule(CHECKING, EventKind.POLL_UNSENT, Phase.CHECKING, (Effect.READ_REMINDER,), publish=False),
    Rule(CHECKING, EventKind.POLL_FAILED, Phase.POLL_FAILED, (Effect.REPORT_POLL, Effect.SCHEDULE)),
    Rule(CHECKING, EventKind.REMINDER_KNOWN, Phase.UPDATE_AVAILABLE, (Effect.SCHEDULE,)),
    Rule(CHECKING, EventKind.REMINDER_NEEDED, Phase.CHECKING, (Effect.NOTIFY_UPDATE,), publish=False),
    Rule(CHECKING, EventKind.UPDATE_NOTIFIED, Phase.UPDATE_AVAILABLE, (Effect.REMEMBER, Effect.SCHEDULE)),
    Rule(CHECKING, EventKind.UPDATE_NOTIFICATION_FAILED, Phase.UPDATE_AVAILABLE, (Effect.REPORT, Effect.SCHEDULE)),
    Rule(CHECKING, EventKind.HISTORY_FAILED, Phase.UPDATE_AVAILABLE, (Effect.REPORT, Effect.SCHEDULE)),
    Rule(
        frozenset({Phase.PREPARING_UPLOAD}), EventKind.BUTTON_READY, Phase.WAITING_FOR_BUTTON, (Effect.NOTIFY_BUTTON,)
    ),
    Rule(frozenset({Phase.WAITING_FOR_BUTTON}), EventKind.SENDING, Phase.SENDING),
    Rule(UPLOADING, EventKind.UPLOAD_COMPLETED, Phase.COMPLETED, (Effect.NOTIFY_RESULT, Effect.CHECK_AGAIN)),
    Rule(UPLOADING, EventKind.UPLOAD_SKIPPED, Phase.SKIPPED, (Effect.NOTIFY_RESULT, Effect.CHECK_AGAIN)),
    Rule(
        UPLOADING,
        EventKind.UPLOAD_FAILED,
        Phase.UPLOAD_FAILED,
        (Effect.REPORT_UPLOAD, Effect.NOTIFY_RESULT, Effect.CHECK_AGAIN),
    ),
    Rule(frozenset(Phase), EventKind.PRESENTATION_FAILED, None, (Effect.REPORT,)),
)
TRANSITIONS = {(phase, rule.event): rule for rule in RULES for phase in rule.sources}


@dataclass(frozen=True)
class Decision:
    """The pure result consumed by the controller's effect runner."""

    state: DesktopState
    effects: tuple[Effect, ...] = ()
    publish: bool = True


def transition(state: DesktopState, event: Event) -> Decision:
    """Decide one allowed transition without performing I/O or reading a clock."""
    rule = TRANSITIONS.get((state.phase, event.kind))
    if rule is None or (event.kind == EventKind.UPLOAD and not state.upload_available):
        return Decision(state, publish=False)
    updated = state.model_copy(update={"phase": rule.target or state.phase})
    if isinstance(event, PollResult):
        updated = updated.model_copy(update={"last_check": event.checked_at, "fingerprint": event.fingerprint})
    if isinstance(event, Failure):
        updated = updated.model_copy(update={"error": event.error})
    if event.kind == EventKind.POLL_FAILED and isinstance(event, Failure):
        updated = updated.model_copy(update={"retained": event.retained})
    if event.kind in {EventKind.CHECK, EventKind.UPLOAD}:
        updated = updated.model_copy(update={"error": None, "retained": False})
    if event.kind == EventKind.UPLOAD_FAILED and isinstance(event, Failure):
        updated = updated.model_copy(update={"last_result": f"Upload failed: {event.error}"[:1000]})
    if event.kind in {EventKind.UPLOAD_COMPLETED, EventKind.UPLOAD_SKIPPED}:
        updated = updated.model_copy(update={"last_result": MESSAGES[updated.phase]})
    return Decision(updated, rule.effects, rule.publish)
