import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, BinaryIO

from pydantic import BaseModel, ConfigDict, Field

from greg_mitchell.pwn_my_sign.images.png import load_png

Token = Annotated[str, Field(min_length=1, pattern=r"^\S+$")]
ReadBytes = Callable[[Path], bytes]


class ImageMap(BaseModel):
    """Explicit token-to-asset settings with no implicit fallback."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    images: Annotated[dict[Token, Path], Field(min_length=1)]


class ImageSelector:
    def __init__(self, read_bytes: ReadBytes = Path.read_bytes) -> None:
        self.read_bytes = read_bytes

    def select(self, map_path: Path, source: BinaryIO) -> bytes:
        """Select and validate the original PNG bytes for one exact stdin token."""
        token = source.read().decode("utf-8")
        if token.endswith("\r\n"):
            token = token[:-2]
        elif token.endswith("\n"):
            token = token[:-1]
        if not token or any(character.isspace() for character in token):
            raise ValueError("Expected one exact status token, optionally followed by one newline.")
        settings = ImageMap.model_validate(tomllib.loads(self.read_bytes(map_path).decode("utf-8")))
        if token not in settings.images:
            raise ValueError(f"No image mapped for token {token!r}.")
        image_path = map_path.parent / settings.images[token]
        data = self.read_bytes(image_path)
        load_png(data)
        return data
