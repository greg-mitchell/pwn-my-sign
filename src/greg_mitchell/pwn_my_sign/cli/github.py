import click

from greg_mitchell.pwn_my_sign.cli.github_status import status


@click.group()
def github() -> None:
    """Read GitHub service health."""


github.add_command(status)
