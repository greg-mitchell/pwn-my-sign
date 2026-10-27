import signal
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType

import click

from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.producer import CommandProducer
from greg_mitchell.pwn_my_sign.workflow.sender import SnapshotSender
from greg_mitchell.pwn_my_sign.workflow.source import ImageSource
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState

SignalHandler = Callable[[int, FrameType | None], None] | int | None
RegisterSignal = Callable[[int, SignalHandler], SignalHandler]


def report(message: str) -> None:
    """Keep workflow diagnostics and prompts on stderr."""
    click.echo(message, err=True)


def workflow(state: Path) -> WorkflowOperations:
    """Wire production adapters while leaving domain operations injectable."""
    return WorkflowOperations(
        WorkflowState(state),
        ImageSource(CommandProducer(), sys.stdin.buffer),
        SnapshotSender(DeviceOperations()),
        report,
    )


@contextmanager
def interruption_handlers(register: RegisterSignal = signal.signal) -> Generator[None]:
    """Unwind active operations and locks on Ctrl-C or SIGTERM before exiting."""

    def interrupted(number: int, frame: FrameType | None) -> None:
        # A second signal must not interrupt transfer cleanup or lock release.
        register(signal.SIGINT, signal.SIG_IGN)
        register(signal.SIGTERM, signal.SIG_IGN)
        if number == signal.SIGINT:
            raise KeyboardInterrupt
        raise SystemExit(128 + number)

    previous_int = register(signal.SIGINT, interrupted)
    previous_term = register(signal.SIGTERM, interrupted)
    try:
        yield
    finally:
        register(signal.SIGINT, previous_int)
        register(signal.SIGTERM, previous_term)
