from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from PIL import Image, ImageChops, ImageFont

from greg_mitchell.pwn_my_sign.cli.mysign import main as mysign
from greg_mitchell.pwn_my_sign.images.card import CardRenderer, CardSpec


@pytest.fixture
def spec(tmp_path: Path) -> CardSpec:
    artwork = tmp_path / "art.png"
    Image.new("RGB", (100, 100), "black").save(artwork)
    font = tmp_path / "font.ttf"
    bundled = ImageFont.load_default()
    if not isinstance(bundled, ImageFont.FreeTypeFont):
        raise TypeError("Card tests require Pillow's bundled TrueType font.")
    font.write_bytes(bundled.font_bytes)
    return CardSpec(artwork=artwork, font=font, title="Service", status="Operational", caption="All systems healthy")


@pytest.fixture
def arguments(spec: CardSpec) -> list[str]:
    return [
        "image",
        "make",
        "--artwork",
        str(spec.artwork),
        "--font",
        str(spec.font),
        "--title",
        spec.title,
        "--status",
        spec.status,
        "--caption",
        spec.caption,
    ]


def test_render_when_inputs_are_identical_returns_identical_png(spec: CardSpec) -> None:
    first = CardRenderer().render(spec)

    result = CardRenderer().render(spec)

    assert result == first


def test_render_when_inputs_are_valid_returns_sign_sized_grayscale_png(spec: CardSpec) -> None:
    result = CardRenderer().render(spec)

    with Image.open(BytesIO(result)) as image:
        assert (image.format, image.mode, image.size) == ("PNG", "L", (1280, 720))


def test_render_when_art_is_square_returns_contained_art(spec: CardSpec) -> None:
    result = CardRenderer().render(spec)

    with Image.open(BytesIO(result)) as image:
        assert ImageChops.invert(image.crop((0, 0, 640, 720))).getbbox() == (32, 64, 624, 656)


def test_render_when_art_is_wide_returns_full_uncropped_art(spec: CardSpec) -> None:
    art = Image.new("L", (200, 100), 0)
    art.paste(128, (100, 0, 200, 100))
    art.save(spec.artwork)

    result = CardRenderer().render(spec)

    with Image.open(BytesIO(result)) as image:
        assert (image.getpixel((32, 360)), image.getpixel((623, 360))) == (0, 128)


def test_render_when_art_has_orientation_returns_upright_art(spec: CardSpec) -> None:
    art = Image.new("RGB", (200, 100), "black")
    exif = Image.Exif()
    exif[274] = 6
    art.save(spec.artwork, exif=exif)

    result = CardRenderer().render(spec)

    with Image.open(BytesIO(result)) as image:
        assert ImageChops.invert(image.crop((0, 0, 640, 720))).getbbox() == (164, 32, 492, 688)


def test_render_when_art_is_transparent_returns_white_background(spec: CardSpec) -> None:
    Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(spec.artwork)

    result = CardRenderer().render(spec)

    with Image.open(BytesIO(result)) as image:
        assert image.getpixel((328, 360)) == 255


def test_render_when_art_has_partial_alpha_returns_composited_gray(spec: CardSpec) -> None:
    Image.new("RGBA", (100, 100), (0, 0, 0, 128)).save(spec.artwork)

    result = CardRenderer().render(spec)

    with Image.open(BytesIO(result)) as image:
        assert image.getpixel((328, 360)) == 127


def test_render_when_text_is_supplied_returns_visible_text(spec: CardSpec) -> None:
    result = CardRenderer().render(spec)

    with Image.open(BytesIO(result)) as image:
        assert ImageChops.invert(image.crop((656, 32, 1248, 688))).getbbox() is not None


def test_render_when_content_is_valid_returns_blank_outer_inset(spec: CardSpec) -> None:
    result = CardRenderer().render(spec)

    with Image.open(BytesIO(result)) as image:
        ink = ImageChops.invert(image)
        ink.paste(0, (32, 32, 1248, 688))
        assert ink.getbbox() is None


def test_render_when_title_needs_wrapping_returns_same_as_explicit_newline(spec: CardSpec) -> None:
    expected = CardRenderer().render(spec.model_copy(update={"title": "Operational\nOperational"}))

    result = CardRenderer().render(spec.model_copy(update={"title": "Operational Operational"}))

    assert result == expected


def test_render_when_text_contains_newline_returns_different_layout(spec: CardSpec) -> None:
    original = CardRenderer().render(spec)

    result = CardRenderer().render(spec.model_copy(update={"caption": "All systems\nhealthy"}))

    assert result != original


@pytest.mark.parametrize("text", ("W" * 100, "word\n" * 100, "word " * 1000))
def test_render_when_text_overflows_raises_value_error(spec: CardSpec, text: str) -> None:
    settings = spec.model_copy(update={"title": text})

    with pytest.raises(ValueError, match="wide|fit"):
        CardRenderer().render(settings)


@pytest.mark.parametrize("field", ("artwork", "font"))
def test_render_when_asset_is_missing_raises_os_error(spec: CardSpec, tmp_path: Path, field: str) -> None:
    settings = spec.model_copy(update={field: tmp_path / "missing"})

    with pytest.raises(OSError):
        CardRenderer().render(settings)


@pytest.mark.parametrize("field", ("artwork", "font"))
def test_render_when_asset_is_malformed_raises_os_error(spec: CardSpec, field: str) -> None:
    getattr(spec, field).write_bytes(b"not an asset")

    with pytest.raises(OSError):
        CardRenderer().render(spec)


def test_render_when_art_is_animated_raises_value_error(spec: CardSpec) -> None:
    Image.new("L", (10, 10), 0).save(spec.artwork, save_all=True, append_images=[Image.new("L", (10, 10), 255)])

    with pytest.raises(ValueError, match="Animated"):
        CardRenderer().render(spec)


def test_make_when_options_are_supplied_calls_renderer_with_spec(spec: CardSpec, arguments: list[str]) -> None:
    renderer = Mock(spec=CardRenderer)
    renderer.render.return_value = b"png"

    CliRunner().invoke(mysign, arguments, obj=renderer, catch_exceptions=False)

    renderer.render.assert_called_once_with(spec)


def test_make_when_output_is_omitted_returns_png_stdout(arguments: list[str]) -> None:
    result = CliRunner().invoke(mysign, arguments, catch_exceptions=False)

    with Image.open(BytesIO(result.stdout_bytes)) as image:
        assert image.size == (1280, 720)


def test_make_when_output_is_named_returns_png_file(arguments: list[str], tmp_path: Path) -> None:
    output = tmp_path / "card.png"

    CliRunner().invoke(mysign, [*arguments, "--output", str(output)], catch_exceptions=False)

    with Image.open(output) as image:
        assert image.size == (1280, 720)


def test_make_when_output_is_named_returns_empty_stdout(arguments: list[str], tmp_path: Path) -> None:
    result = CliRunner().invoke(mysign, [*arguments, "--output", str(tmp_path / "card.png")])

    assert result.stdout_bytes == b""


@pytest.mark.parametrize("error", (ValueError("does not fit"), OSError("cannot read")))
def test_make_when_rendering_fails_returns_error_stderr(arguments: list[str], error: Exception) -> None:
    renderer = Mock(spec=CardRenderer)
    renderer.render.side_effect = error

    result = CliRunner().invoke(mysign, arguments, obj=renderer)

    assert result.stderr == f"Error: Cannot build card: {error}\n"


def test_make_when_rendering_fails_returns_no_stdout(arguments: list[str]) -> None:
    renderer = Mock(spec=CardRenderer)
    renderer.render.side_effect = ValueError("does not fit")

    result = CliRunner().invoke(mysign, arguments, obj=renderer)

    assert result.stdout_bytes == b""


def test_make_when_rendering_fails_returns_preserved_output(arguments: list[str], tmp_path: Path) -> None:
    output = tmp_path / "card.png"
    output.write_bytes(b"previous card")
    renderer = Mock(spec=CardRenderer)
    renderer.render.side_effect = ValueError("does not fit")

    CliRunner().invoke(mysign, [*arguments, "--output", str(output)], obj=renderer)

    assert output.read_bytes() == b"previous card"


def test_make_when_output_parent_is_missing_returns_failure(arguments: list[str], tmp_path: Path) -> None:
    result = CliRunner().invoke(mysign, [*arguments, "--output", str(tmp_path / "missing" / "card.png")])

    assert result.exit_code == 1


@pytest.mark.parametrize("option", ("--title", "--status", "--caption"))
def test_make_when_text_is_blank_returns_failure(arguments: list[str], option: str) -> None:
    arguments[arguments.index(option) + 1] = " \n "

    result = CliRunner().invoke(mysign, arguments)

    assert result.exit_code == 1
