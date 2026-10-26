from http.client import HTTPException
from pathlib import Path

import click

from greg_mitchell.pwn_my_sign.cli.workflow_runtime import workflow
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations


@click.command()
@click.option("--state", type=click.Path(path_type=Path), required=True, help="Shared state directory for this device.")
@click.option("--map", "map_path", type=click.Path(path_type=Path), required=True)
@click.option("--policy", "policy_path", type=click.Path(path_type=Path))
@click.pass_obj
def poll(operations: WorkflowOperations | None, state: Path, map_path: Path, policy_path: Path | None) -> None:
    """Publish a changed desired image without uploading it."""
    try:
        (operations or workflow(state)).poll(PollSettings(map_path=map_path, policy_path=policy_path))
    except (OSError, ValueError, HTTPException) as error:
        raise click.ClickException(str(error)) from error
