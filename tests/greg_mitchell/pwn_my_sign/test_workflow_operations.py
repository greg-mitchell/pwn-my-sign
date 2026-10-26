from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest

from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.sender import SnapshotSender
from greg_mitchell.pwn_my_sign.workflow.source import StatusImageSource
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState


@pytest.fixture
def source() -> Mock:
    return Mock(spec=StatusImageSource, **{"image.return_value": b"desired image"})


@pytest.fixture
def sender() -> Mock:
    return Mock(spec=SnapshotSender)


@pytest.fixture
def report() -> Mock:
    return Mock(spec=Callable)


@pytest.fixture
def workflow(tmp_path: Path, source: Mock, sender: Mock, report: Mock) -> WorkflowOperations:
    return WorkflowOperations(WorkflowState(tmp_path), source, sender, report)


def test_poll_when_image_selected_returns_published_image(workflow: WorkflowOperations) -> None:
    workflow.poll(PollSettings(map_path=Path("map.toml")))

    assert workflow.state.pending() == b"desired image"


def test_poll_when_configured_calls_source_with_settings(workflow: WorkflowOperations, source: Mock) -> None:
    settings = PollSettings(map_path=Path("map with spaces.toml"), policy_path=Path("policy.toml"))

    workflow.poll(settings)

    source.image.assert_called_once_with(settings)


@pytest.mark.parametrize("error", [OSError("fetch failed"), ValueError("invalid image")])
def test_poll_when_source_fails_returns_previous_pending(
    workflow: WorkflowOperations, source: Mock, error: Exception
) -> None:
    workflow.state.publish(b"previous image")
    source.image.side_effect = error

    with pytest.raises(type(error), match=str(error)):
        workflow.poll(PollSettings(map_path=Path("map.toml")))

    assert workflow.state.pending() == b"previous image"


def test_poll_when_locked_calls_no_source(workflow: WorkflowOperations, source: Mock, tmp_path: Path) -> None:
    (tmp_path / "poll.lock").mkdir()

    with pytest.raises(OSError, match="Cannot acquire"):
        workflow.poll(PollSettings(map_path=Path("map.toml")))

    source.image.assert_not_called()


def test_upload_when_unsent_calls_sender_with_snapshot(
    workflow: WorkflowOperations, sender: Mock, report: Mock
) -> None:
    workflow.state.publish(b"desired image")
    settings = UploadSettings(device="test sign")

    workflow.upload(settings)

    sender.send.assert_called_once_with(b"desired image", settings, report)


def test_upload_when_already_sent_calls_no_sender(workflow: WorkflowOperations, sender: Mock) -> None:
    workflow.state.publish(b"desired image")
    workflow.state.record_sent(b"desired image")

    workflow.upload(UploadSettings(device="test sign"))

    sender.send.assert_not_called()


@pytest.mark.parametrize("missing", [True, False])
def test_upload_when_pending_unreadable_calls_no_sender(
    workflow: WorkflowOperations, sender: Mock, tmp_path: Path, missing: bool
) -> None:
    if not missing:
        (tmp_path / "pending.png").mkdir()

    with pytest.raises(OSError):
        workflow.upload(UploadSettings(device="test sign"))

    sender.send.assert_not_called()


def test_upload_when_comparison_fails_calls_no_sender(
    workflow: WorkflowOperations, sender: Mock, tmp_path: Path
) -> None:
    workflow.state.publish(b"desired image")
    (tmp_path / "last-sent.png").mkdir()

    with pytest.raises(OSError):
        workflow.upload(UploadSettings(device="test sign"))

    sender.send.assert_not_called()


@pytest.mark.parametrize("error", [OSError("send failed"), KeyboardInterrupt(), SystemExit(143)])
def test_upload_when_transfer_fails_returns_previous_sent_image(
    workflow: WorkflowOperations, sender: Mock, tmp_path: Path, error: BaseException
) -> None:
    workflow.state.publish(b"desired image")
    workflow.state.record_sent(b"previous image")
    sender.send.side_effect = error

    with pytest.raises(type(error)):
        workflow.upload(UploadSettings(device="test sign"))

    assert (tmp_path / "last-sent.png").read_bytes() == b"previous image"


@pytest.mark.parametrize("filename", ["pending.png", "last-sent.png"])
def test_upload_when_pending_changes_during_transfer_returns_correct_snapshot(
    workflow: WorkflowOperations, sender: Mock, tmp_path: Path, filename: str
) -> None:
    workflow.state.publish(b"uploaded snapshot")

    def transfer(image: bytes, settings: UploadSettings, report: Callable[[str], None]) -> None:
        workflow.state.publish(b"newer desired image")

    sender.send.side_effect = transfer

    workflow.upload(UploadSettings(device="test sign"))

    expected = b"newer desired image" if filename == "pending.png" else b"uploaded snapshot"
    assert (tmp_path / filename).read_bytes() == expected


def test_upload_when_locked_calls_no_sender(workflow: WorkflowOperations, sender: Mock, tmp_path: Path) -> None:
    workflow.state.publish(b"desired image")
    (tmp_path / "upload.lock").mkdir()

    with pytest.raises(OSError, match="Cannot acquire"):
        workflow.upload(UploadSettings(device="test sign"))

    sender.send.assert_not_called()


def test_upload_when_sender_unwinds_returns_lock_held_until_cleanup(
    workflow: WorkflowOperations, sender: Mock, tmp_path: Path
) -> None:
    workflow.state.publish(b"desired image")
    observed: list[bool] = []

    def transfer(image: bytes, settings: UploadSettings, report: Callable[[str], None]) -> None:
        try:
            raise KeyboardInterrupt
        finally:
            observed.append((tmp_path / "upload.lock").is_dir())

    sender.send.side_effect = transfer

    with pytest.raises(KeyboardInterrupt):
        workflow.upload(UploadSettings(device="test sign"))

    assert observed == [True]


def test_poll_when_publication_fails_raises_os_error(source: Mock, sender: Mock, report: Mock) -> None:
    state = Mock(spec=WorkflowState)
    state.lock.return_value = nullcontext()
    state.publish.side_effect = OSError("publication failed")
    workflow = WorkflowOperations(state, source, sender, report)

    with pytest.raises(OSError, match="publication failed"):
        workflow.poll(PollSettings(map_path=Path("map.toml")))
