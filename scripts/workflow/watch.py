"""Run the foreground watch workflow from a checkout."""

from greg_mitchell.pwn_my_sign.cli.workflow_runtime import execute
from greg_mitchell.pwn_my_sign.cli.workflow_watch import watch

if __name__ == "__main__":
    execute(watch)
