from io import BytesIO

from PIL import Image

from greg_mitchell.pwn_my_sign.frame_codec import HEIGHT, WIDTH


def load_png(data: bytes) -> Image.Image:
    """Verify and decode one static sign-sized PNG snapshot."""
    stream = BytesIO(data)
    try:
        with Image.open(stream) as image:
            if image.format != "PNG":
                raise ValueError("Expected PNG image data.")
            if image.size != (WIDTH, HEIGHT):
                raise ValueError(f"Expected {WIDTH}x{HEIGHT}, got {image.width}x{image.height}.")
            if getattr(image, "is_animated", False):
                raise ValueError("Animated PNG images are not supported.")
            image.verify()
            # Pillow verifies chunks before IEND but leaves its payload and checksum unread.
            end = stream.tell()
            if data[end - 8 : end + 4] != b"\x00\x00\x00\x00IEND\xaeB`\x82":
                raise ValueError("Incomplete or invalid PNG end chunk.")
        with Image.open(BytesIO(data)) as image:
            image.load()
            return image.copy()
    except (OSError, SyntaxError) as error:
        raise ValueError(f"Invalid PNG image: {error}") from error
