# Pwn My Sign

Small tools for putting custom content on a Dory e-paper sign from a computer.
I built this to show service health from a cron job, motivated by recent frequent Github outages.

This is an independent, unofficial interoperability project. It is not affiliated with or endorsed by Dory AS.
Use it with signs you own or are authorized to manage. Product names only identify compatibility.

**Working:** GitHub status codes, card building, PNG selection, terminal reminders, and image uploads over Bluetooth LE.

**Planned:** desktop reminders, hands-off uploads.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from this project directory:

```sh
uv sync --locked
```

Python 3.13.6 or later is required. `uv` creates the environment and installs the `mysign` executable.

## Upload a custom image

Prepare an image exactly **1280 × 720 pixels**. The sender converts it to grayscale and 16 levels without resizing or cropping.
The content-safe area appears to be **32 pixels** from each edge; artwork and backgrounds can fill the screen.

### Find the device name or UUID

Close the Dory app on your phone, then discover the sign:

```sh
uv run mysign device scan
```

- Allow Bluetooth access and press the sign's physical button when prompted.
- Results stream immediately as devices advertise
- The scan runs for 30 seconds by default (or `--timeout SECONDS`).
- Only devices advertising the sign's BLE service are shown by default. Use `--all` if that doesn't show your sign.

Each result labels the identifier to copy into the sender's `--device` option:

```text
--device DEVICE-ID  name='advertised-name'  RSSI=-42
```

Use that device ID or the exact advertised name. On macOS, the ID is a UUID local to the scanning computer.

### Send an image

```sh
export MYSIGN_DEVICE='your-sign-name-or-macos-uuid'
uv run mysign device send --device "$MYSIGN_DEVICE" --image image.png
```

The sender prints **“Waiting for the selected sign; press its button now.”** to stderr.
Press the physical button once, then allow roughly two minutes for transfer and refresh.

- A zero exit status means the transfer calls completed. Check the display. The protocol doesn't ack completion.
- Captured headerless payloads can be replayed using `--frame` instead of `--image`.
- Use `--image -` to read one static 1280 × 720 PNG from stdin.
- The `send` command validates PNG data first, before connecting to Bluetooth.

```sh
printf '%s\n' ok | uv run mysign image match --map private/images.toml \
  | uv run mysign device send --device "$MYSIGN_DEVICE" --image -
```

For repeated updates, prepare and snapshot pending images using the [image workflow](#image-workflows).

## Build a test image

```sh
uv run mysign image test-card --output private/mac-test.png
uv run mysign device send --device "$MYSIGN_DEVICE" --image private/mac-test.png
```

Each card says **SENT FROM MAC**, with a fresh ID and timestamp, and includes a grayscale ramp and corner labels.
The corner labels probe the image edges, where the frame can hide some pixels.
The diagnostic currently defaults to a macOS Arial font; `--font` accepts a different TrueType font path.
Use the static card builder below for artwork and reusable layout templates.

## Build a custom card

Supply your own artwork and TrueType or OpenType font. Keep these inputs and finished cards in ignored `private/`:

```sh
uv run mysign image make --layout data/card-layout.toml --artwork private/artwork.png --font private/font.ttf \
  --title 'Service health' --status 'All systems operational' --caption 'Ready for work' \
  --output private/cards/ok.png
```

- Create the output directory first. 
- Omit `--output` to emit PNG bytes on stdout.
- Layouts are defined in TOML templates, and render to 1280 x 720 grayscale.
  - Layout boxes must stay inside the canvas and must not overlap. Text remains aligned left within its box.
- The supplied [split layout](data/card-layout.toml) contains the full artwork on the left and wraps optional title, status,
  and caption on the right. 
  - It uses 56-, 40-, and 32-pixel fonts and centers the complete text stack vertically beside the art.
  - Copy and edit it to choose box positions, sizes, typography, spacing, and vertical alignment (`top`, `center`, or `bottom`).
  - Omit any text options you do not need. Blank text takes no space; `--font` is required only when visible text is supplied.
  - Explicit line breaks are preserved; words or text blocks that do not fit fail rather than being clipped or shrunk.
- The [artwork-only layout](data/artwork-layout.toml) uses the full canvas without a text region.
- The split template places text 32 pixels from the edges, following the observed device's
  [calibration recommendation](docs/display-calibration.md#device-guidance); this is advisory and artwork may reach any edge.
- Transparent artwork is placed on white, photo orientation is honored, and animated artwork is rejected.
- Rendering completes before output is written, so invalid inputs preserve an existing output file.

See [synthetic rendered examples](tests/fixtures/README.md#rendered-card-examples) for previews and regeneration instructions.

## Composable tools

| Command | Input | Output |
| --- | --- | --- | --- |
| `mysign github status` | GitHub's summary endpoint or saved JSON | One status code on stdout |
| `mysign image match --map images.toml` | One code on stdin | Selected PNG bytes on stdout |
| `mysign image make` | Explicit layout/artwork, optional text and font | PNG bytes or named file 
| `mysign device send` | `--image FILE` or `--frame FILE` | Diagnostics on stderr, exit status |
| `mysign device send --image -` | PNG on stdin | Diagnostics on stderr, exit status |
| `mysign image test-card` | Output/font options | Diagnostic PNG and ID metadata |
| `mysign workflow poll` | PNG file/stdin or producer command | Changed `pending.png` in a state directory |
| `mysign workflow upload` | Pending image and device | Transfer and recorded snapshot |
| `mysign workflow watch` | Producer command, device, interval | Foreground reminders and explicit uploads |

See [architecture](docs/architecture.md) for command boundaries, stream contracts, and workflow invariants.

## GitHub workflow

### View and match Github Status

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

The [supplied policy](data/github-actions.toml) maps the overall status + Github Actions status into a
custom code.

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

`mysign image match` implements a general code to image matcher.

Prepare one static 1280 × 720 PNG per code and save a map such as `private/images.toml`:

```toml
[images]
ok = "cards/ok.png"
degraded = "cards/degraded.png"
actions-outage = "cards/actions-outage.png"
widespread-outage = "cards/widespread-outage.png"
```

- Paths resolve relative to the map, so these cards live under `private/cards/`. Absolute paths also work.
- Tokens must match exactly, after stripping an optional LF or CRLF terminator.
- It validates and copies the PNG to stdout.

```sh
uv run mysign github status --policy data/github-actions.toml \
  | uv run mysign image match --map private/images.toml > private/selected.png
```

## Image workflows

The image workflow stitches together an **image producer** with a **poller** which detects changes, and a
**sender** which manages exactly-one writer sending to the sign.

### Poll: prepare the image for sending

The poller detects whether the provided image differs from the current image on the sign, and prepares the new
input for sending if it differs. Some canned options:

```bash
# workflow state, with the image to send
state="${XDG_STATE_HOME:-$HOME/.local/state}/pwn-my-sign/display"

# read an image from file
uv run mysign workflow poll --state "$state" --image private/selected.png

# read an image from stdin
cat private/selected.png | uv run mysign workflow poll --state "$state" --image -

# or invoke an image producer command
uv run mysign workflow poll --state "$state" -- private/produce-image
```

- Image input options: `--image FILE`, `--image -` for stdin, or a producer command after `--`.
  - Arguments are passed literally, without an implicit shell
  - paths resolve from the current working directory.
  - A failed producer's output is discarded, even when it contains a valid PNG.
- The poller publishes a complete `pending.png` by atomic rename only when bytes change.
- Producer, read, or validation failure preserves the previous image and returns failure.
- When making a pipeline in bash, always set `-o pipefail`.

The image artifacts and publication rules are defined in [workflow state](docs/architecture.md#workflow-state).

### Upload the pending image

Once `pending.png` exists, run the uploader:

```bash
uv run mysign workflow upload --state "$state" --device "$MYSIGN_DEVICE"
```

The uploader snapshots pending, skips an already-sent image, and asks the sender to validate that snapshot before its
button prompt and Bluetooth scan. Only successful transfer calls advance `last-sent.png` to the snapshot.
A newer pending image published during the transfer remains available for the next upload.

The snapshot follows the [workflow state contract](docs/architecture.md#workflow-state).

### Watch in a terminal

For a simple foreground alternative to installing a scheduled job, leave this running in a terminal:

```bash
uv run mysign workflow watch --state "$state" --device "$MYSIGN_DEVICE" \
  --interval 300 -- private/produce-image
```

This composes the above tools into a poll loop.

The loop runs the producer immediately and repeats it after each interval. When pending differs from last-sent,
it writes a terminal bell and offers Enter to upload. Press Enter, then press the sign's button when the uploader prompts.

If you leave the prompt alone, it polls again after the interval and reminds you while an update remains unsent.

For example, the GitHub source and image selector compose as one producer:

```sh
uv run mysign workflow watch --state "$state" --device "$MYSIGN_DEVICE" --interval 300 \
  -- bash -o pipefail -c '
    mysign github status --policy data/github-actions.toml |
      mysign image match --map private/images.toml
  '
```

### Locks and recovery

Each operation creates a separate lock directory (`poll.lock`, `upload.lock`, or `watch.lock`) in the selected directory.
An overlapping invocation fails; polling can continue while an upload is in progress. Use one state directory per device.

A crash or forced kill can leave a lock behind. Read its `pid` file, confirm that the process and any transfer child have
stopped, then remove that lock's `pid` file and empty directory. Do not remove a lock belonging to an active process.
An orphaned `.pending.*` or `.last-sent.*` temporary file may be removed after confirming no workflow is using it.

### Schedule polling

The [scheduler recipes](docs/workflow-scheduling.md) cover systemd, cron, and launchd with absolute executable paths.
They schedule only polling; upload remains a foreground action while physical wake is required.
No command installs jobs or starts a scheduler automatically.

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
Workflow behavior is covered by ordinary pytest tests with injected dependencies, without network, Bluetooth,
subprocesses, or real waits. Run those alone with `uv run pytest -k workflow`.
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
