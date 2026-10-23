from typing import BinaryIO

from PIL import Image

from greg_mitchell.pwn_my_sign.frame_codec import HEIGHT, WIDTH


def load_png(stream: BinaryIO) -> Image.Image:
    """Decode a static sign-sized PNG from a seekable stream without closing the caller's stream."""
    try:
        stream.seek(0)
        with Image.open(stream) as image:
            if image.format != "PNG":
                raise ValueError("Expected PNG image data.")
            if image.size != (WIDTH, HEIGHT):
                raise ValueError(f"Expected {WIDTH}x{HEIGHT}, got {image.width}x{image.height}.")
            if getattr(image, "is_animated", False):
                raise ValueError("Animated PNG images are not supported.")
            image.verify()
            # Pillow stops at IEND's payload, accepting a missing CRC; check that complete end chunk explicitly.
            stream.seek(stream.tell() - 8)
            if stream.read(12) != b"\x00\x00\x00\x00IEND\xaeB`\x82":
                raise ValueError("Incomplete or invalid PNG end chunk.")
        stream.seek(0)
        with Image.open(stream) as image:
            image.load()
            return image.copy()
    except (OSError, SyntaxError) as error:
        raise ValueError(f"Invalid PNG image: {error}") from error
