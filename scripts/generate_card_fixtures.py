"""Regenerate synthetic card examples without redistributing artwork or font files."""

import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont

from greg_mitchell.pwn_my_sign.images.card import CardRenderer, CardSpec
from greg_mitchell.pwn_my_sign.images.layout import CardLayout


def main() -> None:
    """Render review fixtures using schematic art and Pillow's bundled test font."""
    root = Path(__file__).resolve().parents[1]
    destination = root / "tests/fixtures/cards"
    destination.mkdir(parents=True, exist_ok=True)
    split = CardLayout.model_validate(tomllib.loads((root / "data/card-layout.toml").read_text()))
    artwork_only = CardLayout.model_validate(tomllib.loads((root / "data/artwork-layout.toml").read_text()))
    alternate = split.model_dump()
    alternate.update(safe_margin=64, artwork={"x": 64, "y": 64, "width": 400, "height": 592})
    alternate["text"].update(x=496, y=64, width=720, height=592, title_size=48)
    with TemporaryDirectory() as directory:
        temporary = Path(directory)
        artwork = temporary / "artwork.png"
        art = Image.new("RGB", (480, 320), "white")
        draw = ImageDraw.Draw(art)
        draw.rectangle((0, 0, 479, 319), outline="black", width=8)
        draw.ellipse((120, 40, 360, 280), fill=(96, 96, 96), outline="black", width=8)
        draw.rectangle((200, 120, 280, 200), fill="white")
        art.save(artwork)
        bundled = ImageFont.load_default()
        if not isinstance(bundled, ImageFont.FreeTypeFont):
            raise TypeError("Fixture generation requires Pillow's bundled TrueType font.")
        font = temporary / "font.ttf"
        font.write_bytes(bundled.font_bytes)
        cases = (
            (
                "split-wrapped",
                split,
                "Service health overview",
                "All systems operational",
                "Synthetic artwork.\nReady for work.",
            ),
            ("title-only", split, "Service health", "", ""),
            ("artwork-only", artwork_only, "", "", ""),
            (
                "alternate-layout",
                CardLayout.model_validate(alternate),
                "Service health",
                "Operational",
                "A larger safe margin.",
            ),
        )
        for name, layout, title, status, caption in cases:
            spec = CardSpec(artwork=artwork, layout=layout, font=font, title=title, status=status, caption=caption)
            (destination / f"{name}.png").write_bytes(CardRenderer().render(spec))


if __name__ == "__main__":
    main()
