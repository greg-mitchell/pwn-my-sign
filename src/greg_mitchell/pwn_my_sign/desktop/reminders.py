from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from greg_mitchell.pwn_my_sign.workflow.state import replace_file


class Reminder(BaseModel):
    """The last unsent image whose notification submission was accepted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None


class ReminderStore:
    """Keep atomic reminder history separate from authoritative workflow images."""

    def __init__(self, directory: Path, replace: Callable[[Path, Path], None] = replace_file) -> None:
        self._path = directory / "desktop-reminder.json"
        self._replace = replace

    def fingerprint(self) -> str | None:
        """Read accepted notification history; malformed records remain visible errors."""
        try:
            return Reminder.model_validate_json(self._path.read_bytes()).fingerprint
        except FileNotFoundError:
            if self._path.is_symlink():
                raise
            return None

    def remember(self, fingerprint: str | None) -> None:
        """Atomically update changed history without altering pending or last-sent images."""
        if self.fingerprint() == fingerprint:
            return
        data = Reminder(fingerprint=fingerprint).model_dump_json().encode("utf-8")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self._path.parent, prefix=".desktop-reminder.", delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(data)
                stream.close()
                self._replace(temporary, self._path)
            finally:
                temporary.unlink(missing_ok=True)
