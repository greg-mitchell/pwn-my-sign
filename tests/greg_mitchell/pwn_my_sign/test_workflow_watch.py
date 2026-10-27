from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest
from bleak.exc import BleakError

from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadSettings, WatchSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState
from greg_mitchell.pwn_my_sign.workflow.terminal import InputResult, TerminalInput
from greg_mitchell.pwn_my_sign.workflow.watch import Watcher


@pytest.fixture
def workflow(tmp_path: Path) -> Mock:
    workflow = Mock(spec=WorkflowOperations)
    workflow.state = WorkflowState(tmp_path)
    workflow.state.publish(b"desired image")
    return workflow


@pytest.fixture
def terminal() -> Mock:
    return Mock(spec=TerminalInput, **{"wait.return_value": InputResult.EOF})


@pytest.fixture
def sleep() -> Mock:
    return Mock(spec=Callable, side_effect=KeyboardInterrupt)


@pytest.fixture
def report() -> Mock:
    return Mock(spec=Callable)


@pytest.fixture
def settings() -> WatchSettings:
    return WatchSettings(
        poll=PollSettings(command=("produce-image",)), upload=UploadSettings(device="test sign"), interval=7
    )


@pytest.fixture
def watcher(workflow: Mock, terminal: Mock, sleep: Mock, report: Mock) -> Watcher:
    return Watcher(workflow, terminal, sleep, report)


def test_run_when_started_calls_poller(watcher: Watcher, workflow: Mock, settings: WatchSettings) -> None:
    watcher.run(settings)

    workflow.poll.assert_called_once_with(settings.poll)


def test_run_when_pending_differs_calls_report_with_bell(
    watcher: Watcher, report: Mock, settings: WatchSettings
) -> None:
    watcher.run(settings)

    assert report.call_args_list[0].args == ("\aPending image differs from last sent.",)


def test_run_when_prompting_calls_terminal_with_interval(
    watcher: Watcher, terminal: Mock, settings: WatchSettings
) -> None:
    watcher.run(settings)

    terminal.wait.assert_called_once_with(7)


def test_run_when_eof_calls_no_uploader(watcher: Watcher, workflow: Mock, settings: WatchSettings) -> None:
    watcher.run(settings)

    workflow.upload.assert_not_called()


def test_run_when_enter_calls_uploader(
    watcher: Watcher, workflow: Mock, terminal: Mock, settings: WatchSettings
) -> None:
    terminal.wait.return_value = InputResult.ENTER

    with pytest.raises(KeyboardInterrupt):
        watcher.run(settings)

    workflow.upload.assert_called_once_with(settings.upload)


def test_run_when_upload_completed_calls_sleep(
    watcher: Watcher, terminal: Mock, sleep: Mock, settings: WatchSettings
) -> None:
    terminal.wait.return_value = InputResult.ENTER

    with pytest.raises(KeyboardInterrupt):
        watcher.run(settings)

    sleep.assert_called_once_with(7)


def test_run_when_input_times_out_calls_poller_again_without_sleep(
    watcher: Watcher, workflow: Mock, terminal: Mock, settings: WatchSettings
) -> None:
    terminal.wait.side_effect = [InputResult.TIMEOUT, InputResult.EOF]

    watcher.run(settings)

    assert workflow.poll.call_count == 2


def test_run_when_input_times_out_calls_no_sleep(
    watcher: Watcher, terminal: Mock, sleep: Mock, settings: WatchSettings
) -> None:
    terminal.wait.side_effect = [InputResult.TIMEOUT, InputResult.EOF]

    watcher.run(settings)

    sleep.assert_not_called()


def test_run_when_already_sent_calls_no_reminder(
    watcher: Watcher, workflow: Mock, report: Mock, settings: WatchSettings
) -> None:
    workflow.state.record_sent(b"desired image")

    with pytest.raises(KeyboardInterrupt):
        watcher.run(settings)

    report.assert_not_called()


@pytest.mark.parametrize("error", [OSError("fetch failed"), ValueError("invalid image")])
def test_run_when_poll_fails_calls_no_terminal(
    watcher: Watcher, workflow: Mock, terminal: Mock, settings: WatchSettings, error: Exception
) -> None:
    workflow.poll.side_effect = error

    with pytest.raises(KeyboardInterrupt):
        watcher.run(settings)

    terminal.wait.assert_not_called()


def test_run_when_poll_recovers_calls_poller_again(
    watcher: Watcher, workflow: Mock, sleep: Mock, settings: WatchSettings
) -> None:
    workflow.poll.side_effect = [OSError("fetch failed"), None]
    sleep.side_effect = None

    watcher.run(settings)

    assert workflow.poll.call_count == 2


@pytest.mark.parametrize("error", [OSError("send failed"), ValueError("invalid PNG"), BleakError("BLE failed")])
def test_run_when_upload_fails_calls_sleep_before_retrying(
    watcher: Watcher, workflow: Mock, terminal: Mock, sleep: Mock, settings: WatchSettings, error: Exception
) -> None:
    terminal.wait.return_value = InputResult.ENTER
    workflow.upload.side_effect = error

    with pytest.raises(KeyboardInterrupt):
        watcher.run(settings)

    sleep.assert_called_once_with(7)


def test_run_when_comparison_fails_calls_no_uploader(
    watcher: Watcher, workflow: Mock, tmp_path: Path, settings: WatchSettings
) -> None:
    (tmp_path / "last-sent.png").mkdir()

    with pytest.raises(OSError):
        watcher.run(settings)

    workflow.upload.assert_not_called()


def test_run_when_watch_locked_calls_no_poller(
    watcher: Watcher, workflow: Mock, tmp_path: Path, settings: WatchSettings
) -> None:
    (tmp_path / "watch.lock").mkdir()

    with pytest.raises(OSError, match="Cannot acquire"):
        watcher.run(settings)

    workflow.poll.assert_not_called()


@pytest.mark.parametrize("stage", ["poll", "upload", "input", "sleep"])
def test_run_when_interrupted_returns_state_without_watch_lock(
    watcher: Watcher, workflow: Mock, terminal: Mock, sleep: Mock, settings: WatchSettings, tmp_path: Path, stage: str
) -> None:
    terminal.wait.return_value = InputResult.ENTER
    if stage == "poll":
        workflow.poll.side_effect = KeyboardInterrupt
    elif stage == "upload":
        workflow.upload.side_effect = KeyboardInterrupt
    elif stage == "input":
        terminal.wait.side_effect = KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        watcher.run(settings)

    assert not (tmp_path / "watch.lock").exists()
