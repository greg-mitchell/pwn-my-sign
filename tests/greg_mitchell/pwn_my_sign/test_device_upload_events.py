import asyncio
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, call

import pytest
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from greg_mitchell.pwn_my_sign.device.events import UploadEvent
from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.transport import send_frame


@pytest.fixture
def frame(tmp_path: Path) -> Path:
    path = tmp_path / "image.frame"
    path.write_bytes(b"\x44" * 460800)
    return path


@pytest.fixture
def scanner() -> Mock:
    return Mock(spec=BleakScanner)


@pytest.fixture
def client() -> MagicMock:
    connection = MagicMock(spec=BleakClient)
    connection.__aenter__.return_value = connection
    return connection


@pytest.fixture
def sender() -> AsyncMock:
    return AsyncMock(spec=send_frame)


@pytest.fixture
def operations(scanner: Mock, client: MagicMock, sender: AsyncMock) -> DeviceOperations:
    return DeviceOperations(scanner=scanner, client_factory=Mock(spec=BleakClient, return_value=client), send=sender)


def test_upload_when_frame_valid_calls_events_at_discovery_and_transfer_boundaries(
    operations: DeviceOperations, scanner: Mock, client: MagicMock, sender: AsyncMock, frame: Path
) -> None:
    observed: list[UploadEvent | str] = []

    async def discover(*args: object, **kwargs: object) -> Mock:
        observed.append("discovery")
        return Mock(spec=BLEDevice)

    async def connected() -> MagicMock:
        observed.append("connected")
        return client

    async def send(*args: object) -> None:
        observed.append("transfer")

    scanner.find_device_by_filter.side_effect = discover
    client.__aenter__.side_effect = connected
    sender.side_effect = send

    asyncio.run(
        operations.upload(
            "test-sign",
            image_path=None,
            frame_path=frame,
            timeout=7,
            packet_delay=0.05,
            report=Mock(spec=Callable),
            on_event=observed.append,
        )
    )

    assert observed == [UploadEvent.WAITING_FOR_BUTTON, "discovery", "connected", UploadEvent.SENDING, "transfer"]


@pytest.mark.parametrize("source", ["frame", "png"])
def test_upload_when_source_invalid_calls_no_events(operations: DeviceOperations, frame: Path, source: str) -> None:
    observer = Mock(spec=Callable)
    frame.write_bytes(b"incomplete image")

    with pytest.raises(ValueError):
        asyncio.run(
            operations.upload(
                "test-sign",
                image_path=None,
                frame_path=frame if source == "frame" else None,
                image_stream=BytesIO(b"incomplete image") if source == "png" else None,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=Callable),
                on_event=observer,
            )
        )

    observer.assert_not_called()


def test_upload_when_waiting_callback_fails_calls_no_discovery(
    operations: DeviceOperations, scanner: Mock, frame: Path
) -> None:
    observer = Mock(spec=Callable, side_effect=TimeoutError("Button prompt was not acknowledged"))

    with pytest.raises(TimeoutError, match="Button prompt was not acknowledged"):
        asyncio.run(
            operations.upload(
                "test-sign",
                image_path=None,
                frame_path=frame,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=Callable),
                on_event=observer,
            )
        )

    scanner.find_device_by_filter.assert_not_called()


@pytest.mark.parametrize("failure", ["discovery", "connection"])
def test_upload_when_connection_unavailable_calls_only_waiting_event(
    operations: DeviceOperations, scanner: Mock, client: MagicMock, frame: Path, failure: str
) -> None:
    observer = Mock(spec=Callable)
    if failure == "discovery":
        scanner.find_device_by_filter.side_effect = OSError("Bluetooth unavailable")
    else:
        client.__aenter__.side_effect = OSError("Bluetooth unavailable")

    with pytest.raises(OSError, match="Bluetooth unavailable"):
        asyncio.run(
            operations.upload(
                "test-sign",
                image_path=None,
                frame_path=frame,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=Callable),
                on_event=observer,
            )
        )

    assert observer.call_args_list == [call(UploadEvent.WAITING_FOR_BUTTON)]


def test_upload_when_sign_not_found_calls_only_waiting_event(
    operations: DeviceOperations, scanner: Mock, frame: Path
) -> None:
    observer = Mock(spec=Callable)
    scanner.find_device_by_filter.return_value = None

    with pytest.raises(TimeoutError, match="Selected sign was not found"):
        asyncio.run(
            operations.upload(
                "test-sign",
                image_path=None,
                frame_path=frame,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=Callable),
                on_event=observer,
            )
        )

    assert observer.call_args_list == [call(UploadEvent.WAITING_FOR_BUTTON)]


def test_upload_when_sending_callback_fails_calls_no_sender(
    operations: DeviceOperations, sender: AsyncMock, frame: Path
) -> None:
    observer = Mock(spec=Callable, side_effect=[None, OSError("Presentation disconnected")])

    with pytest.raises(OSError, match="Presentation disconnected"):
        asyncio.run(
            operations.upload(
                "test-sign",
                image_path=None,
                frame_path=frame,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=Callable),
                on_event=observer,
            )
        )

    sender.assert_not_awaited()


def test_upload_when_sending_callback_fails_calls_connection_cleanup(
    operations: DeviceOperations, client: MagicMock, frame: Path
) -> None:
    observer = Mock(spec=Callable, side_effect=[None, OSError("Presentation disconnected")])

    with pytest.raises(OSError, match="Presentation disconnected"):
        asyncio.run(
            operations.upload(
                "test-sign",
                image_path=None,
                frame_path=frame,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=Callable),
                on_event=observer,
            )
        )

    assert client.__aexit__.await_count == 1
