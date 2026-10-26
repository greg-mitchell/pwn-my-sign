import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from greg_mitchell.pwn_my_sign.workflow.models import WorkflowKind
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState, replace_file


def test_lock_when_acquired_returns_process_id_file(tmp_path: Path) -> None:
    state = WorkflowState(tmp_path)

    with state.lock(WorkflowKind.POLL):
        assert (tmp_path / "poll.lock/pid").read_text() == f"{os.getpid()}\n"


def test_lock_when_already_held_raises_without_removing_existing_lock(tmp_path: Path) -> None:
    state = WorkflowState(tmp_path)

    with state.lock(WorkflowKind.POLL), pytest.raises(OSError, match="Cannot acquire"):
        with state.lock(WorkflowKind.POLL):
            pytest.fail("Overlapping poll acquired a lock")


@pytest.mark.parametrize("error", [None, OSError("failed"), KeyboardInterrupt(), SystemExit(143)])
def test_lock_when_operation_exits_returns_directory_without_lock(tmp_path: Path, error: BaseException | None) -> None:
    state = WorkflowState(tmp_path)

    try:
        with state.lock(WorkflowKind.UPLOAD):
            if error is not None:
                raise error
    except (OSError, KeyboardInterrupt, SystemExit):
        pass

    assert tuple(tmp_path.iterdir()) == ()


def test_lock_when_upload_is_active_returns_available_poll_lock(tmp_path: Path) -> None:
    state = WorkflowState(tmp_path)

    with state.lock(WorkflowKind.UPLOAD), state.lock(WorkflowKind.POLL):
        assert (tmp_path / "poll.lock").is_dir()


def test_pending_when_present_returns_snapshot_bytes(tmp_path: Path) -> None:
    (tmp_path / "pending.png").write_bytes(b"desired image")

    result = WorkflowState(tmp_path).pending()

    assert result == b"desired image"


def test_pending_when_missing_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        WorkflowState(tmp_path).pending()


@pytest.mark.parametrize("sent", [None, b"previous image", b"desired image"])
def test_is_sent_when_comparing_returns_exact_byte_match(tmp_path: Path, sent: bytes | None) -> None:
    if sent is not None:
        (tmp_path / "last-sent.png").write_bytes(sent)

    result = WorkflowState(tmp_path).is_sent(b"desired image")

    assert result is (sent == b"desired image")


@pytest.mark.parametrize("name", ["pending.png", "last-sent.png"])
def test_state_when_comparison_target_is_directory_raises_os_error(tmp_path: Path, name: str) -> None:
    (tmp_path / name).mkdir()
    state = WorkflowState(tmp_path)

    with pytest.raises(OSError):
        if name == "pending.png":
            state.publish(b"desired image")
        else:
            state.is_sent(b"desired image")


@pytest.mark.parametrize("name", ["pending.png", "last-sent.png"])
def test_state_when_comparison_target_is_dangling_symlink_raises_os_error(tmp_path: Path, name: str) -> None:
    (tmp_path / name).symlink_to(tmp_path / "missing")
    state = WorkflowState(tmp_path)

    with pytest.raises(FileNotFoundError):
        if name == "pending.png":
            state.publish(b"desired image")
        else:
            state.is_sent(b"desired image")


def test_publish_when_changed_returns_complete_pending_image(tmp_path: Path) -> None:
    (tmp_path / "pending.png").write_bytes(b"previous image")

    WorkflowState(tmp_path).publish(b"desired image")

    assert (tmp_path / "pending.png").read_bytes() == b"desired image"


def test_publish_when_unchanged_calls_no_replacement(tmp_path: Path) -> None:
    (tmp_path / "pending.png").write_bytes(b"desired image")
    replace = Mock(spec=replace_file)

    WorkflowState(tmp_path, replace).publish(b"desired image")

    replace.assert_not_called()


@pytest.mark.parametrize("operation", ["publish", "record_sent"])
def test_state_when_replacing_calls_dependency_with_complete_sibling_file(tmp_path: Path, operation: str) -> None:
    observed: list[tuple[Path, bytes]] = []

    def replace(source: Path, destination: Path) -> None:
        observed.append((source.parent, source.read_bytes()))

    state = WorkflowState(tmp_path, replace)

    if operation == "publish":
        state.publish(b"desired image")
    else:
        state.record_sent(b"desired image")

    assert observed == [(tmp_path, b"desired image")]


@pytest.mark.parametrize("operation", ["publish", "record_sent"])
def test_state_when_replacement_fails_returns_previous_image(tmp_path: Path, operation: str) -> None:
    name = "pending.png" if operation == "publish" else "last-sent.png"
    (tmp_path / name).write_bytes(b"previous image")
    replace = Mock(spec=replace_file, side_effect=OSError("rename failed"))
    state = WorkflowState(tmp_path, replace)

    with pytest.raises(OSError, match="rename failed"):
        if operation == "publish":
            state.publish(b"desired image")
        else:
            state.record_sent(b"desired image")

    assert (tmp_path / name).read_bytes() == b"previous image"


@pytest.mark.parametrize("error", [None, OSError("rename failed"), KeyboardInterrupt()])
def test_publish_when_replacement_exits_returns_directory_without_temporary_file(
    tmp_path: Path, error: BaseException | None
) -> None:
    replace = Mock(spec=replace_file, side_effect=error)

    try:
        WorkflowState(tmp_path, replace).publish(b"desired image")
    except (OSError, KeyboardInterrupt):
        pass

    assert tuple(tmp_path.iterdir()) == ()


def test_record_sent_when_successful_returns_uploaded_snapshot(tmp_path: Path) -> None:
    (tmp_path / "pending.png").write_bytes(b"newer desired image")

    WorkflowState(tmp_path).record_sent(b"uploaded snapshot")

    assert (tmp_path / "last-sent.png").read_bytes() == b"uploaded snapshot"
