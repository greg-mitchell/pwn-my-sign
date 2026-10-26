from collections.abc import Callable
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import ANY, Mock

import pytest

from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.github.source import GitHubSource
from greg_mitchell.pwn_my_sign.images.selection import ImageSelector
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadSettings
from greg_mitchell.pwn_my_sign.workflow.sender import SnapshotSender
from greg_mitchell.pwn_my_sign.workflow.source import StatusImageSource
from greg_mitchell.pwn_my_sign.workflow.terminal import InputResult, TerminalInput


@pytest.fixture
def source() -> Mock:
    source = Mock(spec=GitHubSource)
    with Path("tests/fixtures/github/healthy.json").open("rb") as stream:
        source.fetch.return_value = GitHubSource().read(stream)
    return source


@pytest.fixture
def selector() -> Mock:
    return Mock(spec=ImageSelector, **{"select.return_value": b"selected PNG"})


def test_image_when_healthy_returns_selected_image(source: Mock, selector: Mock) -> None:
    result = StatusImageSource(source, selector).image(PollSettings(map_path=Path("map.toml")))

    assert result == b"selected PNG"


def test_image_when_fetching_calls_source_once(source: Mock, selector: Mock) -> None:
    StatusImageSource(source, selector).image(PollSettings(map_path=Path("map.toml")))

    source.fetch.assert_called_once_with()


def test_image_when_policy_selected_calls_selector_with_interpreted_token(
    source: Mock, selector: Mock, tmp_path: Path
) -> None:
    settings = PollSettings(map_path=tmp_path / "map with spaces.toml", policy_path=Path("data/github-actions.toml"))
    observed: list[tuple[Path, bytes]] = []

    def select(map_path: Path, stream: BytesIO) -> bytes:
        observed.append((map_path, stream.read()))
        return b"selected PNG"

    selector.select.side_effect = select

    StatusImageSource(source, selector).image(settings)

    assert observed == [(settings.map_path, b"ok\n")]


def test_image_when_policy_invalid_calls_no_source(source: Mock, selector: Mock, tmp_path: Path) -> None:
    policy = tmp_path / "invalid.toml"
    policy.write_text('mode = "unknown"')

    with pytest.raises(ValueError):
        StatusImageSource(source, selector).image(PollSettings(map_path=Path("map.toml"), policy_path=policy))

    source.fetch.assert_not_called()


def test_image_when_fetch_fails_calls_no_selector(source: Mock, selector: Mock) -> None:
    source.fetch.side_effect = OSError("fetch failed")

    with pytest.raises(OSError, match="fetch failed"):
        StatusImageSource(source, selector).image(PollSettings(map_path=Path("map.toml")))

    selector.select.assert_not_called()


def test_image_when_selection_fails_raises_value_error(source: Mock, selector: Mock) -> None:
    selector.select.side_effect = ValueError("no matching image")

    with pytest.raises(ValueError, match="no matching image"):
        StatusImageSource(source, selector).image(PollSettings(map_path=Path("map.toml")))


def test_image_when_composing_real_selector_returns_original_png(source: Mock, tmp_path: Path) -> None:
    image = Path("tests/fixtures/cards/title-only.png").read_bytes()
    (tmp_path / "card.png").write_bytes(image)
    (tmp_path / "map.toml").write_text('[images]\nnone = "card.png"\n')

    result = StatusImageSource(source, ImageSelector()).image(PollSettings(map_path=tmp_path / "map.toml"))

    assert result == image


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
