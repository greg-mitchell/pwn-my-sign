from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

MAX_RECORD_BYTES = 16 * 1024
Text = Annotated[str, Field(max_length=1000)]
Token = Annotated[str, Field(min_length=1, max_length=128)]
Revision = Annotated[int, Field(ge=0, strict=True)]


class Phase(StrEnum):
    STARTING = "starting"
    CHECKING = "checking"
    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    PREPARING_UPLOAD = "preparing_upload"
    WAITING_FOR_BUTTON = "waiting_for_button"
    SENDING = "sending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    POLL_FAILED = "poll_failed"
    UPLOAD_FAILED = "upload_failed"


class NotificationKind(StrEnum):
    UPDATE_AVAILABLE = "update_available"
    BUTTON = "button"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionKind(StrEnum):
    UPLOAD = "upload"
    CHECK = "check"


class Record(BaseModel):
    """A versioned immutable message at the desktop process boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1


class View(Record):
    type: Literal["view"] = "view"
    revision: Revision
    phase: Phase
    message: Text
    upload_available: bool = False
    retained: bool = False
    last_check: str | None = None
    last_result: Text | None = None
    error: Text | None = None


class Notification(Record):
    type: Literal["notification"] = "notification"
    id: Token
    kind: NotificationKind
    title: Annotated[str, Field(max_length=100)]
    body: Text


class Acknowledgment(Record):
    version: Literal[1]
    type: Literal["ack"] = "ack"
    id: Token
    submitted: Annotated[bool, Field(strict=True)]
    error: Text | None = None


class Action(Record):
    version: Literal[1]
    type: Literal["action"] = "action"
    action: ActionKind
    revision: Revision


Incoming = Action | Acknowledgment
Outgoing = View | Notification
INCOMING = TypeAdapter[Incoming](Annotated[Incoming, Field(discriminator="type")])
