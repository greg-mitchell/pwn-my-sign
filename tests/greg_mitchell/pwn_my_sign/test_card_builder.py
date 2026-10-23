import tomllib
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from PIL import Image, ImageChops, ImageFont

from greg_mitchell.pwn_my_sign.cli.mysign import main as mysign
from greg_mitchell.pwn_my_sign.images.card import CardRenderer, CardSpec
from greg_mitchell.pwn_my_sign.images.layout import CardLayout


@pytest.fixture
def spec(tmp_path: Path) -> CardSpec:
    artwork = tmp_path / "art.png"
    Image.new("RGB", (100, 100), "black").save(artwork)
    font = tmp_path / "font.ttf"
    bundled = ImageFont.load_default()
    if not isinstance(bundled, ImageFont.FreeTypeFont):
        raise TypeError("Card tests require Pillow's bundled TrueType font.")
    font.write_bytes(bundled.font_bytes)
    layout = CardLayout.model_validate(tomllib.loads(Path("data/card-layout.toml").read_text()))
    return CardSpec(
        artwork=artwork, layout=layout, font=font, title="Service", status="Operational", caption="All systems healthy"
    )


@pytest.fixture
def arguments(spec: CardSpec) -> list[str]:
    return [
        "image",
        "make",
        "--layout",
        "data/card-layout.toml",
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


def test_render_when_split_layout_is_selected_returns_vertically_centered_text_stack(spec: CardSpec) -> None:
    result = CardRenderer().render(spec)

    with Image.open(BytesIO(result)) as image:
        bounds = ImageChops.invert(image.crop((656, 0, 1248, 720))).getbbox()
        assert bounds is not None and abs((bounds[1] + bounds[3]) / 2 - 360) <= 1


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
    path = getattr(spec, field)
    path.write_bytes(b"not an asset")

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
def test_make_when_text_is_blank_returns_success(arguments: list[str], option: str) -> None:
    arguments[arguments.index(option) + 1] = " \n "

    result = CliRunner().invoke(mysign, arguments)

    assert result.exit_code == 0


def test_make_when_text_and_font_are_omitted_returns_success(spec: CardSpec) -> None:
    result = CliRunner().invoke(
        mysign, ["image", "make", "--layout", "data/card-layout.toml", "--artwork", str(spec.artwork)]
    )

    assert result.exit_code == 0


def test_render_when_font_is_unused_returns_art_only_png(spec: CardSpec, tmp_path: Path) -> None:
    settings = CardSpec(artwork=spec.artwork, layout=spec.layout, font=tmp_path / "missing.ttf")

    result = CardRenderer().render(settings)

    with Image.open(BytesIO(result)) as image:
        assert image.crop((656, 32, 1248, 688)).getextrema() == (255, 255)


def test_render_when_visible_text_has_no_font_raises_value_error(spec: CardSpec) -> None:
    settings = spec.model_copy(update={"font": None})

    with pytest.raises(ValueError, match="font is required"):
        CardRenderer().render(settings)


def test_render_when_text_region_is_absent_returns_full_artwork(spec: CardSpec) -> None:
    layout = CardLayout.model_validate(tomllib.loads(Path("data/artwork-layout.toml").read_text()))
    settings = CardSpec(artwork=spec.artwork, layout=layout)

    result = CardRenderer().render(settings)

    with Image.open(BytesIO(result)) as image:
        assert ImageChops.invert(image).getbbox() == (280, 0, 1000, 720)


def test_make_when_artwork_reaches_canvas_edges_returns_full_artwork(spec: CardSpec, tmp_path: Path) -> None:
    Image.new("L", (1280, 720), 0).save(spec.artwork)
    template = Path("data/artwork-layout.toml").read_text()
    template = template.replace("x = 32", "x = 0").replace("y = 32", "y = 0")
    template = template.replace("width = 1216", "width = 1280").replace("height = 656", "height = 720")
    layout = tmp_path / "edge-layout.toml"
    layout.write_text(template)

    result = CliRunner().invoke(mysign, ["image", "make", "--layout", str(layout), "--artwork", str(spec.artwork)])

    assert result.exit_code == 0, result.stderr


def test_render_when_text_region_is_absent_with_visible_text_raises_value_error(spec: CardSpec) -> None:
    layout = CardLayout.model_validate(tomllib.loads(Path("data/artwork-layout.toml").read_text()))
    settings = spec.model_copy(update={"layout": layout})

    with pytest.raises(ValueError, match="text region is required"):
        CardRenderer().render(settings)


def test_render_when_artwork_is_below_text_returns_selected_geometry(spec: CardSpec) -> None:
    layout = spec.layout.model_dump()
    layout["artwork"].update(x=32, y=360, width=1216, height=328)
    layout["text"].update(x=32, y=32, width=1216, height=296)
    settings = spec.model_copy(update={"layout": CardLayout.model_validate(layout)})

    result = CardRenderer().render(settings)

    with Image.open(BytesIO(result)) as image:
        assert ImageChops.invert(image.crop((0, 360, 1280, 720))).getbbox() == (476, 0, 804, 328)


@pytest.mark.parametrize("name", ("split-wrapped", "title-only", "artwork-only", "alternate-layout"))
def test_fixture_when_card_is_loaded_returns_sign_sized_grayscale_png(name: str) -> None:
    with Image.open(Path("tests/fixtures/cards") / f"{name}.png") as image:
        bounds = ImageChops.invert(image).getbbox()

        assert (
            image.mode == "L"
            and image.size == (1280, 720)
            and bounds is not None
            and bounds[0] >= 0
            and bounds[1] >= 0
            and bounds[2] <= 1280
            and bounds[3] <= 720
        )


def test_fixture_when_artwork_only_is_loaded_returns_art_at_canvas_edge() -> None:
    with Image.open("tests/fixtures/cards/artwork-only.png") as image:
        result = image.getpixel((640, 0))

    assert result == 0


def test_render_when_title_and_status_are_blank_returns_centered_caption(spec: CardSpec) -> None:
    settings = spec.model_copy(update={"title": " \n", "status": ""})

    result = CardRenderer().render(settings)

    with Image.open(BytesIO(result)) as image:
        bounds = ImageChops.invert(image.crop((656, 0, 1248, 720))).getbbox()
        assert bounds is not None and abs((bounds[1] + bounds[3]) / 2 - 360) <= 1


def test_render_when_layout_has_different_boxes_returns_repositioned_art(spec: CardSpec) -> None:
    layout = spec.layout.model_dump()
    layout["artwork"].update(x=64, y=64, width=400, height=592)
    layout["text"].update(x=496, y=64, width=720, height=592)
    settings = spec.model_copy(update={"layout": CardLayout.model_validate(layout)})

    result = CardRenderer().render(settings)

    with Image.open(BytesIO(result)) as image:
        assert ImageChops.invert(image.crop((0, 0, 480, 720))).getbbox() == (64, 160, 464, 560)


def test_render_when_text_box_is_narrower_raises_word_overflow(spec: CardSpec) -> None:
    layout = spec.layout.model_dump()
    layout["text"]["width"] = 50
    settings = spec.model_copy(update={"layout": CardLayout.model_validate(layout)})

    with pytest.raises(ValueError, match="fit"):
        CardRenderer().render(settings)


def test_render_when_font_size_changes_returns_different_text(spec: CardSpec) -> None:
    original = CardRenderer().render(spec)
    layout = spec.layout.model_dump()
    layout["text"]["title_size"] = 24
    settings = spec.model_copy(update={"layout": CardLayout.model_validate(layout)})

    result = CardRenderer().render(settings)

    assert result != original


def test_render_when_text_box_is_shorter_raises_vertical_overflow(spec: CardSpec) -> None:
    layout = spec.layout.model_dump()
    layout["text"]["height"] = 40
    settings = spec.model_copy(update={"layout": CardLayout.model_validate(layout)})

    with pytest.raises(ValueError, match="fit"):
        CardRenderer().render(settings)


@pytest.mark.parametrize(
    "document",
    (
        "not TOML",
        "[artwork]",
        Path("data/card-layout.toml").read_text().replace("width = 592", "width = 1280"),
        Path("data/card-layout.toml").read_text().replace("x = 656", "x = 32"),
        Path("data/card-layout.toml").read_text().replace("title_size = 56", "title_size = 0"),
    ),
    ids=("malformed", "incomplete", "outside-canvas", "overlapping", "invalid-size"),
)
def test_make_when_layout_is_invalid_returns_no_stdout(arguments: list[str], tmp_path: Path, document: str) -> None:
    path = tmp_path / "layout.toml"
    path.write_text(document)
    arguments[arguments.index("--layout") + 1] = str(path)

    result = CliRunner().invoke(mysign, arguments)

    assert result.stdout_bytes == b""


def test_make_when_layout_is_invalid_returns_preserved_output(arguments: list[str], tmp_path: Path) -> None:
    layout = tmp_path / "invalid.toml"
    layout.write_text("invalid")
    arguments[arguments.index("--layout") + 1] = str(layout)
    output = tmp_path / "card.png"
    output.write_bytes(b"old card")

    CliRunner().invoke(mysign, [*arguments, "--output", str(output)])

    assert output.read_bytes() == b"old card"


@pytest.mark.parametrize(("alignment", "edge"), (("top", 32), ("bottom", 688)))
def test_render_when_art_alignment_is_selected_returns_selected_edge(spec: CardSpec, alignment: str, edge: int) -> None:
    Image.new("L", (200, 100), 0).save(spec.artwork)
    layout = spec.layout.model_dump()
    layout["artwork"]["vertical_alignment"] = alignment
    settings = spec.model_copy(update={"layout": CardLayout.model_validate(layout)})

    result = CardRenderer().render(settings)

    with Image.open(BytesIO(result)) as image:
        bounds = ImageChops.invert(image.crop((0, 0, 640, 720))).getbbox()
        assert bounds is not None and bounds[1 if alignment == "top" else 3] == edge


@pytest.mark.parametrize(("alignment", "edge"), (("top", 32), ("bottom", 688)))
def test_render_when_text_alignment_is_selected_returns_selected_edge(
    spec: CardSpec, alignment: str, edge: int
) -> None:
    layout = spec.layout.model_dump()
    layout["text"]["vertical_alignment"] = alignment
    settings = spec.model_copy(update={"layout": CardLayout.model_validate(layout)})

    result = CardRenderer().render(settings)

    with Image.open(BytesIO(result)) as image:
        bounds = ImageChops.invert(image.crop((656, 0, 1248, 720))).getbbox()
        assert bounds is not None and abs(bounds[1 if alignment == "top" else 3] - edge) <= 1
