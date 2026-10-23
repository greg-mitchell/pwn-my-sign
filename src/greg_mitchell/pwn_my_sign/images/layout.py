from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greg_mitchell.pwn_my_sign.frame_codec import HEIGHT, WIDTH


class Box(BaseModel):
    """A pixel rectangle in canvas coordinates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class TextBox(Box):
    """Text placement and typography for the optional card text blocks."""

    title_size: int = Field(gt=0)
    status_size: int = Field(gt=0)
    caption_size: int = Field(gt=0)
    line_spacing: int = Field(ge=0)
    block_spacing: int = Field(ge=0)


class CardLayout(BaseModel):
    """Explicit layout settings constrained to a sign's safe content area."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    safe_margin: int = Field(ge=0)
    artwork: Box
    text: TextBox | None = None

    @model_validator(mode="after")
    def require_safe_boxes(self) -> Self:
        """Keep both boxes inside the declared margin and separate from each other."""
        boxes = (self.artwork,) if self.text is None else (self.artwork, self.text)
        for box in boxes:
            if (
                box.x < self.safe_margin
                or box.y < self.safe_margin
                or box.x + box.width > WIDTH - self.safe_margin
                or box.y + box.height > HEIGHT - self.safe_margin
            ):
                raise ValueError("Layout boxes must fit inside the canvas safe margin.")
        art, text = self.artwork, self.text
        if text is None:
            return self
        if not (
            art.x + art.width <= text.x
            or text.x + text.width <= art.x
            or art.y + art.height <= text.y
            or text.y + text.height <= art.y
        ):
            raise ValueError("Artwork and text boxes must not overlap.")
        return self
