import asyncio
from collections.abc import Callable
from io import BytesIO

from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.workflow.models import UploadSettings


class SnapshotSender:
    """Validate and transfer an immutable pending snapshot through the existing sender."""

    def __init__(self, operations: DeviceOperations) -> None:
        self._operations = operations

    def send(self, image: bytes, settings: UploadSettings, report: Callable[[str], None]) -> None:
        """Wait for transfer and async cleanup before returning to the workflow lock."""
        with BytesIO(image) as stream:
            asyncio.run(
                self._operations.upload(
                    settings.device,
                    image_path=None,
                    frame_path=None,
                    image_stream=stream,
                    timeout=60,
                    packet_delay=0.05,
                    report=report,
                )
            )
