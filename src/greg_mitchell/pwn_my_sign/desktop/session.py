from collections.abc import Callable
from time import monotonic
from uuid import uuid4

from greg_mitchell.pwn_my_sign.desktop.channel import MessageReader, MessageWriter
from greg_mitchell.pwn_my_sign.desktop.protocol import (
    Acknowledgment,
    Notification,
    NotificationKind,
    Phase,
    View,
)


def notification_id() -> str:
    """Identify one submission acknowledgment independently of view revisions."""
    return uuid4().hex


def display_text(value: str, limit: int = 1000) -> str:
    """Bound menu text and replace controls before JSON escaping expands them."""
    return "".join(character if character.isprintable() else " " for character in value[:limit])


class NotificationError(ValueError):
    """The native application could not submit the requested notification."""


class DesktopSession:
    """Own changed views and the bounded native notification acknowledgment handshake."""

    def __init__(
        self,
        reader: MessageReader,
        writer: MessageWriter,
        notification_timeout: float,
        clock: Callable[[], float] = monotonic,
        identify: Callable[[], str] = notification_id,
    ) -> None:
        self.reader = reader
        self._writer = writer
        self._timeout = notification_timeout
        self._clock = clock
        self._identify = identify
        self.view = View(revision=0, phase=Phase.STARTING, message="Starting sign workflow.")
        self._emitted = False

    def show(
        self,
        phase: Phase,
        message: str,
        *,
        upload_available: bool = False,
        retained: bool = False,
        last_check: str | None = None,
        last_result: str | None = None,
        error: str | None = None,
    ) -> None:
        """Emit a complete view only when its visible fields change."""
        candidate = View(
            revision=self.view.revision + int(self._emitted),
            phase=phase,
            message=display_text(message),
            upload_available=upload_available,
            retained=retained,
            last_check=display_text(last_check, 128) if last_check else None,
            last_result=display_text(last_result) if last_result else None,
            error=display_text(error) if error else None,
        )
        if self._emitted and candidate.model_dump(exclude={"revision"}) == self.view.model_dump(exclude={"revision"}):
            return
        self.view = candidate
        self._writer.send(candidate)
        self._emitted = True

    def notify(self, kind: NotificationKind, title: str, body: str) -> None:
        """Require a matching successful submission acknowledgment before returning."""
        request = Notification(id=self._identify(), kind=kind, title=display_text(title, 100), body=display_text(body))
        self._writer.send(request)
        deadline = self._clock() + self._timeout
        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError("The desktop application did not acknowledge the notification.")
            message = self.reader.receive(remaining)
            if message is None:
                raise TimeoutError("The desktop application did not acknowledge the notification.")
            if not isinstance(message, Acknowledgment) or message.id != request.id:
                continue
            if not message.submitted:
                raise NotificationError(message.error or "Notification submission was denied.")
            return
