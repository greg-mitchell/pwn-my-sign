from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, ConfigDict

from greg_mitchell.pwn_my_sign.frame_codec import HEIGHT, WIDTH
from greg_mitchell.pwn_my_sign.images.layout import CardLayout


class CardSpec(BaseModel):
    """Explicit artwork, font, and text for one static display card."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artwork: Path
    layout: CardLayout
    font: Path | None = None
    title: str = ""
    status: str = ""
    caption: str = ""


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> tuple[str, ...]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            left, _, right, _ = font.getbbox(word)
            if right - left > width:
                raise ValueError("A word is too wide for the text column.")
            candidate = f"{line} {word}" if line else word
            left, _, right, _ = font.getbbox(candidate)
            if right - left > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return tuple(lines)


def _draw_text(image: Image.Image, spec: CardSpec) -> None:
    text_box = spec.layout.text
    if text_box is None:
        if any(text.strip() for text in (spec.title, spec.status, spec.caption)):
            raise ValueError("A text region is required when card text is supplied.")
        return
    draw = ImageDraw.Draw(image)
    y = text_box.y
    blocks = (
        (spec.title, text_box.title_size),
        (spec.status, text_box.status_size),
        (spec.caption, text_box.caption_size),
    )
    for text, size in blocks:
        if not text.strip():
            continue
        if spec.font is None:
            raise ValueError("A font is required when card text is supplied.")
        font = ImageFont.truetype(str(spec.font), size)
        ascent, descent = font.getmetrics()
        if y > text_box.y:
            y += text_box.block_spacing
        for index, line in enumerate(_wrap(text, font, text_box.width)):
            if index:
                y += text_box.line_spacing
            left, top, _, bottom = font.getbbox(line)
            height = max(ascent + descent, bottom - top)
            if y + height > text_box.y + text_box.height:
                raise ValueError("Card text does not fit within the content inset.")
            draw.text((text_box.x - left, y - top), line, font=font, fill=0)
            y += height


class CardRenderer:
    """Render complete grayscale PNGs with contained art and fixed-size text."""

    def render(self, spec: CardSpec) -> bytes:
        """Build a deterministic card, rejecting artwork or text that cannot be rendered."""
        with Image.open(spec.artwork) as source:
            if getattr(source, "is_animated", False):
                raise ValueError("Animated artwork is not supported.")
            source.load()
            artwork = ImageOps.exif_transpose(source).convert("RGBA")
        background = Image.new("RGBA", artwork.size, "white")
        background.alpha_composite(artwork)
        art_box = spec.layout.artwork
        artwork = ImageOps.contain(background.convert("L"), (art_box.width, art_box.height))
        image = Image.new("L", (WIDTH, HEIGHT), 255)
        image.paste(
            artwork,
            (art_box.x + (art_box.width - artwork.width) // 2, art_box.y + (art_box.height - artwork.height) // 2),
        )
        _draw_text(image, spec)
        with BytesIO() as stream:
            image.save(stream, format="PNG")
            return stream.getvalue()
