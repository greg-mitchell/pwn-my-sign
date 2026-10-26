"""Run the foreground upload workflow from a checkout."""

from greg_mitchell.pwn_my_sign.cli.workflow_runtime import execute
from greg_mitchell.pwn_my_sign.cli.workflow_upload import upload

if __name__ == "__main__":
    execute(upload)
