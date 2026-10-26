import click

from greg_mitchell.pwn_my_sign.cli.workflow_poll import poll
from greg_mitchell.pwn_my_sign.cli.workflow_runtime import interruption_handlers
from greg_mitchell.pwn_my_sign.cli.workflow_upload import upload
from greg_mitchell.pwn_my_sign.cli.workflow_watch import watch


@click.group()
@click.pass_context
def workflow(context: click.Context) -> None:
    """Prepare, upload, and watch persistent sign updates."""
    context.with_resource(interruption_handlers())


workflow.add_command(poll)
workflow.add_command(upload)
workflow.add_command(watch)
