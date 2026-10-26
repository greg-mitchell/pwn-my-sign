import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from greg_mitchell.pwn_my_sign.workflow.models import WorkflowKind


def replace_file(source: Path, destination: Path) -> None:
    """Publish a complete file by atomic rename on the same filesystem."""
    source.replace(destination)


class WorkflowState:
    """Own workflow images and locks in one explicitly selected directory."""

    def __init__(self, directory: Path, replace: Callable[[Path, Path], None] = replace_file) -> None:
        self.directory = directory
        self._replace = replace

    @contextmanager
    def lock(self, kind: WorkflowKind) -> Generator[None]:
        """Reject overlap and retain the lock until the operation has unwound."""
        self.directory.mkdir(parents=True, exist_ok=True)
        lock = self.directory / f"{kind}.lock"
        try:
            lock.mkdir()
        except FileExistsError as error:
            raise OSError(f"Cannot acquire {lock}; another workflow may be running.") from error
        try:
            (lock / "pid").write_text(f"{os.getpid()}\n")
            yield
        finally:
            (lock / "pid").unlink(missing_ok=True)
            lock.rmdir()

    def pending(self) -> bytes:
        """Read one complete snapshot of the desired image."""
        return (self.directory / "pending.png").read_bytes()

    def is_sent(self, image: bytes) -> bool:
        """Compare with the last completed transfer; read errors propagate."""
        return self._read_optional(self.directory / "last-sent.png") == image

    def publish(self, image: bytes) -> bool:
        """Publish changed pending bytes, preserving unchanged files."""
        destination = self.directory / "pending.png"
        if self._read_optional(destination) == image:
            return False
        self._write(destination, image)
        return True

    def record_sent(self, image: bytes) -> None:
        """Record exactly the snapshot whose transfer completed."""
        self._write(self.directory / "last-sent.png", image)

    def _read_optional(self, path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            if path.is_symlink():
                raise
            return None

    def _write(self, destination: Path, image: bytes) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.directory, prefix=f".{destination.stem}.", delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(image)
                stream.close()
                self._replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
