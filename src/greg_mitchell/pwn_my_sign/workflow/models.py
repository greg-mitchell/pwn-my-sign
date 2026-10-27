from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowKind(StrEnum):
    POLL = "poll"
    UPLOAD = "upload"
    WATCH = "watch"


class PollSettings(BaseModel):
    """Explicit inputs for producing a desired image."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command: tuple[str, ...] = ()
    image_path: Path | None = None

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if bool(self.command) == (self.image_path is not None):
            raise ValueError("Provide either an image path or a producer command.")
        if self.command and not self.command[0]:
            raise ValueError("The producer executable must not be empty.")
        return self


class UploadSettings(BaseModel):
    """The selected device for foreground transfers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    device: Annotated[str, Field(min_length=1)]


class WatchSettings(BaseModel):
    """Foreground polling and reminder settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    poll: PollSettings
    upload: UploadSettings
    interval: Annotated[int, Field(gt=0, strict=True)] = 300

    @model_validator(mode="after")
    def validate_repeatable_source(self) -> Self:
        if not self.poll.command:
            raise ValueError("Watching requires a repeatable producer command.")
        return self
