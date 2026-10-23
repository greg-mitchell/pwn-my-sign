import sys
from pathlib import Path

import click

from greg_mitchell.pwn_my_sign.images.selection import ImageSelector


@click.command("match")
@click.option("--map", "map_path", type=click.Path(path_type=Path), required=True, help="Explicit TOML image map.")
@click.pass_obj
def match(operations: ImageSelector | None, map_path: Path) -> None:
    """Select a static 1280x720 PNG for one exact code on stdin."""
    try:
        data = (operations or ImageSelector()).select(map_path, sys.stdin.buffer)
    except (OSError, ValueError) as error:
        raise click.ClickException(f"Cannot select image: {error}") from error
    click.echo(data, nl=False)
