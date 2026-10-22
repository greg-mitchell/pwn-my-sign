# Synthetic image fixtures

`grayscale.frame.gz` and `checkerboard.frame.gz` are independently constructed
460,800-byte wire-format patterns. Both carry asymmetric corner values so pixel
direction can be checked. They contain no app pixels, fonts, artwork, device
identity, HCI metadata, or Android diagnostics.

The payloads omit the separate `!I` command and use deterministic gzip storage.
Regenerate them from the project root:

```sh
uv run --no-sync python scripts/generate_test_fixtures.py
```

The generator constructs bytes directly without importing the project encoder.
Original captured TEST A / TEST B images remain private. See [the protocol](../../docs/protocol.md)
for the observations that established the format.
