import click

from greg_mitchell.pwn_my_sign.cli.device import device
from greg_mitchell.pwn_my_sign.cli.image import image


@click.group(name="mysign")
def main() -> None:
    """Build images and send them to a compatible sign."""


main.add_command(device)
main.add_command(image)
