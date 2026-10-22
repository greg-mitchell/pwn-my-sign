# Pwn My Sign

Small tools for putting custom content on a Dory e-paper sign from a computer.
I built this to show service health from a cron job, motivated by recent frequent Github outages.

This is an independent, unofficial interoperability project. It is not affiliated with or endorsed by Dory AS.
Use it with signs you own or are authorized to manage. Product names identify compatibility.

**Working:** discovery and full-screen image uploads from macOS over Bluetooth LE.
**WIP:** GitHub status fetching, image selection, change detection workflows, and desktop prompts.
The sign currently needs a physical button press for each upload.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from this project directory:

```sh
uv sync --locked
```

Python 3.13.6 or later is required. `uv` creates the environment and installs the `mysign` executable.
Run `uv run mysign --help` to discover its domain groups and commands.
This replaces the earlier `dory`, `dory-send`, and `dory-test-card` executables; no compatibility aliases are installed.
The project follows the namespace package and development tooling used in
[greg-mitchell/portfolio](https://github.com/greg-mitchell/portfolio).

## Upload a custom image

Prepare an image exactly **1280 × 720 pixels**. The sender converts it to grayscale and 16 levels without resizing or cropping.
Keep important text and graphics at least **32 pixels** from each edge; backgrounds can fill the screen.

Close the Dory app on your phone, then discover the sign:

```sh
uv run mysign device scan
```

Allow Bluetooth access and press the sign's physical button when prompted.
Use its advertised name or the UUID printed by the scan. On macOS, that UUID is local to the scanning computer.

```sh
export MYSIGN_DEVICE='your-sign-name-or-macos-uuid'
uv run mysign device send --device "$MYSIGN_DEVICE" --image image.png
```

The sender prints **“Waiting for the selected sign; press its button now.”** to stderr.
Press the physical button once, then allow roughly two minutes for transfer and refresh.
The scan wait defaults to 60 seconds and can be changed with `--timeout`.

A zero exit status means the transfer calls completed. Check the display: the captured protocol provides no observed
application acknowledgement that the intended image is physically visible.

Captured headerless payloads can be replayed using `--frame` instead of `--image`.

## Build a recognizable test image

```sh
uv run mysign image test-card --output private/mac-test.png
uv run mysign device send --device "$MYSIGN_DEVICE" --image private/mac-test.png
```

Each card says **SENT FROM MAC**, with a fresh ID and timestamp, and includes a grayscale ramp and corner labels.
The corner labels probe the image edges, where the frame can hide some pixels.
The diagnostic currently defaults to a macOS Arial font; `--font` accepts a different TrueType font path.
General image building and rendering from templates are WIP.

## Composable tools

These are the intended interfaces. Only the rows marked **working** are installed today.

| Command | Input | Output | Status |
| --- | --- | --- | --- |
| `mysign github status` | GitHub's status endpoint | One status code on stdout | WIP |
| `mysign image match --map images.toml` | One code on stdin | Selected PNG bytes on stdout | WIP |
| `mysign image make` | Text and appearance options | PNG | WIP |
| `mysign device send` | `--image FILE` or `--frame FILE` | Diagnostics on stderr, exit status | Working |
| `mysign device send --image -` | PNG on stdin | Diagnostics on stderr, exit status | WIP |
| `mysign image test-card` | Output/font options | Diagnostic PNG and ID metadata | Working |

Data belongs on stdout; diagnostics belong on stderr. Each leaf command runs once and exits.
Domain groups organize help; commands remain small operations that compose through Unix pipes.
Source adapters own domain-specific interpretation. Matchers own configuration. The sender owns Bluetooth and encoding.
Polling, comparisons, files, locks, and scheduling belong in documented shell composition.

## GitHub workflow

### Inspect the source now

[GitHub Status](https://www.githubstatus.com/api) exposes
`https://www.githubstatus.com/api/v2/status.json`. Its overall indicator is `none`, `minor`, `major`, or `critical`.
This is GitHub's rollup; unresolved incidents can exist while the rollup is `none`.
The summary endpoint is available later for component and incident details.

Run this Bash snippet to fetch and validate a code:

```bash
set -euo pipefail
# Fail on HTTP errors, keep errors visible, and bound the request to 15 seconds.
curl --fail --silent --show-error --max-time 15 \
  https://www.githubstatus.com/api/v2/status.json |
  jq -er '.status.indicator | select(. == "none" or . == "minor" or . == "major" or . == "critical")'
```

`mysign github status` will package that domain-specific operation. Fetch failures and unknown codes must fail rather than
silently selecting the healthy image.

### Prepare only changed images — WIP

First build one static PNG per code. A mapping file will select an asset without rendering it on every poll.
The following describes the target workflow; `mysign github status` and `mysign image match` are not implemented yet.

```bash
set -euo pipefail
state="${XDG_STATE_HOME:-$HOME/.local/state}/pwn-my-sign/github"
mkdir -p "$state"
next="$(mktemp "$state/.pending.XXXXXX")"
trap 'rm -f "$next"' EXIT

uv run mysign github status | uv run mysign image match --map images.toml > "$next"
if ! cmp -s "$next" "$state/pending.png"; then
  mv "$next" "$state/pending.png"
fi
```

The temporary file sits beside the destination so the rename publishes a complete image atomically.
On failure, the previous pending image survives. Prebuilt assets are deterministic; polling does not add a new timestamp.

### Upload the pending image

Once `pending.png` exists, this Bash workflow is usable with the current sender.
Run from the project directory with `MYSIGN_DEVICE` set. Run at most one uploader for a device at a time.

```bash
set -euo pipefail
state="${XDG_STATE_HOME:-$HOME/.local/state}/pwn-my-sign/github"
snapshot="$(mktemp "$state/.upload.XXXXXX")"
trap 'rm -f "$snapshot"' EXIT
cp "$state/pending.png" "$snapshot"

if cmp -s "$snapshot" "$state/last-sent.png"; then
  printf '%s\n' 'The latest desired image has already been sent.' >&2
  exit 0
fi

uv run mysign device send --device "$MYSIGN_DEVICE" --image "$snapshot"
mv "$snapshot" "$state/last-sent.png"
```

The prompt tells the person at the computer when to press the sign's button. A failed transfer leaves `last-sent.png`
unchanged. If polling publishes a new image during upload, the snapshot still records exactly what was sent;
the newer pending image remains available for the next upload.

### Schedule polling — WIP

Documented scheduler recipes will invoke the one-shot poll workflow with absolute paths and explicit environment variables:

- Linux: a systemd oneshot service and timer, or cron with an overlap lock.
- macOS: a user launchd job; cron is another Unix option.

Scheduling must not start overlapping pollers. Upload remains a separate foreground action while physical wake is required.
Installing jobs, starting background processes, and posting desktop notifications are future opt-in setup steps.

### Desktop reminders and templates — WIP

The initial user interface is the sender's terminal prompt and progress output.
A notification or menu bar helper can later show **update pending**, then invoke the same upload workflow.
macOS menu bar utilities can run without a main window; a SwiftBar plugin can also host a script-driven menu.
See [architecture](docs/architecture.md#button-prompts-and-desktop-integration) for the options and workflow states.

Rendering from a template on a status change is a later enhancement. It should produce the same PNG interface and preserve
the code → image → sender boundary.

## Development

The source lives in `src/greg_mitchell/pwn_my_sign/`, with matching tests under `tests/greg_mitchell/pwn_my_sign/`.
Each Click group and command has a focused module in `src/greg_mitchell/pwn_my_sign/cli/`.
The single `mysign` executable is declared in `[project.scripts]` in `pyproject.toml`.
Device operations live in `device/`; diagnostic image construction lives in `images/`.
Run commands from the project root; `uv run` syncs the environment implicitly:

```sh
uv run poe format
uv run poe check-all
```

Poe defines `lint`, `format`, `typecheck` (`ty`), `test` (pytest), `check-all`, and `fix-all` in `pyproject.toml`.
Pre-commit uses the same Ruff, type, and test checks. After initializing a Git checkout, hooks can be installed with
`uv run pre-commit install`.

Unit tests use injected dependencies and mocks; they never scan Bluetooth, fetch the network, or send an image.
The public compressed fixtures are independently generated grayscale and checkerboard patterns.
Android bug reports, raw Bluetooth logs, device identities, photos, and generated evidence stay under ignored `private/`.

Investigation scripts are retained in `scripts/investigation/`, outside production lint/type-check scope.
To rerun the photo analysis, install the optional investigation dependencies:

```sh
uv sync --locked --extra investigation
uv run python scripts/investigation/analyze_photo.py private/photos/20261022T130213_mac_custom_test.jpg
```

## Documentation

- [Implementation plan](docs/implementation-plan.md): milestones and current WIP.
- [Protocol](docs/protocol.md): observed BLE behavior and confirmed wire format.
- [Architecture](docs/architecture.md): tool contracts, workflow state, and optional desktop integration.
- [Display calibration](docs/display-calibration.md): photograph analysis and the 32-pixel content inset.
- [Provenance and licensing](docs/provenance.md): independent implementation, synthetic fixtures, and dependency notices.
- [Agent instructions](AGENTS.md), [Python style](docs/python-style.md), and [test style](docs/test-style.md).

## License

Project code and documentation are available under the [MIT License](LICENSE.txt), including its warranty disclaimer.
Third-party dependencies retain their own licenses. No Dory app, firmware, bundled fonts, or app-rendered assets are
distributed in this repository. See [provenance](docs/provenance.md).
