import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from PIL import Image

from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.transport import send_frame


@pytest.fixture
def scanner() -> Mock:
    return Mock(spec=BleakScanner)


@pytest.fixture
def frame_path(tmp_path: Path) -> Path:
    path = tmp_path / "frame.bin"
    path.write_bytes(b"\x44" * 460800)
    return path


def test_scan_when_devices_are_found_returns_discoveries(scanner: Mock) -> None:
    device = Mock(spec=BLEDevice)
    advertisement = Mock(spec=AdvertisementData)
    scanner.discover.return_value = {"test-address": (device, advertisement)}

    result = asyncio.run(DeviceOperations(scanner=scanner).scan(7))

    assert result == ((device, advertisement),)


def test_scan_when_called_calls_scanner_with_timeout(scanner: Mock) -> None:
    scanner.discover.return_value = {}

    asyncio.run(DeviceOperations(scanner=scanner).scan(7))

    scanner.discover.assert_awaited_once_with(timeout=7, return_adv=True)


def test_scan_when_discovery_fails_raises_os_error(scanner: Mock) -> None:
    scanner.discover.side_effect = OSError("Bluetooth unavailable")

    with pytest.raises(OSError, match="Bluetooth unavailable"):
        asyncio.run(DeviceOperations(scanner=scanner).scan(7))


def test_upload_when_frame_is_valid_calls_sender_with_unchanged_bytes(scanner: Mock, frame_path: Path) -> None:
    client = MagicMock(spec=BleakClient)
    client.__aenter__.return_value = client
    factory = Mock(spec=BleakClient, return_value=client)
    send = AsyncMock(spec=send_frame)
    sleep = AsyncMock(spec=asyncio.sleep)
    operations = DeviceOperations(scanner=scanner, client_factory=factory, send=send, sleep=sleep)

    asyncio.run(
        operations.upload(
            "test-sign", image_path=None, frame_path=frame_path, timeout=7, packet_delay=0.05, report=Mock(spec=print)
        )
    )

    send.assert_awaited_once_with(client, b"\x44" * 460800, 0.05, sleep)


def test_upload_when_image_is_valid_calls_sender_with_encoded_frame(scanner: Mock, tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    Image.new("L", (1280, 720), 255).save(image_path)
    client = MagicMock(spec=BleakClient)
    client.__aenter__.return_value = client
    send = AsyncMock(spec=send_frame)
    sleep = AsyncMock(spec=asyncio.sleep)
    operations = DeviceOperations(
        scanner=scanner, client_factory=Mock(spec=BleakClient, return_value=client), send=send, sleep=sleep
    )

    asyncio.run(
        operations.upload(
            "test-sign", image_path=image_path, frame_path=None, timeout=7, packet_delay=0.05, report=Mock(spec=print)
        )
    )

    send.assert_awaited_once_with(client, b"\xff" * 460800, 0.05, sleep)


def test_upload_when_frame_is_valid_calls_client_factory_with_discovered_device(
    scanner: Mock, frame_path: Path
) -> None:
    device = Mock(spec=BLEDevice)
    scanner.find_device_by_filter.return_value = device
    client = MagicMock(spec=BleakClient)
    factory = Mock(spec=BleakClient, return_value=client)
    operations = DeviceOperations(scanner=scanner, client_factory=factory, send=AsyncMock(spec=send_frame))

    asyncio.run(
        operations.upload(
            "test-sign", image_path=None, frame_path=frame_path, timeout=7, packet_delay=0.05, report=Mock(spec=print)
        )
    )

    factory.assert_called_once_with(device)


def test_upload_when_frame_is_valid_calls_button_prompt_before_discovery(scanner: Mock, frame_path: Path) -> None:
    events: list[str] = []

    async def find_device(*args: object, **kwargs: object) -> None:
        events.append("scan")
        return None

    scanner.find_device_by_filter.side_effect = find_device

    with pytest.raises(TimeoutError):
        asyncio.run(
            DeviceOperations(scanner=scanner).upload(
                "test-sign",
                image_path=None,
                frame_path=frame_path,
                timeout=7,
                packet_delay=0.05,
                report=events.append,
            )
        )

    assert events == ["Waiting for the selected sign; press its button now.", "scan"]


def test_upload_when_frame_is_invalid_calls_no_discovery(scanner: Mock, tmp_path: Path) -> None:
    path = tmp_path / "short.bin"
    path.write_bytes(b"short")

    with pytest.raises(ValueError, match="460800"):
        asyncio.run(
            DeviceOperations(scanner=scanner).upload(
                "test-sign", image_path=None, frame_path=path, timeout=7, packet_delay=0.05, report=Mock(spec=print)
            )
        )

    scanner.find_device_by_filter.assert_not_called()


def test_upload_when_source_is_missing_raises_os_error(scanner: Mock, tmp_path: Path) -> None:
    with pytest.raises(OSError):
        asyncio.run(
            DeviceOperations(scanner=scanner).upload(
                "test-sign",
                image_path=tmp_path / "missing.png",
                frame_path=None,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )


def test_upload_when_device_is_missing_raises_timeout_error(scanner: Mock, frame_path: Path) -> None:
    scanner.find_device_by_filter.return_value = None

    with pytest.raises(TimeoutError, match="Selected sign was not found"):
        asyncio.run(
            DeviceOperations(scanner=scanner).upload(
                "test-sign",
                image_path=None,
                frame_path=frame_path,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )


def test_upload_when_sender_fails_raises_runtime_error(scanner: Mock, frame_path: Path) -> None:
    client = MagicMock(spec=BleakClient)
    send = AsyncMock(spec=send_frame, side_effect=RuntimeError("stream failed"))
    operations = DeviceOperations(
        scanner=scanner, client_factory=Mock(spec=BleakClient, return_value=client), send=send
    )

    with pytest.raises(RuntimeError, match="stream failed"):
        asyncio.run(
            operations.upload(
                "test-sign",
                image_path=None,
                frame_path=frame_path,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )


@pytest.mark.parametrize(
    ("target", "address", "name", "local_name", "expected"),
    (
        ("test-uuid", "TEST-UUID", "other", "other", True),
        ("test-sign", "other", "TEST-SIGN", None, True),
        ("test-sign", "other", None, "TEST-SIGN", True),
        ("test", "test-uuid", "test-sign", "test-sign", False),
        ("test-sign", "other", None, None, False),
    ),
)
def test_upload_when_discovery_filters_devices_returns_exact_casefold_match(
    target: str,
    address: str,
    name: str | None,
    local_name: str | None,
    expected: bool,
    scanner: Mock,
    frame_path: Path,
) -> None:
    device = Mock(spec=BLEDevice, address=address)
    device.name = name
    advertisement = Mock(spec=AdvertisementData, local_name=local_name)
    decisions: list[bool] = []

    async def find_device(predicate: Callable[[BLEDevice, AdvertisementData], bool], *, timeout: float) -> None:
        decisions.append(predicate(device, advertisement))

    scanner.find_device_by_filter.side_effect = find_device

    with pytest.raises(TimeoutError):
        asyncio.run(
            DeviceOperations(scanner=scanner).upload(
                target,
                image_path=None,
                frame_path=frame_path,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )

    assert decisions == [expected]


def test_upload_when_discovery_fails_raises_os_error(scanner: Mock, frame_path: Path) -> None:
    scanner.find_device_by_filter.side_effect = OSError("Bluetooth unavailable")

    with pytest.raises(OSError, match="Bluetooth unavailable"):
        asyncio.run(
            DeviceOperations(scanner=scanner).upload(
                "test-sign",
                image_path=None,
                frame_path=frame_path,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )


def test_upload_when_connection_fails_raises_os_error(scanner: Mock, frame_path: Path) -> None:
    client = MagicMock(spec=BleakClient)
    client.__aenter__.side_effect = OSError("connection failed")
    operations = DeviceOperations(scanner=scanner, client_factory=Mock(spec=BleakClient, return_value=client))

    with pytest.raises(OSError, match="connection failed"):
        asyncio.run(
            operations.upload(
                "test-sign",
                image_path=None,
                frame_path=frame_path,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )
