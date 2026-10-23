import tomllib
from io import BytesIO
from pathlib import Path
from typing import Annotated, BinaryIO

from pydantic import BaseModel, ConfigDict, Field

from greg_mitchell.pwn_my_sign.images.png import load_png

Token = Annotated[str, Field(min_length=1, pattern=r"^\S+$")]


class ImageMap(BaseModel):
    """Explicit token-to-asset settings with no implicit fallback."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    images: Annotated[dict[Token, Path], Field(min_length=1)]


class ImageSelector:
    def select(self, map_path: Path, source: BinaryIO) -> bytes:
        """Select and validate the original PNG bytes for one exact stdin token."""
        token = source.read().decode("utf-8")
        if token.endswith("\r\n"):
            token = token[:-2]
        elif token.endswith("\n"):
            token = token[:-1]
        if not token or any(character.isspace() for character in token):
            raise ValueError("Expected one exact status token, optionally followed by one newline.")
        settings = ImageMap.model_validate(tomllib.loads(map_path.read_bytes().decode("utf-8")))
        if token not in settings.images:
            raise ValueError(f"No image mapped for token {token!r}.")
        image_path = map_path.parent / settings.images[token]
        data = image_path.read_bytes()
        with BytesIO(data) as stream:
            load_png(stream).close()
        return data
