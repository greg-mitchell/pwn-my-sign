from collections.abc import Callable
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import ANY, Mock

import pytest

from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadSettings
from greg_mitchell.pwn_my_sign.workflow.producer import CommandProducer, ProducerError
from greg_mitchell.pwn_my_sign.workflow.sender import SnapshotSender
from greg_mitchell.pwn_my_sign.workflow.source import ImageSource
from greg_mitchell.pwn_my_sign.workflow.terminal import InputResult, TerminalInput


@pytest.fixture
def png() -> bytes:
    return Path("tests/fixtures/cards/title-only.png").read_bytes()


@pytest.fixture
def producer(png: bytes) -> Mock:
    return Mock(spec=CommandProducer, **{"run.return_value": png})


def test_image_when_producer_succeeds_returns_original_png(producer: Mock, png: bytes) -> None:
    result = ImageSource(producer, BytesIO()).image(PollSettings(command=("producer",)))

    assert result == png


def test_image_when_producer_selected_calls_producer_with_arguments(producer: Mock) -> None:
    ImageSource(producer, BytesIO()).image(PollSettings(command=("producer", "--title", "example image")))

    producer.run.assert_called_once_with(("producer", "--title", "example image"))


def test_image_when_file_selected_returns_original_png(producer: Mock, png: bytes, tmp_path: Path) -> None:
    path = tmp_path / "image with spaces.png"
    path.write_bytes(png)

    result = ImageSource(producer, BytesIO()).image(PollSettings(image_path=path))

    assert result == png


def test_image_when_stdin_selected_returns_original_png(producer: Mock, png: bytes) -> None:
    result = ImageSource(producer, BytesIO(png)).image(PollSettings(image_path=Path("-")))

    assert result == png


def test_image_when_stdin_selected_calls_no_producer(producer: Mock, png: bytes) -> None:
    ImageSource(producer, BytesIO(png)).image(PollSettings(image_path=Path("-")))

    producer.run.assert_not_called()


@pytest.mark.parametrize("error", [OSError("not executable"), ProducerError("exit status 1")])
def test_image_when_producer_fails_raises_source_error(producer: Mock, error: Exception) -> None:
    producer.run.side_effect = error

    with pytest.raises(type(error), match=str(error)):
        ImageSource(producer, BytesIO()).image(PollSettings(command=("producer",)))


@pytest.mark.parametrize("data", [b"", b"partial PNG", b"diagnostic text"])
def test_image_when_producer_output_invalid_raises_value_error(producer: Mock, data: bytes) -> None:
    producer.run.return_value = data

    with pytest.raises(ValueError):
        ImageSource(producer, BytesIO()).image(PollSettings(command=("producer",)))


def test_image_when_file_missing_raises_os_error(producer: Mock, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ImageSource(producer, BytesIO()).image(PollSettings(image_path=tmp_path / "missing.png"))


def test_send_when_snapshot_selected_calls_device_uploader_with_defaults() -> None:
    operations = Mock(spec=DeviceOperations)
    report = Mock(spec=Callable)

    SnapshotSender(operations).send(b"snapshot PNG", UploadSettings(device="test sign"), report)

    operations.upload.assert_awaited_once_with(
        "test sign", image_path=None, frame_path=None, image_stream=ANY, timeout=60, packet_delay=0.05, report=report
    )


def test_send_when_snapshot_selected_calls_device_uploader_with_snapshot_bytes() -> None:
    operations = Mock(spec=DeviceOperations)
    observed: list[bytes] = []

    async def upload(device: str, **kwargs: object) -> None:
        stream = kwargs["image_stream"]
        assert isinstance(stream, BytesIO)
        observed.append(stream.read())

    operations.upload.side_effect = upload

    SnapshotSender(operations).send(b"snapshot PNG", UploadSettings(device="test sign"), Mock(spec=Callable))

    assert observed == [b"snapshot PNG"]


def test_send_when_device_uploader_fails_raises_os_error() -> None:
    operations = Mock(spec=DeviceOperations)
    operations.upload.side_effect = OSError("Bluetooth unavailable")

    with pytest.raises(OSError, match="Bluetooth unavailable"):
        SnapshotSender(operations).send(b"snapshot PNG", UploadSettings(device="test sign"), Mock(spec=Callable))


@pytest.mark.parametrize(
    ("ready", "text", "expected"),
    [(False, "", InputResult.TIMEOUT), (True, "", InputResult.EOF), (True, "\n", InputResult.ENTER)],
)
def test_wait_when_input_changes_returns_distinct_result(ready: bool, text: str, expected: InputResult) -> None:
    terminal = TerminalInput(StringIO(text), Mock(spec=Callable, return_value=ready))

    result = terminal.wait(7)

    assert result == expected


def test_wait_when_waiting_calls_readiness_dependency_with_interval() -> None:
    stream = StringIO()
    ready = Mock(spec=Callable, return_value=False)

    TerminalInput(stream, ready).wait(7)

    ready.assert_called_once_with(stream, 7)


def test_wait_when_readiness_fails_raises_os_error() -> None:
    ready = Mock(spec=Callable, side_effect=OSError("input unavailable"))

    with pytest.raises(OSError, match="input unavailable"):
        TerminalInput(StringIO(), ready).wait(7)
