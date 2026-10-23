# Pwn My Sign

Small tools for putting custom content on a Dory e-paper sign from a computer.
I built this to show service health from a cron job, motivated by recent frequent Github outages.

This is an independent, unofficial interoperability project. It is not affiliated with or endorsed by Dory AS.
Use it with signs you own or are authorized to manage. Product names identify compatibility.

**Working:** GitHub status codes, card building, PNG selection, discovery, and image uploads from macOS over Bluetooth LE.
**WIP:** change detection workflows and desktop prompts.
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
For the observed sign, keep text at least **32 pixels** from each edge; artwork and backgrounds can fill the screen.

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
Use `--image -` to read one static 1280 × 720 PNG from stdin. The sender reads and validates it completely before
printing the button prompt or scanning Bluetooth; malformed input produces an error on stderr and no transfer.

```sh
printf '%s\n' ok | uv run mysign image match --map private/images.toml \
  | uv run mysign device send --device "$MYSIGN_DEVICE" --image -
```

For repeated updates, prepare and snapshot pending images using the [GitHub workflow](#github-workflow).

## Build a recognizable test image

```sh
uv run mysign image test-card --output private/mac-test.png
uv run mysign device send --device "$MYSIGN_DEVICE" --image private/mac-test.png
```

Each card says **SENT FROM MAC**, with a fresh ID and timestamp, and includes a grayscale ramp and corner labels.
The corner labels probe the image edges, where the frame can hide some pixels.
The diagnostic currently defaults to a macOS Arial font; `--font` accepts a different TrueType font path.
Use the static card builder below for artwork and reusable layout templates.

## Build a static display card

Supply your own artwork and TrueType or OpenType font. Keep these inputs and finished cards in ignored `private/`:

```sh
uv run mysign image make --layout data/card-layout.toml --artwork private/artwork.png --font private/font.ttf \
  --title 'Service health' --status 'All systems operational' --caption 'Ready for work' \
  --output private/cards/ok.png
```

Create the output directory first. Omit `--output` to emit PNG bytes on stdout.
The deterministic 1280 × 720 grayscale output uses an explicitly selected TOML layout template.
The supplied [split layout](data/card-layout.toml) contains the full artwork on the left and wraps optional title, status,
and caption on the right. It uses 56-, 40-, and 32-pixel fonts and centers the complete text stack vertically beside the art.
Copy and edit it to choose box positions, sizes, typography, spacing, and vertical alignment (`top`, `center`, or `bottom`).
Layout boxes must stay inside the canvas and must not overlap. Text remains aligned left within its box.
The [artwork-only layout](data/artwork-layout.toml) uses the full canvas without a text region.
The split template places text 32 pixels from the edges, following the observed device's
[calibration recommendation](docs/display-calibration.md#device-guidance); this is advisory and artwork may reach any edge.
Omit any text options you do not need. Blank text takes no space; `--font` is required only when visible text is supplied.
Explicit line breaks are preserved; words or text blocks that do not fit fail rather than being clipped or shrunk.
Pillow handles pixel-width wrapping and multiline baselines; trailing invisible whitespace can be discarded.
Transparent artwork is placed on white, photo orientation is honored, and animated artwork is rejected.
Rendering completes before output is written, so invalid inputs preserve an existing output file.
See [synthetic rendered examples](tests/fixtures/README.md#rendered-card-examples) for previews and regeneration instructions.

## Composable tools

These are the intended interfaces. Only the rows marked **working** are installed today.

| Command | Input | Output | Status |
| --- | --- | --- | --- |
| `mysign github status` | GitHub's summary endpoint or saved JSON | One status code on stdout | Working |
| `mysign image match --map images.toml` | One code on stdin | Selected PNG bytes on stdout | Working |
| `mysign image make` | Explicit layout/artwork, optional text and font | PNG bytes or named file | Working |
| `mysign device send` | `--image FILE` or `--frame FILE` | Diagnostics on stderr, exit status | Working |
| `mysign device send --image -` | PNG on stdin | Diagnostics on stderr, exit status | Working |
| `mysign image test-card` | Output/font options | Diagnostic PNG and ID metadata | Working |

See [architecture](docs/architecture.md) for command boundaries, stream contracts, and workflow invariants.

## GitHub workflow

### Inspect the source now

```sh
uv run mysign github status
uv run mysign github status --policy data/github-actions.toml
uv run mysign github status --input tests/fixtures/github/healthy.json
```

The default prints [GitHub's indicator](https://www.githubstatus.com/api):

| Code | Meaning |
| --- | --- |
| `none` | No reported impact. |
| `minor` | Minor impact. |
| `major` | Major impact. |
| `critical` | Critical impact. |

The [supplied policy](data/github-actions.toml) prioritizes GitHub Actions and uses these outputs.
Service policies explicitly set their mode, priority services, outage threshold, and every output code:

| Code | Meaning |
| --- | --- |
| `ok` | Services are healthy, with no unresolved incident or active maintenance. |
| `degraded` | Some impairment, incident, or maintenance without an outage below. |
| `actions-outage` | Actions is the only service reporting an outage. |
| `widespread-outage` | Multiple visible services report outages. |

See the [policy settings](src/greg_mitchell/pwn_my_sign/github/policy.py),
[classification policy](src/greg_mitchell/pwn_my_sign/github/interpretation.py), and
[offline examples](tests/fixtures/README.md#github-summary-examples) for details.

### Select a private static card

Prepare one static 1280 × 720 PNG per code and save a map such as `private/images.toml`:

```toml
[images]
ok = "cards/ok.png"
degraded = "cards/degraded.png"
actions-outage = "cards/actions-outage.png"
widespread-outage = "cards/widespread-outage.png"
```

Paths resolve relative to the map, so these cards live under `private/cards/`. Absolute paths also work.
Tokens match exactly, including case; stdin accepts one token with an optional LF or CRLF terminator.
The selector validates the selected PNG completely before emitting its original bytes. Animated PNGs, wrong dimensions,
unknown codes, invalid maps, and unreadable or damaged images fail with no image output. Unselected assets are not read.

```sh
uv run mysign github status --policy data/github-actions.toml \
  | uv run mysign image match --map private/images.toml > private/selected.png
```

### Prepare only changed images — WIP

The composition below prepares a complete temporary image before replacing pending. Scheduler and lock integration
remain WIP.

```bash
set -euo pipefail
state="${XDG_STATE_HOME:-$HOME/.local/state}/pwn-my-sign/github"
mkdir -p "$state"
next="$(mktemp "$state/.pending.XXXXXX")"
trap 'rm -f "$next"' EXIT

uv run mysign github status --policy data/github-actions.toml \
  | uv run mysign image match --map private/images.toml > "$next"
if ! cmp -s "$next" "$state/pending.png"; then
  mv "$next" "$state/pending.png"
fi
```

The image artifacts and publication rules are defined in [workflow state](docs/architecture.md#workflow-state).

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

The snapshot follows the [workflow state contract](docs/architecture.md#workflow-state).

### Schedule polling — WIP

Documented scheduler recipes will invoke the one-shot poll workflow with absolute paths and explicit environment variables:

- Linux: a systemd oneshot service and timer, or cron with an overlap lock.
- macOS: a user launchd job; cron is another Unix option.

Scheduling must not start overlapping pollers. Upload remains a separate foreground action while physical wake is required.
Installing jobs, starting background processes, and posting desktop notifications are future opt-in setup steps.

### Desktop reminders — WIP

Desktop helpers and optional dynamic rendering are tracked in the
[implementation plan](docs/implementation-plan.md#optional-desktop-and-rendering-work). Their design boundaries are defined
in [architecture](docs/architecture.md#button-prompts-and-desktop-integration).

## Development

Run commands from the project root; `uv run` syncs the environment implicitly:

```sh
uv run poe format
uv run poe check-all
```

Available tasks, entrypoints, and dependencies are defined in [pyproject.toml](pyproject.toml).
See [the contributor guidelines](AGENTS.md) for required checks, coding conventions, and test rules.
Install commit hooks with `uv run pre-commit install`.

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
