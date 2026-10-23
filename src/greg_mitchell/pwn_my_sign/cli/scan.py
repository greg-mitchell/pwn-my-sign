import asyncio

import click

from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations


@click.command()
@click.option("--timeout", type=click.FloatRange(min=0, min_open=True), default=30, show_default=True)
@click.pass_obj
def scan(operations: DeviceOperations | None, timeout: float) -> None:
    """List nearby devices without connecting."""
    click.echo("Scanning; press the sign's button now.", err=True)
    for device, advertisement in asyncio.run((operations or DeviceOperations()).scan(timeout)):
        name = advertisement.local_name or device.name or "(unnamed)"
        click.echo(f"{device.address}  {name!r}  RSSI {advertisement.rssi}")
