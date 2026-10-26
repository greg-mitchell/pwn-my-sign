"""Run the foreground polling workflow from a checkout."""

from greg_mitchell.pwn_my_sign.cli.workflow_poll import poll
from greg_mitchell.pwn_my_sign.cli.workflow_runtime import execute

if __name__ == "__main__":
    execute(poll)
