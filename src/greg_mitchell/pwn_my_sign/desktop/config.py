import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class DesktopSettings(BaseModel):
    """Explicit private producer, device, state, and timing settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command: Annotated[tuple[str, ...], Field(min_length=1)]
    working_directory: Path
    state_directory: Path
    device: Annotated[str, Field(min_length=1)]
    interval: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)] = 300
    notification_timeout: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)] = 15


def load_settings(path: Path) -> DesktopSettings:
    """Resolve explicit paths against the configuration and producer working directory."""
    path = path.resolve()
    with path.open("rb") as stream:
        settings = DesktopSettings.model_validate(tomllib.load(stream))
    working = (path.parent / settings.working_directory).resolve()
    state = (path.parent / settings.state_directory).resolve()
    executable = settings.command[0]
    if not executable:
        raise ValueError("The producer executable must not be empty.")
    return DesktopSettings(
        command=(str((working / executable).resolve()), *settings.command[1:]),
        working_directory=working,
        state_directory=state,
        device=settings.device,
        interval=settings.interval,
        notification_timeout=settings.notification_timeout,
    )
