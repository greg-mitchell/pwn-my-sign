import os
import signal
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired
from unittest.mock import MagicMock, Mock, call

import pytest

from greg_mitchell.pwn_my_sign.workflow.models import PollSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.producer import CommandProducer, ProducerError
from greg_mitchell.pwn_my_sign.workflow.sender import SnapshotSender
from greg_mitchell.pwn_my_sign.workflow.source import ImageSource
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState


@pytest.fixture
def process() -> MagicMock:
    process = MagicMock(spec=Popen)
    process.__enter__.return_value = process
    process.pid = 123
    process.returncode = 0
    process.communicate.return_value = (b"PNG bytes", None)
    return process


@pytest.fixture
def spawn(process: MagicMock) -> Mock:
    return Mock(spec=Popen, return_value=process)


@pytest.fixture
def kill_group() -> Mock:
    return Mock(spec=os.killpg)


def test_run_when_producer_succeeds_returns_stdout_bytes(spawn: Mock, kill_group: Mock) -> None:
    result = CommandProducer(spawn, kill_group).run(("producer",))

    assert result == b"PNG bytes"


def test_run_when_invoked_calls_spawn_with_literal_arguments_and_reserved_stdin(spawn: Mock, kill_group: Mock) -> None:
    command = ("producer with spaces", "--caption", "a; $(literal)")

    CommandProducer(spawn, kill_group).run(command)

    spawn.assert_called_once_with(command, stdin=DEVNULL, stdout=PIPE, start_new_session=True)


def test_run_when_waiting_calls_communicate(process: MagicMock, spawn: Mock, kill_group: Mock) -> None:
    CommandProducer(spawn, kill_group).run(("producer",))

    process.communicate.assert_called_once_with()


@pytest.mark.parametrize("status", [1, 7, -15])
def test_run_when_exit_nonzero_raises_producer_error(
    process: MagicMock, spawn: Mock, kill_group: Mock, status: int
) -> None:
    process.returncode = status

    with pytest.raises(ProducerError, match=f"Producer exited with status {status}"):
        CommandProducer(spawn, kill_group).run(("producer",))


def test_run_when_executable_missing_raises_os_error(spawn: Mock, kill_group: Mock) -> None:
    spawn.side_effect = FileNotFoundError("producer missing")

    with pytest.raises(FileNotFoundError, match="producer missing"):
        CommandProducer(spawn, kill_group).run(("producer",))


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(143), OSError("pipe failed")])
def test_run_when_capture_interrupted_calls_group_termination(
    process: MagicMock, spawn: Mock, kill_group: Mock, error: BaseException
) -> None:
    process.communicate.side_effect = [error, (b"", None)]

    with pytest.raises(type(error)):
        CommandProducer(spawn, kill_group).run(("producer",))

    kill_group.assert_called_once_with(123, signal.SIGTERM)


def test_run_when_interrupted_calls_communicate_to_reap_before_returning(
    process: MagicMock, spawn: Mock, kill_group: Mock
) -> None:
    process.communicate.side_effect = [KeyboardInterrupt(), (b"", None)]

    with pytest.raises(KeyboardInterrupt):
        CommandProducer(spawn, kill_group).run(("producer",))

    assert process.communicate.call_args_list == [call(), call(timeout=5)]


def test_run_when_termination_times_out_calls_group_kill(process: MagicMock, spawn: Mock, kill_group: Mock) -> None:
    process.communicate.side_effect = [KeyboardInterrupt(), TimeoutExpired("producer", 5), (b"", None)]

    with pytest.raises(KeyboardInterrupt):
        CommandProducer(spawn, kill_group).run(("producer",))

    assert kill_group.call_args_list == [call(123, signal.SIGTERM), call(123, signal.SIGKILL)]


def test_run_when_group_already_exited_raises_original_interruption(
    process: MagicMock, spawn: Mock, kill_group: Mock
) -> None:
    process.communicate.side_effect = [KeyboardInterrupt(), (b"", None)]
    kill_group.side_effect = ProcessLookupError

    with pytest.raises(KeyboardInterrupt):
        CommandProducer(spawn, kill_group).run(("producer",))


def test_poll_when_producer_interrupted_returns_lock_held_during_child_cleanup(
    process: MagicMock, spawn: Mock, tmp_path: Path
) -> None:
    process.communicate.side_effect = [KeyboardInterrupt(), (b"", None)]
    observed: list[bool] = []
    kill_group = Mock(
        spec=os.killpg, side_effect=lambda group, number: observed.append((tmp_path / "poll.lock").is_dir())
    )
    workflow = WorkflowOperations(
        WorkflowState(tmp_path),
        ImageSource(CommandProducer(spawn, kill_group), BytesIO()),
        Mock(spec=SnapshotSender),
        Mock(spec=Callable),
    )

    with pytest.raises(KeyboardInterrupt):
        workflow.poll(PollSettings(command=("producer",)))

    assert observed == [True]


@pytest.mark.parametrize("status", [0, 7])
def test_poll_when_producer_output_invalid_or_failed_returns_previous_pending(
    process: MagicMock, spawn: Mock, kill_group: Mock, tmp_path: Path, status: int
) -> None:
    state = WorkflowState(tmp_path)
    state.publish(b"previous image")
    process.returncode = status
    process.communicate.return_value = (b"partial PNG", None)
    workflow = WorkflowOperations(
        state,
        ImageSource(CommandProducer(spawn, kill_group), BytesIO()),
        Mock(spec=SnapshotSender),
        Mock(spec=Callable),
    )

    with pytest.raises(ValueError):
        workflow.poll(PollSettings(command=("producer",)))

    assert state.pending() == b"previous image"
