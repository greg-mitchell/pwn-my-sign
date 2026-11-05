from pathlib import Path

import click
from bleak.exc import BleakError

from greg_mitchell.pwn_my_sign.desktop.runtime import DesktopRuntime


@click.command()
@click.option(
    "--config", type=click.Path(path_type=Path), required=True, help="Explicit private desktop TOML configuration."
)
@click.pass_obj
def desktop(runtime: DesktopRuntime | None, config: Path) -> None:
    """Run the native menu application's workflow child over JSON stdin/stdout."""
    try:
        (runtime or DesktopRuntime()).run(config)
    except (OSError, ValueError, BleakError) as error:
        raise click.ClickException(str(error)) from error
