import sys
import time
from pathlib import Path

import click
from bleak.exc import BleakError

from greg_mitchell.pwn_my_sign.cli.workflow_runtime import report, workflow
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadSettings, WatchSettings
from greg_mitchell.pwn_my_sign.workflow.terminal import TerminalInput
from greg_mitchell.pwn_my_sign.workflow.watch import Watcher


@click.command()
@click.option("--state", type=click.Path(path_type=Path), required=True, help="Shared state directory for this device.")
@click.option("--device", required=True, help="Exact advertised name or device ID.")
@click.option("--interval", type=click.IntRange(min=1), default=300, show_default=True)
@click.argument("command", nargs=-1, required=True, type=click.UNPROCESSED)
@click.pass_obj
def watch(watcher: Watcher | None, state: Path, device: str, interval: int, command: tuple[str, ...]) -> None:
    """Repeat a producer COMMAND after --; offer Enter to upload its PNG output."""
    try:
        settings = WatchSettings(
            poll=PollSettings(command=command),
            upload=UploadSettings(device=device),
            interval=interval,
        )
        (watcher or Watcher(workflow(state), TerminalInput(sys.stdin), time.sleep, report)).run(settings)
    except (OSError, ValueError, BleakError) as error:
        raise click.ClickException(str(error)) from error
