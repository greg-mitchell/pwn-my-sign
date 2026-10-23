# Synthetic fixtures

## GitHub summary examples

`github/*.json` are hand-written summary documents for offline status simulations.
Only the Actions component ID is a real API identifier; other IDs and service combinations are schematic.
No live API responses, incidents, device identities, or private assets are included.

| File | Team view |
| --- | --- |
| `github/healthy.json` | `ok` |
| `github/actions-only.json` | `actions-outage`, despite a critical rollup and unrelated degradation |
| `github/unrelated-outage.json` | `degraded` |
| `github/simultaneous-outages.json` | `widespread-outage`, including Actions |
| `github/widespread-outages.json` | `widespread-outage`, excluding Actions |
| `github/maintenance.json` | `degraded`, with active scheduled maintenance |

Run a simulation from the project root:

```sh
uv run mysign github status --view team --input tests/fixtures/github/actions-only.json
```

## Image fixtures

`grayscale.frame.gz` and `checkerboard.frame.gz` are independently constructed
460,800-byte wire-format patterns. Both carry asymmetric corner values so pixel
direction can be checked. They contain no app pixels, fonts, artwork, device
identity, HCI metadata, or Android diagnostics.

The payloads omit the separate `!I` command and use deterministic gzip storage.
Regenerate them from the project root:

```sh
uv run python scripts/generate_test_fixtures.py
```

The generator constructs bytes directly without importing the project encoder.
Original captured TEST A / TEST B images remain private. See [the protocol](../../docs/protocol.md)
for the observations that established the format.
