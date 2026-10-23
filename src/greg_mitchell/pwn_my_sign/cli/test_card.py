import datetime
import json
import uuid
from collections.abc import Callable
from pathlib import Path

import click
from PIL import Image

from greg_mitchell.pwn_my_sign.images.test_card import make_test_card


@click.command()
@click.option("--output", type=click.Path(path_type=Path), default=Path("private/mac-test.png"), show_default=True)
@click.option(
    "--font",
    type=click.Path(path_type=Path),
    default=Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    show_default=True,
)
@click.pass_obj
def test_card(builder: Callable[[str, str, Path], Image.Image] | None, output: Path, font: Path) -> None:
    """Create a visibly distinct Dory upload test."""
    test_id = f"MAC-{uuid.uuid4().hex[:6].upper()}"
    timestamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    image = (builder or make_test_card)(test_id, timestamp, font)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    output.with_suffix(".json").write_text(json.dumps({"test_id": test_id, "created_at": timestamp}, indent=2) + "\n")
    click.echo(f"Created {output}: SENT FROM MAC / {test_id}")
