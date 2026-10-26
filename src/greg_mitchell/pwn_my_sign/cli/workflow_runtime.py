import signal
from collections.abc import Callable
from pathlib import Path
from types import FrameType

import click

from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.github.source import GitHubSource
from greg_mitchell.pwn_my_sign.images.selection import ImageSelector
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.sender import SnapshotSender
from greg_mitchell.pwn_my_sign.workflow.source import StatusImageSource
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
        StatusImageSource(GitHubSource(), ImageSelector()),
        SnapshotSender(DeviceOperations()),
        report,
    )


def execute(command: click.Command, register: RegisterSignal = signal.signal) -> None:
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
        command()
    finally:
        register(signal.SIGINT, previous_int)
        register(signal.SIGTERM, previous_term)
