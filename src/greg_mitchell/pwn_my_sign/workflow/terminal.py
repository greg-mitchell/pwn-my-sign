import select
from collections.abc import Callable
from enum import StrEnum
from typing import TextIO


class InputResult(StrEnum):
    ENTER = "enter"
    TIMEOUT = "timeout"
    EOF = "eof"


def readable(stream: TextIO, timeout: float) -> bool:
    """Wait for terminal input on Unix without threads or background children."""
    ready, _, _ = select.select([stream], [], [], timeout)
    return bool(ready)


class TerminalInput:
    """Distinguish input, timeout, and EOF at the reminder prompt."""

    def __init__(self, stream: TextIO, ready: Callable[[TextIO, float], bool] = readable) -> None:
        self._stream = stream
        self._ready = ready

    def wait(self, timeout: float) -> InputResult:
        """Wait once for a line, or return when the reminder interval expires."""
        if not self._ready(self._stream, timeout):
            return InputResult.TIMEOUT
        return InputResult.ENTER if self._stream.readline() else InputResult.EOF
