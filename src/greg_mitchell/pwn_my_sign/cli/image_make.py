from pathlib import Path

import click

from greg_mitchell.pwn_my_sign.images.card import CardRenderer, CardSpec


@click.command("make")
@click.option("--artwork", type=click.Path(path_type=Path), required=True, help="Static artwork for the left column.")
@click.option("--font", type=click.Path(path_type=Path), required=True, help="Explicit TrueType or OpenType font.")
@click.option("--title", required=True, help="Title text, rendered at 56 pixels.")
@click.option("--status", required=True, help="Factual status text, rendered at 40 pixels.")
@click.option("--caption", required=True, help="Caption text, rendered at 32 pixels.")
@click.option("--output", type=click.Path(path_type=Path), help="Write PNG here instead of stdout.")
@click.pass_obj
def make(
    renderer: CardRenderer | None,
    artwork: Path,
    font: Path,
    title: str,
    status: str,
    caption: str,
    output: Path | None,
) -> None:
    """Build a static 1280x720 grayscale PNG with wrapped text."""
    try:
        spec = CardSpec(artwork=artwork, font=font, title=title, status=status, caption=caption)
        data = (renderer or CardRenderer()).render(spec)
        if output is not None:
            output.write_bytes(data)
        else:
            click.echo(data, nl=False)
    except (OSError, ValueError) as error:
        raise click.ClickException(f"Cannot build card: {error}") from error
