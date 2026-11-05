from collections.abc import Callable
from enum import StrEnum
from queue import Empty, Queue
from time import monotonic
from typing import BinaryIO

from greg_mitchell.pwn_my_sign.desktop.protocol import INCOMING, MAX_RECORD_BYTES, Incoming, Outgoing


class InputIssue(StrEnum):
    """Framing diagnostics delivered in order with complete input records."""

    OVERSIZED = "Ignoring oversized desktop message."
    INCOMPLETE = "Ignoring incomplete desktop message at EOF."


type PipeInput = bytes | InputIssue | OSError | EOFError


class LinePump:
    """Feed bounded lines to a queue from one privately owned buffered stream."""

    def __init__(self, stream: BinaryIO, deliver: Callable[[PipeInput], None]) -> None:
        self._stream = stream
        self._deliver = deliver

    def run(self) -> None:
        """Read until EOF or failure, draining oversized records in bounded pieces."""
        try:
            while line := self._stream.readline(MAX_RECORD_BYTES + 1):
                if len(line) > MAX_RECORD_BYTES:
                    while line and not line.endswith(b"\n"):
                        line = self._stream.readline(MAX_RECORD_BYTES + 1)
                    self._deliver(InputIssue.OVERSIZED if line else InputIssue.INCOMPLETE)
                elif not line.endswith(b"\n"):
                    self._deliver(InputIssue.INCOMPLETE)
                else:
                    self._deliver(line)
        except OSError as error:
            self._deliver(error)
            return
        self._deliver(EOFError("The desktop application closed its input pipe."))


class MessageReader:
    """Validate queued JSON lines within one receive deadline."""

    def __init__(
        self,
        messages: Queue[PipeInput],
        report: Callable[[str], None],
        clock: Callable[[], float] = monotonic,
        parent_closed: Callable[[], bool] = lambda: False,
    ) -> None:
        self._messages = messages
        self._report = report
        self._clock = clock
        self._parent_closed = parent_closed
        self._failure: OSError | EOFError | None = None

    def receive(self, timeout: float) -> Incoming | None:
        """Return one valid message, time out, or raise EOFError when the parent closes."""
        if self._failure is not None:
            raise self._failure
        if timeout == 0 and self._parent_closed():
            self._failure = EOFError("The desktop application closed its input pipe.")
            raise self._failure
        deadline = self._clock() + timeout
        while True:
            remaining = deadline - self._clock()
            if timeout > 0 and remaining <= 0:
                return None
            try:
                record = self._messages.get(timeout=max(0, remaining))
            except Empty:
                return None
            if isinstance(record, (OSError, EOFError)):
                self._failure = record
                raise record
            if isinstance(record, InputIssue):
                self._report(record)
                continue
            try:
                return INCOMING.validate_json(record)
            except ValueError as error:
                self._report(f"Ignoring invalid desktop message: {str(error)[:1000]}")


class MessageWriter:
    """Publish complete protocol records on stdout with explicit flushing."""

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def send(self, record: Outgoing) -> None:
        """Write one bounded record without mixing in workflow diagnostics."""
        data = record.model_dump_json().encode("utf-8") + b"\n"
        if len(data) > MAX_RECORD_BYTES:
            raise ValueError("Desktop output record exceeds 16 KiB.")
        self._stream.write(data)
        self._stream.flush()
