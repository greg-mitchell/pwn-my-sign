from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageText
from pydantic import BaseModel, ConfigDict

from greg_mitchell.pwn_my_sign.frame_codec import HEIGHT, WIDTH
from greg_mitchell.pwn_my_sign.images.layout import CardLayout, VerticalAlignment


class CardSpec(BaseModel):
    """Explicit artwork, font, and text for one static display card."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artwork: Path
    layout: CardLayout
    font: Path | None = None
    title: str = ""
    status: str = ""
    caption: str = ""


def _alignment_fraction(alignment: VerticalAlignment) -> float:
    return {VerticalAlignment.TOP: 0.0, VerticalAlignment.CENTER: 0.5, VerticalAlignment.BOTTOM: 1.0}[alignment]


def _draw_text(image: Image.Image, spec: CardSpec) -> None:
    text_box = spec.layout.text
    if text_box is None:
        if any(text.strip() for text in (spec.title, spec.status, spec.caption)):
            raise ValueError("A text region is required when card text is supplied.")
        return
    blocks = (
        (spec.title, text_box.title_size),
        (spec.status, text_box.status_size),
        (spec.caption, text_box.caption_size),
    )
    measured: list[tuple[ImageText.Text[str], tuple[float, float, float, float]]] = []
    for text, size in blocks:
        if not text.strip():
            continue
        if spec.font is None:
            raise ValueError("A font is required when card text is supplied.")
        font = ImageFont.truetype(str(spec.font), size)
        block = ImageText.Text(text, font=font, spacing=text_box.line_spacing)
        block.wrap(text_box.width)
        bounds = block.get_bbox()
        if bounds[2] - bounds[0] > text_box.width:
            raise ValueError("Card text does not fit within the text box width.")
        measured.append((block, bounds))
    height = sum(bounds[3] - bounds[1] for _, bounds in measured)
    height += max(0, len(measured) - 1) * text_box.block_spacing
    if height > text_box.height:
        raise ValueError("Card text does not fit within the text box height.")
    y = text_box.y + int((text_box.height - height) * _alignment_fraction(text_box.vertical_alignment))
    draw = ImageDraw.Draw(image)
    for block, (left, top, _, bottom) in measured:
        draw.text((text_box.x - left, y - top), block, fill=0)
        y += bottom - top + text_box.block_spacing


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
        artwork = ImageOps.pad(
            background.convert("L"),
            (art_box.width, art_box.height),
            color=255,
            centering=(0.5, _alignment_fraction(art_box.vertical_alignment)),
        )
        image = Image.new("L", (WIDTH, HEIGHT), 255)
        image.paste(artwork, (art_box.x, art_box.y))
        _draw_text(image, spec)
        with BytesIO() as stream:
            image.save(stream, format="PNG")
            return stream.getvalue()
