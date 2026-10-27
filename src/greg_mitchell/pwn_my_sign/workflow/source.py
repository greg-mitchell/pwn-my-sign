from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from greg_mitchell.pwn_my_sign.images.png import load_png
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings
from greg_mitchell.pwn_my_sign.workflow.producer import CommandProducer


class ImageSource:
    """Read a complete sign-sized PNG from a producer, file, or injected stdin."""

    def __init__(self, producer: CommandProducer, stdin: BinaryIO) -> None:
        self._producer = producer
        self._stdin = stdin

    def image(self, settings: PollSettings) -> bytes:
        """Validate all image data before returning original bytes for publication."""
        if settings.command:
            data = self._producer.run(settings.command)
        elif settings.image_path == Path("-"):
            data = self._stdin.read()
        elif settings.image_path is not None:
            data = settings.image_path.read_bytes()
        else:
            raise ValueError("An image source is required.")
        with BytesIO(data) as stream, load_png(stream):
            return data
