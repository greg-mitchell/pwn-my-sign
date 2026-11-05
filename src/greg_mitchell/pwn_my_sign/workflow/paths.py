import os
from collections.abc import Callable, Mapping
from pathlib import Path


def default_state_directory(environment: Mapping[str, str] | None = None, home: Callable[[], Path] = Path.home) -> Path:
    """Use absolute XDG state storage, falling back to the user's local state directory."""
    value = (os.environ if environment is None else environment).get("XDG_STATE_HOME", "")
    base = Path(value)
    if not base.is_absolute():
        base = home() / ".local/state"
    return base / "pwn-my-sign/display"
