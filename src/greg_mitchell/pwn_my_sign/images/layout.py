from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from greg_mitchell.pwn_my_sign.frame_codec import HEIGHT, WIDTH


class VerticalAlignment(StrEnum):
    """Vertical placement of contained content within its layout box."""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class Box(BaseModel):
    """A pixel rectangle in canvas coordinates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    vertical_alignment: VerticalAlignment


class TextBox(Box):
    """Text placement and typography for the optional card text blocks."""

    title_size: int = Field(gt=0)
    status_size: int = Field(gt=0)
    caption_size: int = Field(gt=0)
    line_spacing: int = Field(ge=0)
    block_spacing: int = Field(ge=0)


class CardLayout(BaseModel):
    """Explicit layout settings constrained to the sign canvas."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artwork: Box
    text: TextBox | None = None

    @model_validator(mode="after")
    def require_canvas_boxes(self) -> Self:
        """Keep both boxes inside the canvas and separate from each other."""
        boxes = (self.artwork,) if self.text is None else (self.artwork, self.text)
        for box in boxes:
            if box.x + box.width > WIDTH or box.y + box.height > HEIGHT:
                raise ValueError("Layout boxes must fit inside the canvas.")
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
