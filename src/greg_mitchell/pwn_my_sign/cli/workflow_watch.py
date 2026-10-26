import sys
import time
from http.client import HTTPException
from pathlib import Path

import click
from bleak.exc import BleakError

from greg_mitchell.pwn_my_sign.cli.workflow_runtime import report, workflow
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadSettings, WatchSettings
from greg_mitchell.pwn_my_sign.workflow.terminal import TerminalInput
from greg_mitchell.pwn_my_sign.workflow.watch import Watcher


@click.command()
@click.option("--state", type=click.Path(path_type=Path), required=True, help="Shared state directory for this device.")
@click.option("--map", "map_path", type=click.Path(path_type=Path), required=True)
@click.option("--policy", "policy_path", type=click.Path(path_type=Path))
@click.option("--device", required=True, help="Exact advertised name or device ID.")
@click.option("--interval", type=click.IntRange(min=1), default=300, show_default=True)
@click.pass_obj
def watch(
    watcher: Watcher | None, state: Path, map_path: Path, policy_path: Path | None, device: str, interval: int
) -> None:
    """Poll in the foreground and offer Enter to upload changed images."""
    try:
        settings = WatchSettings(
            poll=PollSettings(map_path=map_path, policy_path=policy_path),
            upload=UploadSettings(device=device),
            interval=interval,
        )
        (watcher or Watcher(workflow(state), TerminalInput(sys.stdin), time.sleep, report)).run(settings)
    except (OSError, ValueError, HTTPException, BleakError) as error:
        raise click.ClickException(str(error)) from error
