import asyncio
from collections.abc import Awaitable, Callable
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from PIL import Image

from greg_mitchell.pwn_my_sign.frame_codec import FRAME_BYTES, encode_image
from greg_mitchell.pwn_my_sign.images.png import load_png
from greg_mitchell.pwn_my_sign.transport import send_frame

Sleep = Callable[[float], Awaitable[None]]
SendFrame = Callable[[BleakClient, bytes, float, Sleep], Awaitable[None]]


class ImageInputError(ValueError):
    """PNG stream input could not be read or validated before device discovery."""


class DeviceOperations:
    def __init__(
        self,
        scanner: type[BleakScanner] = BleakScanner,
        client_factory: type[BleakClient] = BleakClient,
        send: SendFrame = send_frame,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.scanner = scanner
        self.client_factory = client_factory
        self.send = send
        self.sleep = sleep

    async def scan(self, timeout: float) -> tuple[tuple[BLEDevice, AdvertisementData], ...]:
        devices = await self.scanner.discover(timeout=timeout, return_adv=True)
        return tuple(devices.values())

    async def upload(
        self,
        device_name: str,
        *,
        image_path: Path | None,
        frame_path: Path | None,
        timeout: float,
        packet_delay: float,
        report: Callable[[str], None],
        image_stream: BinaryIO | None = None,
    ) -> None:
        if image_stream is not None:
            if image_path is not None or frame_path is not None:
                raise ImageInputError("Provide only one image or frame source.")
            try:
                with BytesIO(image_stream.read()) as stream, load_png(stream) as image:
                    payload = encode_image(image)
            except (OSError, ValueError) as error:
                raise ImageInputError(str(error)) from error
        elif image_path is not None:
            with Image.open(image_path) as image:
                payload = encode_image(image)
        elif frame_path is not None:
            payload = frame_path.read_bytes()
        else:
            raise ValueError("An image or frame is required")
        if len(payload) != FRAME_BYTES:
            raise ValueError(f"Expected a headerless {FRAME_BYTES}-byte frame")

        def matches(device: BLEDevice, advertisement: AdvertisementData) -> bool:
            return device_name.casefold() in {
                device.address.casefold(),
                (device.name or "").casefold(),
                (advertisement.local_name or "").casefold(),
            }

        report("Waiting for the selected sign; press its button now.")
        device = await self.scanner.find_device_by_filter(matches, timeout=timeout)
        if device is None:
            raise TimeoutError("Selected sign was not found before the timeout")
        async with self.client_factory(device) as client:
            await self.send(client, payload, packet_delay, self.sleep)
