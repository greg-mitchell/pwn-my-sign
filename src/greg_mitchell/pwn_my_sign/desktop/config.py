import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from greg_mitchell.pwn_my_sign.workflow.paths import default_state_directory


class DesktopSettings(BaseModel):
    """Explicit private producer, device, state, and timing settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command: Annotated[tuple[str, ...], Field(min_length=1)]
    working_directory: Path
    state_directory: Path = Field(default_factory=default_state_directory)
    device: Annotated[str, Field(min_length=1)]
    interval: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)] = 300
    notification_timeout: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)] = 15

    @field_validator("working_directory", "state_directory")
    @classmethod
    def validate_directory(cls, value: Path) -> Path:
        """Expand home notation and reject ambiguous relative directory overrides."""
        expanded = value.expanduser()
        if not expanded.is_absolute():
            raise ValueError("Desktop directories must be absolute paths or start with ~/.")
        return expanded.resolve()


def load_settings(path: Path) -> DesktopSettings:
    """Default directories and resolve the producer from its configured working directory."""
    path = path.expanduser().resolve()
    with path.open("rb") as stream:
        settings = DesktopSettings.model_validate({"working_directory": path.parent, **tomllib.load(stream)})
    executable = settings.command[0]
    if not executable:
        raise ValueError("The producer executable must not be empty.")
    return DesktopSettings(
        command=(str((settings.working_directory / Path(executable).expanduser()).resolve()), *settings.command[1:]),
        working_directory=settings.working_directory,
        state_directory=settings.state_directory,
        device=settings.device,
        interval=settings.interval,
        notification_timeout=settings.notification_timeout,
    )
