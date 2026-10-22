import asyncio
import gzip
from pathlib import Path
from unittest.mock import AsyncMock, Mock, call

import pytest
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.service import BleakGATTService, BleakGATTServiceCollection

from greg_mitchell.pwn_my_sign.transport import NOTIFY, send_frame, show_notification


@pytest.fixture
def connected_client() -> tuple[Mock, Mock]:
    characteristic = Mock(spec=BleakGATTCharacteristic)
    characteristic.max_write_without_response_size = 244
    service = Mock(spec=BleakGATTService)
    service.get_characteristic.return_value = characteristic
    client = Mock(spec=BleakClient)
    client.services = Mock(spec=BleakGATTServiceCollection)
    client.services.get_service.return_value = service
    return client, characteristic


def test_send_frame_when_streaming_a_frame_calls_protocol_writes(connected_client: tuple[Mock, Mock]) -> None:
    client, characteristic = connected_client
    fixture = Path(__file__).parents[2] / "fixtures" / "grayscale.frame.gz"
    payload = gzip.decompress(fixture.read_bytes())
    expected = [call(characteristic, b"!I", response=False)] + [
        call(characteristic, payload[offset : offset + 240], response=False) for offset in range(0, 460800, 240)
    ]

    asyncio.run(send_frame(client, payload, 0.05, AsyncMock(spec=asyncio.sleep)))

    assert client.write_gatt_char.await_args_list == expected


def test_send_frame_when_service_is_available_calls_notification_subscription(
    connected_client: tuple[Mock, Mock],
) -> None:
    client, _ = connected_client
    payload = bytes(460800)

    asyncio.run(send_frame(client, payload, 0.05, AsyncMock(spec=asyncio.sleep)))

    client.start_notify.assert_awaited_once_with(NOTIFY, show_notification)


def test_send_frame_when_payload_is_short_raises_value_error(connected_client: tuple[Mock, Mock]) -> None:
    client, _ = connected_client
    payload = b"short"

    with pytest.raises(ValueError, match="Expected 460800 image bytes"):
        asyncio.run(send_frame(client, payload, 0.05, AsyncMock(spec=asyncio.sleep)))


def test_send_frame_when_service_is_missing_raises_value_error(connected_client: tuple[Mock, Mock]) -> None:
    client, _ = connected_client
    client.services.get_service.return_value = None
    payload = bytes(460800)

    with pytest.raises(ValueError, match="does not expose the captured service"):
        asyncio.run(send_frame(client, payload, 0.05, AsyncMock(spec=asyncio.sleep)))


def test_send_frame_when_characteristic_is_missing_raises_value_error(connected_client: tuple[Mock, Mock]) -> None:
    client, _ = connected_client
    client.services.get_service.return_value.get_characteristic.return_value = None
    payload = bytes(460800)

    with pytest.raises(ValueError, match="does not expose the image write characteristic"):
        asyncio.run(send_frame(client, payload, 0.05, AsyncMock(spec=asyncio.sleep)))


def test_send_frame_when_write_limit_is_small_raises_value_error(connected_client: tuple[Mock, Mock]) -> None:
    client, characteristic = connected_client
    characteristic.max_write_without_response_size = 20
    payload = bytes(460800)

    with pytest.raises(ValueError, match="BLE write limit is 20"):
        asyncio.run(send_frame(client, payload, 0.05, AsyncMock(spec=asyncio.sleep)))


def test_send_frame_when_notification_subscription_fails_raises_runtime_error(
    connected_client: tuple[Mock, Mock],
) -> None:
    client, _ = connected_client
    client.start_notify.side_effect = RuntimeError("subscription failed")
    payload = bytes(460800)

    with pytest.raises(RuntimeError, match="subscription failed"):
        asyncio.run(send_frame(client, payload, 0.05, AsyncMock(spec=asyncio.sleep)))


def test_send_frame_when_write_fails_raises_runtime_error(connected_client: tuple[Mock, Mock]) -> None:
    client, _ = connected_client
    client.write_gatt_char.side_effect = RuntimeError("connection lost")
    payload = bytes(460800)

    with pytest.raises(RuntimeError, match="connection lost"):
        asyncio.run(send_frame(client, payload, 0.05, AsyncMock(spec=asyncio.sleep)))
