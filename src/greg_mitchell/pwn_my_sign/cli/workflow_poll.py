from pathlib import Path

import click

from greg_mitchell.pwn_my_sign.cli.workflow_runtime import workflow
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations


@click.command()
@click.option("--state", type=click.Path(path_type=Path), required=True, help="Shared state directory for this device.")
@click.option("--image", "image_path", type=click.Path(path_type=Path), help="Static 1280x720 PNG, or - for stdin.")
@click.argument("command", nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def poll(operations: WorkflowOperations | None, state: Path, image_path: Path | None, command: tuple[str, ...]) -> None:
    """Publish a PNG from --image or a producer COMMAND after --, without uploading."""
    if bool(command) == (image_path is not None):
        raise click.UsageError("Provide either --image FILE (or - for stdin) or a producer command after --.")
    try:
        (operations or workflow(state)).poll(PollSettings(image_path=image_path, command=command))
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error
