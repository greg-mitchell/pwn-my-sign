import asyncio
from collections.abc import Callable
from functools import partial
from io import BytesIO

from greg_mitchell.pwn_my_sign.device.events import UploadEvent
from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.workflow.models import UploadSettings


class SnapshotSender:
    """Validate and transfer an immutable pending snapshot through the existing sender."""

    def __init__(self, operations: DeviceOperations, on_event: Callable[[UploadEvent], None] | None = None) -> None:
        self._operations = operations
        self._on_event = on_event

    def send(self, image: bytes, settings: UploadSettings, report: Callable[[str], None]) -> None:
        """Wait for transfer and async cleanup before returning to the workflow lock."""
        upload = self._operations.upload
        if self._on_event is not None:
            upload = partial(upload, on_event=self._on_event)
        with BytesIO(image) as stream:
            asyncio.run(
                upload(
                    settings.device,
                    image_path=None,
                    frame_path=None,
                    image_stream=stream,
                    timeout=60,
                    packet_delay=0.05,
                    report=report,
                )
            )
