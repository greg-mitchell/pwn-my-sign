from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, ConfigDict, field_validator


class CardSpec(BaseModel):
    """Explicit artwork, font, and text for one static display card."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artwork: Path
    font: Path
    title: str
    status: str
    caption: str

    @field_validator("title", "status", "caption")
    @classmethod
    def require_text(cls, value: str) -> str:
        """Require visible text without changing the supplied line breaks."""
        if not value.strip():
            raise ValueError("Card text must not be blank.")
        return value


def _wrap(text: str, font: ImageFont.FreeTypeFont) -> tuple[str, ...]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            left, _, right, _ = font.getbbox(word)
            if right - left > 592:
                raise ValueError("A word is too wide for the text column.")
            candidate = f"{line} {word}" if line else word
            left, _, right, _ = font.getbbox(candidate)
            if right - left > 592:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return tuple(lines)


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
        artwork = ImageOps.contain(background.convert("L"), (592, 656))
        image = Image.new("L", (1280, 720), 255)
        image.paste(artwork, (32 + (592 - artwork.width) // 2, 32 + (656 - artwork.height) // 2))
        draw = ImageDraw.Draw(image)
        y = 32
        for text, size in ((spec.title, 56), (spec.status, 40), (spec.caption, 32)):
            font = ImageFont.truetype(str(spec.font), size)
            ascent, descent = font.getmetrics()
            for line in _wrap(text, font):
                left, top, right, bottom = font.getbbox(line)
                height = max(ascent + descent, bottom - top)
                if y + height > 688:
                    raise ValueError("Card text does not fit within the content inset.")
                draw.text((656 - left, y - top), line, font=font, fill=0)
                y += height + 8
            y += 8
        with BytesIO() as stream:
            image.save(stream, format="PNG")
            return stream.getvalue()
