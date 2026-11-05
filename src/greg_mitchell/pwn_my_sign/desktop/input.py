from __future__ import annotations

import os
import select
import sys
from collections.abc import Callable, Generator
from contextlib import closing, contextmanager
from queue import Queue, ShutDown
from threading import Thread
from typing import BinaryIO

from greg_mitchell.pwn_my_sign.desktop.channel import LinePump, MessageReader, PipeInput


def pump_input(stream: BinaryIO, messages: Queue[PipeInput]) -> None:
    """Close the private buffer after EOF, or stop delivery when the controller exits."""
    with stream:
        try:
            LinePump(stream, messages.put).run()
        except ShutDown:
            return


def parent_closed(events: select.kqueue) -> bool:
    """Detect native-parent EOF independently of background reader scheduling."""
    return any(event.flags & select.KQ_EV_EOF for event in events.control(None, 1, 0))


def duplicate_input(descriptor: int) -> BinaryIO:
    """Keep the input worker's buffer separate from Python's global stdin."""
    return os.fdopen(os.dup(descriptor), "rb")


def start_reader(pump: Callable[[], None]) -> None:
    """Run only pipe framing in the background; workflow and Bluetooth stay on the main thread."""
    Thread(target=pump, name="desktop-input", daemon=True).start()


def open_monitor(platform: str = sys.platform) -> select.kqueue:
    """Reject unsupported desktop platforms without affecting ordinary CLI imports."""
    if platform != "darwin":
        raise OSError("The native desktop workflow requires macOS.")
    return select.kqueue()


@contextmanager
def pipe_reader(
    descriptor: int,
    report: Callable[[str], None],
    monitor: Callable[[], select.kqueue] = open_monitor,
    open_stream: Callable[[int], BinaryIO] = duplicate_input,
    start: Callable[[Callable[[], None]], None] = start_reader,
) -> Generator[MessageReader]:
    """Own one macOS pipe reader without holding Python's global stdin buffer lock."""
    with closing(monitor()) as events:
        events.control([select.kevent(descriptor, filter=select.KQ_FILTER_READ, flags=select.KQ_EV_ADD)], 0)
        messages: Queue[PipeInput] = Queue(maxsize=64)
        stream = open_stream(descriptor)
        try:
            start(lambda: pump_input(stream, messages))
        except RuntimeError:
            stream.close()
            raise
        try:
            yield MessageReader(messages, report, parent_closed=lambda: parent_closed(events))
        finally:
            # Release a pump blocked on backpressure; a blocked read dies with this child process.
            messages.shutdown(immediate=True)
