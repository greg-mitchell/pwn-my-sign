import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from PIL import Image

from greg_mitchell.pwn_my_sign.frame_codec import FRAME_BYTES, encode_image
from greg_mitchell.pwn_my_sign.transport import send_frame


async def run(arguments: argparse.Namespace) -> None:
    if arguments.command == "scan":
        print("Scanning; press the sign's button now.", file=sys.stderr, flush=True)
        devices = await BleakScanner.discover(timeout=arguments.timeout, return_adv=True)
        for discovered, advertisement in devices.values():
            name = advertisement.local_name or discovered.name or "(unnamed)"
            print(f"{discovered.address}  {name!r}  RSSI {advertisement.rssi}")
        return
    if arguments.image is not None:
        with Image.open(arguments.image) as image:
            payload = encode_image(image)
    else:
        payload = arguments.frame.read_bytes()
    if len(payload) != FRAME_BYTES:
        raise ValueError(f"Expected a headerless {FRAME_BYTES}-byte frame")

    def matches(device: BLEDevice, advertisement: AdvertisementData) -> bool:
        return arguments.device.casefold() in {
            device.address.casefold(),
            (device.name or "").casefold(),
            (advertisement.local_name or "").casefold(),
        }

    print("Waiting for the selected sign; press its button now.", file=sys.stderr, flush=True)
    device = await BleakScanner.find_device_by_filter(matches, timeout=arguments.timeout)
    if device is None:
        raise TimeoutError("Selected sign was not found before the timeout")
    async with BleakClient(device) as client:
        await send_frame(client, payload, arguments.packet_delay, asyncio.sleep)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scan and upload images to a Dory sign")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="List nearby devices without connecting")
    scan.add_argument("--timeout", type=float, default=30)
    upload = commands.add_parser("upload", help="Send one image after the sign is woken")
    upload.add_argument("--device", required=True, help="Exact advertised name or Mac BLE UUID")
    upload.add_argument("--timeout", type=float, default=60)
    upload.add_argument("--packet-delay", type=float, default=0.05)
    source = upload.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=Path, help="1280x720 image")
    source.add_argument("--frame", type=Path, help="Headerless captured image payload")
    arguments = parser.parse_args(argv)
    if arguments.timeout <= 0:
        parser.error("--timeout must be positive")
    if arguments.command == "upload" and arguments.packet_delay < 0:
        parser.error("--packet-delay must be nonnegative")
    asyncio.run(run(arguments))


def send_main() -> None:
    main(("upload", *sys.argv[1:]))
