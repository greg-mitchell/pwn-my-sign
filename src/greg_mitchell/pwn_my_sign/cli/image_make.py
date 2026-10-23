import tomllib
from pathlib import Path

import click

from greg_mitchell.pwn_my_sign.images.card import CardRenderer, CardSpec
from greg_mitchell.pwn_my_sign.images.layout import CardLayout


@click.command("make")
@click.option("--layout", type=click.Path(path_type=Path), required=True, help="Explicit TOML layout template.")
@click.option(
    "--artwork", type=click.Path(path_type=Path), required=True, help="Static artwork to contain without cropping."
)
@click.option("--font", type=click.Path(path_type=Path), help="TrueType or OpenType font; required for visible text.")
@click.option("--title", default="", help="Optional title text.")
@click.option("--status", default="", help="Optional factual status text.")
@click.option("--caption", default="", help="Optional caption text.")
@click.option("--output", type=click.Path(path_type=Path), help="Write PNG here instead of stdout.")
@click.pass_obj
def make(
    renderer: CardRenderer | None,
    layout: Path,
    artwork: Path,
    font: Path | None,
    title: str,
    status: str,
    caption: str,
    output: Path | None,
) -> None:
    """Build a static 1280x720 grayscale PNG with wrapped text."""
    try:
        settings = CardLayout.model_validate(tomllib.loads(layout.read_text()))
        spec = CardSpec(artwork=artwork, layout=settings, font=font, title=title, status=status, caption=caption)
        data = (renderer or CardRenderer()).render(spec)
        if output is not None:
            output.write_bytes(data)
        else:
            click.echo(data, nl=False)
    except (OSError, ValueError) as error:
        raise click.ClickException(f"Cannot build card: {error}") from error
