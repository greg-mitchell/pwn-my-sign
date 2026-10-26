import asyncio
import sys

import click
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations


@click.command()
@click.option("--timeout", type=click.FloatRange(min=0, min_open=True), default=30, show_default=True)
@click.option(
    "--all", "all_devices", is_flag=True, help="Show all nearby BLE devices, regardless of advertised service."
)
@click.pass_obj
def scan(operations: DeviceOperations | None, timeout: float, all_devices: bool) -> None:
    """Stream devices advertising the sign service without connecting."""
    found = False

    def report(device: BLEDevice, advertisement: AdvertisementData) -> None:
        nonlocal found
        found = True
        name = advertisement.local_name or device.name or "(unnamed)"
        click.echo(f"--device {device.address}  name={name!r}  RSSI={advertisement.rssi}")
        sys.stdout.flush()

    scope = "all BLE devices" if all_devices else "sign service only"
    click.echo(f"Scanning for {timeout:g} seconds ({scope}); press the sign's button now.", err=True)
    try:
        asyncio.run((operations or DeviceOperations()).scan(timeout, report, all_devices=all_devices))
    except (BleakError, OSError) as error:
        raise click.ClickException(str(error)) from error
    if found:
        click.echo("Scan complete.", err=True)
    else:
        hint = "" if all_devices else " Try --all to show every nearby BLE device."
        click.echo(f"Scan complete: no matching devices found.{hint}", err=True)
