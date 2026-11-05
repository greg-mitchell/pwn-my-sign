from pathlib import Path
from subprocess import CalledProcessError

import click

from greg_mitchell.pwn_my_sign.desktop.build import DesktopAppBuilder
from greg_mitchell.pwn_my_sign.desktop.config import load_settings


@click.command(name='desktop-build')
@click.option('--config', type=click.Path(path_type=Path), required=True, help='Explicit private desktop TOML file.')
@click.option(
    '--output', type=click.Path(path_type=Path), required=True, help='Local output application ending in .app.'
)
@click.option('--checkout', type=click.Path(path_type=Path), default='.', help='Source checkout with its synced .venv.')
@click.pass_obj
def desktop_build(builder: DesktopAppBuilder | None, config: Path, output: Path, checkout: Path) -> None:
    """Build and locally sign the optional macOS menu bar application."""
    try:
        load_settings(config)
        application = (builder or DesktopAppBuilder()).build(checkout, config, output)
    except (OSError, ValueError, CalledProcessError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f'Built {application}. Open it to start the desktop workflow.', err=True)
