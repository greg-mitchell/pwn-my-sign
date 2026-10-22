import sys
from collections.abc import Awaitable, Callable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from greg_mitchell.pwn_my_sign.frame_codec import FRAME_BYTES

SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
CHUNK_BYTES = 240


def show_notification(characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
    print(f"Notification: {data.hex()}", file=sys.stderr, flush=True)


async def send_frame(
    client: BleakClient,
    payload: bytes,
    delay: float,
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    if len(payload) != FRAME_BYTES:
        raise ValueError(f"Expected {FRAME_BYTES} image bytes, got {len(payload)}")
    service = client.services.get_service(SERVICE)
    if service is None:
        raise ValueError("Selected device does not expose the captured service")
    characteristic = service.get_characteristic(WRITE)
    if characteristic is None:
        raise ValueError("Selected device does not expose the image write characteristic")
    await client.start_notify(NOTIFY, show_notification)
    await sleep(2)
    maximum = characteristic.max_write_without_response_size
    if maximum < CHUNK_BYTES:
        raise ValueError(f"BLE write limit is {maximum}; capture used {CHUNK_BYTES}")
    print(f"Connected; sending {len(payload)} image bytes", file=sys.stderr, flush=True)
    await client.write_gatt_char(characteristic, b"!I", response=False)
    await sleep(0.02)
    for offset in range(0, len(payload), CHUNK_BYTES):
        await client.write_gatt_char(characteristic, payload[offset : offset + CHUNK_BYTES], response=False)
        await sleep(delay)
        sent = offset + CHUNK_BYTES
        if sent % (CHUNK_BYTES * 192) == 0:
            print(f"Sent {sent * 100 // len(payload)}%", file=sys.stderr, flush=True)
    await sleep(2)
    print("Image bytes sent. Check the sign to confirm the refresh.", file=sys.stderr, flush=True)
