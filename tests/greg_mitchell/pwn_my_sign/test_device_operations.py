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
from greg_mitchell.pwn_my_sign.transport import SERVICE, send_frame


@pytest.fixture
def scanner() -> Mock:
    return Mock(spec=BleakScanner)


@pytest.fixture
def frame_path(tmp_path: Path) -> Path:
    path = tmp_path / "frame.bin"
    path.write_bytes(b"\x44" * 460800)
    return path


@pytest.fixture
def scan_session(scanner: Mock) -> MagicMock:
    session = MagicMock(spec=BleakScanner)
    scanner.return_value = session
    return session


@pytest.mark.parametrize(
    ("services", "all_devices", "expected"),
    [([SERVICE], False, True), ([SERVICE.upper()], False, True), ([], False, False), ([], True, True)],
)
def test_scan_when_advertisement_arrives_calls_report_for_selected_services(
    scanner: Mock, scan_session: MagicMock, services: list[str], all_devices: bool, expected: bool
) -> None:
    device = Mock(spec=BLEDevice, address="test-address")
    device.name = "test-sign"
    advertisement = Mock(spec=AdvertisementData, local_name="test-sign", service_uuids=services)
    report = Mock(spec=Callable)

    async def advertise(timeout: float) -> None:
        scanner.call_args.kwargs["detection_callback"](device, advertisement)

    asyncio.run(DeviceOperations(scanner=scanner, sleep=advertise).scan(7, report, all_devices=all_devices))

    assert report.call_args_list == ([((device, advertisement), {})] if expected else [])


@pytest.mark.parametrize("names", [(None, None), ("test-sign", "test-sign"), (None, "test-sign")])
def test_scan_when_advertisements_repeat_calls_report_only_for_new_names(
    scanner: Mock, scan_session: MagicMock, names: tuple[str | None, str | None]
) -> None:
    device = Mock(spec=BLEDevice, address="test-address")
    device.name = None
    advertisements = tuple(
        Mock(spec=AdvertisementData, local_name=name, rssi=rssi, service_uuids=[SERVICE])
        for name, rssi in zip(names, (-42, -43), strict=True)
    )
    report = Mock(spec=Callable)

    async def advertise(timeout: float) -> None:
        for advertisement in advertisements:
            scanner.call_args.kwargs["detection_callback"](device, advertisement)

    asyncio.run(DeviceOperations(scanner=scanner, sleep=advertise).scan(7, report))

    expected = advertisements if names[0] != names[1] else advertisements[:1]
    assert report.call_args_list == [((device, advertisement), {}) for advertisement in expected]


def test_scan_when_called_calls_sleep_with_timeout(scanner: Mock, scan_session: MagicMock) -> None:
    sleep = AsyncMock(spec=asyncio.sleep)

    asyncio.run(DeviceOperations(scanner=scanner, sleep=sleep).scan(7, Mock(spec=Callable)))

    sleep.assert_awaited_once_with(7)


def test_scan_when_window_ends_calls_scanner_stop(scanner: Mock, scan_session: MagicMock) -> None:
    asyncio.run(DeviceOperations(scanner=scanner, sleep=AsyncMock(spec=asyncio.sleep)).scan(7, Mock(spec=Callable)))

    scan_session.__aexit__.assert_awaited_once_with(None, None, None)


def test_scan_when_discovery_fails_raises_os_error(scanner: Mock, scan_session: MagicMock) -> None:
    scan_session.__aenter__.side_effect = OSError("Bluetooth unavailable")

    with pytest.raises(OSError, match="Bluetooth unavailable"):
        asyncio.run(DeviceOperations(scanner=scanner).scan(7, Mock(spec=Callable)))


def test_scan_when_window_is_interrupted_calls_scanner_stop(scanner: Mock, scan_session: MagicMock) -> None:
    sleep = AsyncMock(spec=asyncio.sleep, side_effect=asyncio.CancelledError)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(DeviceOperations(scanner=scanner, sleep=sleep).scan(7, Mock(spec=Callable)))

    assert scan_session.__aexit__.await_count == 1


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
