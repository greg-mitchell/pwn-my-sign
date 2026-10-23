import math
from http.client import HTTPException
from typing import BinaryIO

import click

from greg_mitchell.pwn_my_sign.github.interpretation import team_status
from greg_mitchell.pwn_my_sign.github.source import GitHubSource


def _finite_timeout(context: click.Context, parameter: click.Parameter, value: float) -> float:
    if not math.isfinite(value):
        raise click.BadParameter("must be positive and finite", ctx=context, param=parameter)
    return value


@click.command()
@click.option("--view", type=click.Choice(("rollup", "team")), default="rollup", show_default=True)
@click.option(
    "--timeout",
    type=click.FloatRange(min=0, min_open=True),
    callback=_finite_timeout,
    default=15,
    show_default=True,
    help="Socket timeout in seconds, not a whole-command deadline.",
)
@click.option(
    "--input", "source", type=click.File("rb"), help="Saved summary JSON file, or - for stdin; skips fetching."
)
@click.pass_obj
def status(operations: GitHubSource | None, view: str, timeout: float, source: BinaryIO | None) -> None:
    """Print one validated status code; errors produce no code."""
    operations = operations or GitHubSource()
    try:
        summary = operations.read(source) if source is not None else operations.fetch(timeout)
    except (OSError, HTTPException, ValueError) as error:
        raise click.ClickException(f"Cannot read GitHub status: {error}") from error
    click.echo(summary.status.indicator if view == "rollup" else team_status(summary))
