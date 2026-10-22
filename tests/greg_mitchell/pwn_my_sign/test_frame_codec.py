import gzip
from pathlib import Path

import pytest
from PIL import Image

from greg_mitchell.pwn_my_sign.frame_codec import FRAME_BYTES, decode_frame, encode_image


def test_encode_image_when_corners_are_marked_returns_right_to_left_rows() -> None:
    image = Image.new("L", (1280, 720), 255)
    image.putpixel((0, 0), 0)
    image.putpixel((1279, 0), 17)
    image.putpixel((0, 719), 34)
    image.putpixel((1279, 719), 51)

    frame = encode_image(image)

    assert (frame[0], frame[639], frame[-640], frame[-1]) == (0x1F, 0xF0, 0x3F, 0xF2)


def test_decode_frame_when_rows_are_reversed_returns_marked_corners() -> None:
    frame = bytearray([255]) * FRAME_BYTES
    frame[0], frame[639], frame[-640], frame[-1] = 0x1F, 0xF0, 0x3F, 0xF2

    image = decode_frame(bytes(frame))

    assert tuple(image.getpixel(point) for point in ((0, 0), (1279, 0), (0, 719), (1279, 719))) == (0, 17, 34, 51)


def test_encode_image_when_dimensions_are_wrong_raises_value_error() -> None:
    image = Image.new("L", (720, 720), 255)

    with pytest.raises(ValueError, match="Expected 1280x720"):
        encode_image(image)


def test_decode_frame_when_payload_is_short_raises_value_error() -> None:
    frame = bytes(10)

    with pytest.raises(ValueError, match="Expected 460800 image bytes"):
        decode_frame(frame)


@pytest.mark.parametrize("name", ("grayscale", "checkerboard"))
def test_encode_image_when_decoding_a_fixture_returns_original_bytes(name: str) -> None:
    fixture = Path(__file__).parents[2] / "fixtures" / f"{name}.frame.gz"
    frame = gzip.decompress(fixture.read_bytes())

    actual = encode_image(decode_frame(frame))

    assert actual == frame
