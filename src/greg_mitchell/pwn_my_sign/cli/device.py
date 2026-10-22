import click

from greg_mitchell.pwn_my_sign.cli.scan import scan
from greg_mitchell.pwn_my_sign.cli.send import send


@click.group()
def device() -> None:
    """Discover and send images to a Dory sign."""


device.add_command(scan)
device.add_command(send)
