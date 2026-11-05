import os
import signal
from collections.abc import Callable
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired


class ProducerError(ValueError):
    """The image producer exited unsuccessfully; its output must not be published."""


class CommandProducer:
    """Capture a producer's binary stdout while preserving stderr and terminal input."""

    def __init__(
        self,
        spawn: Callable[..., Popen[bytes]] = Popen,
        kill_group: Callable[[int, int], None] = os.killpg,
        cwd: Path | None = None,
    ) -> None:
        self._spawn = spawn
        self._kill_group = kill_group
        self._cwd = cwd

    def run(self, command: tuple[str, ...]) -> bytes:
        """Run explicit arguments without a shell and reap the producer before returning."""
        options = {"cwd": self._cwd} if self._cwd is not None else {}
        with self._spawn(command, stdin=DEVNULL, stdout=PIPE, start_new_session=True, **options) as process:
            try:
                output, _ = process.communicate()
            except BaseException:
                self._stop(process)
                raise
            if process.returncode != 0:
                raise ProducerError(f"Producer exited with status {process.returncode}.")
            return output

    def _stop(self, process: Popen[bytes]) -> None:
        # A shell producer may own a pipeline; stop its entire group before unlocking.
        self._signal(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=5)
        except TimeoutExpired:
            self._signal(process.pid, signal.SIGKILL)
            process.communicate()

    def _signal(self, group: int, number: int) -> None:
        try:
            self._kill_group(group, number)
        except ProcessLookupError:
            pass
