from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class WorkflowKind(StrEnum):
    POLL = "poll"
    UPLOAD = "upload"
    WATCH = "watch"


class PollSettings(BaseModel):
    """Explicit inputs for producing a desired image."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    map_path: Path
    policy_path: Path | None = None


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
