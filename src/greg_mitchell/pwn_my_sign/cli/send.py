import asyncio
import sys
from pathlib import Path

import click

from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations, ImageInputError


def _report(message: str) -> None:
    click.echo(message, err=True)


@click.command()
@click.option("--device", required=True, help="Exact advertised name or Mac BLE UUID.")
@click.option("--timeout", type=click.FloatRange(min=0, min_open=True), default=60, show_default=True)
@click.option("--packet-delay", type=click.FloatRange(min=0), default=0.05, show_default=True)
@click.option("--image", type=click.Path(path_type=Path), help="1280x720 image file, or - for static PNG stdin.")
@click.option("--frame", type=click.Path(path_type=Path), help="Headerless captured image payload.")
@click.pass_obj
def send(
    operations: DeviceOperations | None,
    device: str,
    timeout: float,
    packet_delay: float,
    image: Path | None,
    frame: Path | None,
) -> None:
    """Send one image after the sign is woken."""
    if (image is None) == (frame is None):
        raise click.UsageError("Provide exactly one of --image or --frame.")
    try:
        asyncio.run(
            (operations or DeviceOperations()).upload(
                device,
                image_path=None if image == Path("-") else image,
                image_stream=sys.stdin.buffer if image == Path("-") else None,
                frame_path=frame,
                timeout=timeout,
                packet_delay=packet_delay,
                report=_report,
            )
        )
    except ImageInputError as error:
        raise click.ClickException(f"Cannot read PNG stdin: {error}") from error
