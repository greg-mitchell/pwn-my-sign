from __future__ import annotations

import select
import sys
from collections.abc import Callable
from io import BytesIO
from queue import Queue
from unittest.mock import MagicMock, Mock

import pytest

from greg_mitchell.pwn_my_sign.desktop.channel import PipeInput
from greg_mitchell.pwn_my_sign.desktop.input import open_monitor, parent_closed, pipe_reader, pump_input

macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="Native pipe EOF monitoring uses macOS kqueue.")


def test_pump_input_when_stream_finishes_returns_closed_private_buffer() -> None:
    stream = BytesIO(b'{}\n')
    messages: Queue[PipeInput] = Queue()

    pump_input(stream, messages)

    assert stream.closed


def test_pump_input_when_stream_has_record_calls_queue_with_complete_line() -> None:
    messages: Queue[PipeInput] = Queue()

    pump_input(BytesIO(b'{}\n'), messages)

    assert messages.get_nowait() == b'{}\n'


@macos_only
@pytest.mark.parametrize("closed", [True, False])
def test_parent_closed_when_pipe_status_changes_returns_eof_status(closed: bool) -> None:
    flags = select.KQ_EV_EOF if closed else 0
    monitor = Mock(spec=select.kqueue, **{"control.return_value": [select.kevent(42, flags=flags)]})

    result = parent_closed(monitor)

    assert result is closed


@macos_only
def test_parent_closed_when_probe_fails_raises_os_error() -> None:
    monitor = Mock(spec=select.kqueue, **{"control.side_effect": OSError("Monitor failed")})

    with pytest.raises(OSError, match="Monitor failed"):
        parent_closed(monitor)


@pytest.fixture
def monitor() -> MagicMock:
    events = MagicMock(spec=select.kqueue)
    events.control.return_value = []
    return events


@macos_only
def test_pipe_reader_when_opened_calls_stream_factory_with_parent_descriptor(monitor: MagicMock) -> None:
    stream = Mock(spec=Callable, return_value=BytesIO())

    with pipe_reader(42, Mock(spec=Callable), monitor=lambda: monitor, open_stream=stream, start=Mock(spec=Callable)):
        pass

    stream.assert_called_once_with(42)


@macos_only
def test_pipe_reader_when_opened_calls_injected_reader_launcher(monitor: MagicMock) -> None:
    start = Mock(spec=Callable)

    with pipe_reader(
        42, Mock(spec=Callable), monitor=lambda: monitor, open_stream=lambda descriptor: BytesIO(), start=start
    ):
        pass

    assert start.call_count == 1


@macos_only
def test_pipe_reader_when_launcher_fails_returns_closed_buffer(monitor: MagicMock) -> None:
    stream = BytesIO()
    start = Mock(spec=Callable, side_effect=RuntimeError("Cannot start reader"))

    with pytest.raises(RuntimeError, match="Cannot start reader"):
        with pipe_reader(
            42, Mock(spec=Callable), monitor=lambda: monitor, open_stream=lambda descriptor: stream, start=start
        ):
            pass

    assert stream.closed


@macos_only
def test_pipe_reader_when_controller_fails_calls_monitor_cleanup(monitor: MagicMock) -> None:
    with pytest.raises(ValueError, match="Controller failed"):
        with pipe_reader(
            42,
            Mock(spec=Callable),
            monitor=lambda: monitor,
            open_stream=lambda descriptor: BytesIO(),
            start=Mock(spec=Callable),
        ):
            raise ValueError("Controller failed")

    monitor.close.assert_called_once_with()


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_open_monitor_when_platform_unsupported_raises_desktop_only_error(platform: str) -> None:
    with pytest.raises(OSError, match="desktop workflow requires macOS"):
        open_monitor(platform)
