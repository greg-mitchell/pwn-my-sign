from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from time import monotonic, sleep

from greg_mitchell.pwn_my_sign.workflow.models import WorkflowKind
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState


class DesktopInstance:
    """Wait briefly for an old controller to unwind without deleting its lock."""

    def __init__(
        self,
        state: WorkflowState,
        clock: Callable[[], float] = monotonic,
        pause: Callable[[float], None] = sleep,
        timeout: float = 3,
    ) -> None:
        self._state = state
        self._clock = clock
        self._pause = pause
        self._timeout = timeout

    @contextmanager
    def hold(self) -> Generator[None]:
        """Retry acquisition only; errors from running work are never replayed."""
        deadline = self._clock() + self._timeout
        with ExitStack() as stack:
            while True:
                try:
                    stack.enter_context(self._state.lock(WorkflowKind.DESKTOP))
                    break
                except OSError:
                    remaining = deadline - self._clock()
                    if remaining <= 0 or not (self._state.directory / "desktop.lock").is_dir():
                        raise
                    self._pause(min(0.1, remaining))
            yield
