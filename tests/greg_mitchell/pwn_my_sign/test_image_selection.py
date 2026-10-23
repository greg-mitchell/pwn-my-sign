from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from zlib import crc32

import pytest
from click.testing import CliRunner
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from greg_mitchell.pwn_my_sign.cli.mysign import main as mysign
from greg_mitchell.pwn_my_sign.images.png import load_png
from greg_mitchell.pwn_my_sign.images.selection import ImageSelector


@pytest.fixture
def png() -> bytes:
    stream = BytesIO()
    metadata = PngInfo()
    metadata.add_text("description", "Preserve this exact asset snapshot.")
    Image.new("L", (1280, 720), 255).save(stream, format="PNG", pnginfo=metadata)
    return stream.getvalue()


@pytest.fixture
def map_path(tmp_path: Path, png: bytes) -> Path:
    (tmp_path / "card.png").write_bytes(png)
    path = tmp_path / "images.toml"
    path.write_text('[images]\nok = "card.png"\nmissing = "missing.png"\n')
    return path


@pytest.mark.parametrize("token", (b"ok", b"ok\n", b"ok\r\n"))
def test_select_when_token_matches_returns_original_bytes(map_path: Path, png: bytes, token: bytes) -> None:
    result = ImageSelector().select(map_path, BytesIO(token))

    assert result == png


def test_select_when_path_is_absolute_returns_original_bytes(map_path: Path, png: bytes) -> None:
    map_path.write_text(f'[images]\nok = "{map_path.parent / "card.png"}"\n')

    result = ImageSelector().select(map_path, BytesIO(b"ok"))

    assert result == png


def test_select_when_map_is_nested_returns_asset_relative_to_map(tmp_path: Path, png: bytes) -> None:
    settings = tmp_path / "settings"
    settings.mkdir()
    cards = tmp_path / "cards"
    cards.mkdir()
    (cards / "ok.png").write_bytes(png)
    map_path = settings / "images.toml"
    map_path.write_text('[images]\nok = "../cards/ok.png"')

    result = ImageSelector().select(map_path, BytesIO(b"ok"))

    assert result == png


@pytest.mark.parametrize("token", (b"", b"\n", b" ok", b"ok ", b"ok\n\n", b"ok\r", b"ok\nother", b"\xff"))
def test_select_when_input_is_not_one_token_raises_value_error(map_path: Path, token: bytes) -> None:
    with pytest.raises(ValueError):
        ImageSelector().select(map_path, BytesIO(token))


@pytest.mark.parametrize("token", (b"OK", b"unknown"))
def test_select_when_token_is_unmapped_raises_value_error(map_path: Path, token: bytes) -> None:
    with pytest.raises(ValueError, match="No image mapped"):
        ImageSelector().select(map_path, BytesIO(token))


@pytest.mark.parametrize(
    "document",
    (
        b"not toml",
        b"\xff",
        b"",
        b"[images]",
        b'[images]\n" " = "card.png"',
        b'[images]\nok = 123',
        b'unknown = true\n[images]\nok = "card.png"',
        b'[images]\nok = "card.png"\nunused = 123',
    ),
)
def test_select_when_map_is_invalid_raises_value_error(map_path: Path, document: bytes) -> None:
    map_path.write_bytes(document)

    with pytest.raises(ValueError):
        ImageSelector().select(map_path, BytesIO(b"ok"))


@pytest.mark.parametrize("asset", ("missing.png", "", ".", " "))
def test_select_when_asset_is_unreadable_raises_os_error(map_path: Path, asset: str) -> None:
    map_path.write_text(f'[images]\nok = "{asset}"\n')

    with pytest.raises(OSError):
        ImageSelector().select(map_path, BytesIO(b"ok"))


def test_select_when_map_is_missing_raises_os_error(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        ImageSelector().select(tmp_path / "missing.toml", BytesIO(b"ok"))


def test_select_when_stream_read_fails_raises_os_error() -> None:
    stream = Mock(spec=BytesIO)
    stream.read.side_effect = OSError("cannot read stdin")

    with pytest.raises(OSError, match="cannot read stdin"):
        ImageSelector().select(Path("images.toml"), stream)


def test_load_png_when_image_is_valid_returns_decoded_pixels(png: bytes) -> None:
    result = load_png(BytesIO(png))

    assert result.tobytes() == b"\xff" * (1280 * 720)


@pytest.mark.parametrize("cut", (1, 4, 8, 12, 20))
def test_load_png_when_image_is_truncated_raises_value_error(png: bytes, cut: int) -> None:
    with pytest.raises(ValueError):
        load_png(BytesIO(png[:-cut]))


def test_load_png_when_chunk_checksum_is_corrupt_raises_value_error(png: bytes) -> None:
    damaged = bytearray(png)
    damaged[png.index(b"IDAT") + 4] ^= 1

    with pytest.raises(ValueError):
        load_png(BytesIO(damaged))


def test_load_png_when_pixels_cannot_decode_raises_value_error(png: bytes) -> None:
    start = png.index(b"IDAT") - 4
    length = int.from_bytes(png[start : start + 4])
    chunk = b"IDATinvalid deflate pixels"
    damaged = png[:start] + (len(chunk) - 4).to_bytes(4) + chunk + crc32(chunk).to_bytes(4) + png[start + length + 12 :]

    with pytest.raises(ValueError):
        load_png(BytesIO(damaged))


@pytest.mark.parametrize(("format", "size"), (("JPEG", (1280, 720)), ("PNG", (1279, 720)), ("PNG", (1280, 719))))
def test_load_png_when_format_or_size_is_wrong_raises_value_error(format: str, size: tuple[int, int]) -> None:
    stream = BytesIO()
    Image.new("L", size).save(stream, format=format)

    with pytest.raises(ValueError):
        load_png(stream)


def test_load_png_when_image_is_animated_raises_value_error() -> None:
    stream = BytesIO()
    Image.new("L", (1280, 720), 0).save(
        stream, format="PNG", save_all=True, append_images=[Image.new("L", (1280, 720), 255)]
    )

    with pytest.raises(ValueError, match="Animated"):
        load_png(stream)


def test_load_png_when_stream_is_a_file_returns_decoded_pixels(tmp_path: Path, png: bytes) -> None:
    image_path = tmp_path / "card.png"
    image_path.write_bytes(png)

    with image_path.open("rb") as stream:
        result = load_png(stream)

    assert result.tobytes() == b"\xff" * (1280 * 720)


def test_load_png_when_image_is_valid_returns_with_stream_open(png: bytes) -> None:
    with BytesIO(png) as stream:
        load_png(stream)

        assert not stream.closed


def test_load_png_when_image_is_invalid_returns_with_stream_open() -> None:
    with BytesIO(b"not PNG") as stream:
        with pytest.raises(ValueError):
            load_png(stream)

        assert not stream.closed


def test_select_when_selected_asset_is_invalid_raises_value_error(map_path: Path) -> None:
    (map_path.parent / "card.png").write_bytes(b"invalid image")

    with pytest.raises(ValueError):
        ImageSelector().select(map_path, BytesIO(b"ok"))


def test_image_match_when_token_matches_returns_original_png(map_path: Path, png: bytes) -> None:
    result = CliRunner().invoke(mysign, ["image", "match", "--map", str(map_path)], input=b"ok\n")

    assert result.stdout_bytes == png


def test_image_match_when_token_matches_returns_no_diagnostic(map_path: Path) -> None:
    result = CliRunner().invoke(mysign, ["image", "match", "--map", str(map_path)], input=b"ok")

    assert result.stderr == ""


@pytest.mark.parametrize("failure", ("map-missing", "map-invalid", "asset-invalid"))
def test_image_match_when_files_are_invalid_returns_no_image(map_path: Path, failure: str) -> None:
    if failure == "map-missing":
        map_path = map_path.with_name("missing.toml")
    elif failure == "map-invalid":
        map_path.write_bytes(b"not TOML")
    else:
        (map_path.parent / "card.png").write_bytes(b"not PNG")

    result = CliRunner().invoke(mysign, ["image", "match", "--map", str(map_path)], input=b"ok")

    assert (result.exit_code, result.stdout_bytes) == (1, b"")


def test_image_match_when_help_is_requested_calls_no_selector() -> None:
    operations = Mock(spec=ImageSelector)

    CliRunner().invoke(mysign, ["image", "match", "--help"], obj=operations)

    assert operations.mock_calls == []


def test_image_match_when_invoked_calls_selector_with_map_and_binary_stdin() -> None:
    operations = Mock(spec=ImageSelector, select=Mock(return_value=b"PNG bytes"))

    CliRunner().invoke(mysign, ["image", "match", "--map", "images.toml"], input=b"ok\n", obj=operations)

    assert (operations.select.call_args.args[0], operations.select.call_args.args[1].getvalue()) == (
        Path("images.toml"),
        b"ok\n",
    )


@pytest.mark.parametrize("error", (OSError("read failed"), ValueError("invalid image")))
def test_image_match_when_selection_fails_returns_no_image(error: Exception) -> None:
    operations = Mock(spec=ImageSelector)
    operations.select.side_effect = error

    result = CliRunner().invoke(mysign, ["image", "match", "--map", "images.toml"], input=b"ok", obj=operations)

    assert (result.exit_code, result.stdout_bytes) == (1, b"")


def test_image_match_when_selection_fails_returns_diagnostic_on_stderr() -> None:
    operations = Mock(spec=ImageSelector)
    operations.select.side_effect = OSError("read failed")

    result = CliRunner().invoke(mysign, ["image", "match", "--map", "images.toml"], input=b"ok", obj=operations)

    assert result.stderr == "Error: Cannot select image: read failed\n"


@pytest.mark.parametrize("token", (b"unknown", b"missing", b"\xff", b"ok\n\n"))
def test_image_match_when_input_cannot_select_an_image_returns_no_image(map_path: Path, token: bytes) -> None:
    result = CliRunner().invoke(mysign, ["image", "match", "--map", str(map_path)], input=token)

    assert (result.exit_code, result.stdout_bytes) == (1, b"")


@pytest.mark.parametrize("arguments", ([], ["--map", "images.toml", "--unknown"]))
def test_image_match_when_options_are_invalid_returns_usage_error(arguments: list[str]) -> None:
    result = CliRunner().invoke(mysign, ["image", "match", *arguments])

    assert result.exit_code == 2
