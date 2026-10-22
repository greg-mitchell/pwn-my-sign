from PIL import Image

WIDTH = 1280
HEIGHT = 720
FRAME_BYTES = WIDTH * HEIGHT // 2


def decode_frame(payload: bytes) -> Image.Image:
    if len(payload) != FRAME_BYTES:
        raise ValueError(f"Expected {FRAME_BYTES} image bytes, got {len(payload)}")
    pixels = bytes(level * 17 for byte in payload for level in (byte >> 4, byte & 15))
    return Image.frombytes("L", (WIDTH, HEIGHT), pixels).transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def encode_image(image: Image.Image) -> bytes:
    if image.size != (WIDTH, HEIGHT):
        raise ValueError(f"Expected {WIDTH}x{HEIGHT}, got {image.width}x{image.height}")
    pixels = image.convert("L").transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()
    levels = bytes((value * 15 + 127) // 255 for value in pixels)
    return bytes((high << 4) | low for high, low in zip(levels[::2], levels[1::2]))
