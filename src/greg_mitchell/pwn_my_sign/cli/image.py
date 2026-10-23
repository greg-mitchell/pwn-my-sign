import click

from greg_mitchell.pwn_my_sign.cli.image_match import match
from greg_mitchell.pwn_my_sign.cli.test_card import test_card


@click.group()
def image() -> None:
    """Build images for the sign."""


image.add_command(test_card)
image.add_command(match)
