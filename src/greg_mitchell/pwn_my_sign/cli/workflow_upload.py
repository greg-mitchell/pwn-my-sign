from pathlib import Path

import click
from bleak.exc import BleakError

from greg_mitchell.pwn_my_sign.cli.workflow_runtime import workflow
from greg_mitchell.pwn_my_sign.workflow.models import UploadSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.paths import default_state_directory


@click.command()
@click.option(
    "--state",
    type=click.Path(path_type=Path),
    default=default_state_directory,
    show_default="$XDG_STATE_HOME/pwn-my-sign/display or ~/.local/state/pwn-my-sign/display",
    help="Shared state directory for this device.",
)
@click.option("--device", required=True, help="Exact advertised name or device ID.")
@click.pass_obj
def upload(operations: WorkflowOperations | None, state: Path, device: str) -> None:
    """Upload a pending snapshot unless it has already been sent."""
    try:
        (operations or workflow(state.expanduser())).upload(UploadSettings(device=device))
    except (OSError, ValueError, BleakError) as error:
        raise click.ClickException(str(error)) from error
