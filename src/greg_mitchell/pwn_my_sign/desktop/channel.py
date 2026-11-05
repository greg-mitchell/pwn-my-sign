import os
import select
from collections.abc import Callable
from time import monotonic
from typing import BinaryIO

from greg_mitchell.pwn_my_sign.desktop.protocol import INCOMING, MAX_RECORD_BYTES, Incoming, Outgoing


def readable(descriptor: int, timeout: float) -> bool:
    """Wait for pipe input without buffering data outside the message reader."""
    ready, _, _ = select.select([descriptor], [], [], timeout)
    return bool(ready)


class MessageReader:
    """Read bounded newline-delimited UTF-8 JSON using one owned byte buffer."""

    def __init__(
        self,
        descriptor: int,
        report: Callable[[str], None],
        ready: Callable[[int, float], bool] = readable,
        read: Callable[[int, int], bytes] = os.read,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._descriptor = descriptor
        self._report = report
        self._ready = ready
        self._read = read
        self._clock = clock
        self._buffer = bytearray()
        self._discarding = False

    def receive(self, timeout: float) -> Incoming | None:
        """Return one valid message, time out, or raise EOFError when the parent closes."""
        deadline = self._clock() + timeout
        while True:
            if b"\n" in self._buffer:
                raw, _, remainder = self._buffer.partition(b"\n")
                self._buffer = bytearray(remainder)
                if self._discarding or len(raw) + 1 > MAX_RECORD_BYTES:
                    self._discarding = False
                    self._report("Ignoring oversized desktop message.")
                    continue
                try:
                    return INCOMING.validate_json(raw)
                except ValueError as error:
                    self._report(f"Ignoring invalid desktop message: {str(error)[:1000]}")
                    continue
            if len(self._buffer) >= MAX_RECORD_BYTES:
                self._buffer.clear()
                self._discarding = True
            remaining = deadline - self._clock()
            if timeout > 0 and remaining <= 0:
                return None
            if not self._ready(self._descriptor, max(0, remaining)):
                return None
            chunk = self._read(self._descriptor, 4096)
            if not chunk:
                if self._buffer or self._discarding:
                    self._report("Ignoring incomplete desktop message at EOF.")
                raise EOFError("The desktop application closed its input pipe.")
            self._buffer.extend(chunk)


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
