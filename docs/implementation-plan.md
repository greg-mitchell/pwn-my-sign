# Implementation plan

The goal is a GitHub status sign assembled from small tools and normal Unix workflows.
Physical button wake is accepted. Poll as often as useful, but send only meaningful image changes.
User-selected artwork, fonts, captions, maps, and finished cards stay in ignored `private/`.
The repository supplies general tools and workflow documentation, without redistributing those assets.

| Milestone | State | Acceptance criterion |
| --- | --- | --- |
| 1. Learn the protocol | Complete | Two Android captures decode, and Mac replay changes TEST B to TEST A. |
| 2. Send custom content | Complete | Newly generated image is visible, upright, and matched to its source photograph. |
| 3. Establish the project | Complete | Packaged sender and diagnostic, offline tests, developer tooling, and docs. |
| 4. Compose GitHub status | Complete | Validated source codes select private static cards; simulate every state offline. |
| 5. Run the workflow | WIP | Atomic pending images, upload snapshots, scheduler recipes, and terminal prompts. |
| 6. Add convenience | Optional | Dynamic rendering, notifications, or a thin menu bar helper using the existing commands. |

## PR sequence

Each row is one reviewable PR. Pure refactors and feature changes use separate commits.
These units share CLI group registration and dependency metadata, so implement them serially from `main` after review.
Keep later prototypes local rather than creating an unnecessary PR stack.

| Unit | Scope | State | Dependency |
| --- | --- | --- | --- |
| 1. Click domain groups | Install `mysign` with `device` and `image` groups, extract domain operations, preserve leaf behavior. | Complete | Existing sender |
| 2. GitHub source | Add `mysign github status`, validated summary data, explicit service policies, and offline inputs. | Complete | CLI convention |
| 3. Image selection and piping | Add `mysign image match`, then PNG stdin support for the sender in a separate feature commit. | Complete | CLI convention |
| 4. Card building | Add `mysign image make` with explicit artwork/layout inputs and optional text/font. | In review | CLI convention |
| 5. Workflow integration | Runnable shell examples, state comparisons, upload snapshots, locks, and scheduler docs. | Queued | Source, selection, sender |

## Source and selection acceptance

- Fetch GitHub's summary with a positive finite socket timeout, a response-size limit, and no automatic retries.
  A socket timeout is not a hard deadline for the entire command.
- Default output remains GitHub's indicator: `none`, `minor`, `major`, or `critical`.
- An explicit TOML service policy requires priority services, outage count threshold, and all output tokens.
  The [static Actions policy](../data/github-actions.toml) names GitHub Actions and reserves widespread outage
  for reports across multiple visible services;
  a critical rollup alone is insufficient. An Actions-only partial or major outage selects its priority code,
  even with a critical rollup. Other degradation, maintenance, or unresolved incidents select a degraded code.
  Policy files require an explicit mode and fail before fetching when invalid; indicator policies reject service settings.
  No policy file is loaded implicitly, and no service-specific defaults live in Python.
- Reject unknown or incomplete source data; never infer healthy from a failed fetch or malformed response.
- Select an exact token from stdin using a TOML map. Resolve asset paths relative to that map and emit the original PNG bytes.
  Read and validate the complete selected image before writing stdout; lookup or read failure produces no image.
  Require static 1280 x 720 PNGs; reject animation and other dimensions before publishing an image.
- Accept PNG stdin with `mysign device send --image -`; validate before prompting or scanning Bluetooth.
- Simulate Actions-only, unrelated, simultaneous, and widespread failures offline.

## Card acceptance

- Produce deterministic 1280 x 720 grayscale PNGs from user-selected art, fonts, and text.
- Use an explicit TOML layout with nonoverlapping canvas boxes, vertical alignment, and typography settings.
  The supplied split template puts full artwork on the left and optional title, factual status, and caption on the right.
  The split template centers the complete text stack beside the art; the artwork-only template uses the full canvas.
  Recommend a device-specific text inset without restricting artwork to it.
  Contain artwork without cropping and reject text that will not fit; omitted text consumes no space and needs no font.
- Prebuild private static cards. Dynamic rendering from source data is optional later work.
- Public examples use schematic placeholders or instructions for supplying assets, not meme images or font files.

## Workflow acceptance

- Publish complete pending images using a temporary file beside the destination and an atomic rename.
- Preserve the previous pending image on fetch, selection, or render failure.
- Snapshot pending before an upload; advance last-sent only to that snapshot after successful transfer calls.
  A newer pending image survives an older snapshot's successful upload.
- Keep one poller and one uploader per workflow/device using scheduler supervision or a Unix lock.
  Clean locks on ordinary interruption and document stale-lock recovery after a crash.
- Test shell workflows as integration checks, separate from subprocess-free Python unit tests.
- Document systemd/cron and launchd; do not embed a scheduler in any executable or install jobs automatically.
- Prompt after image validation and before scanning. Define stale-data behavior before unattended use.

## Optional desktop and rendering work

Start with the foreground terminal. Evaluate a notification or SwiftBar plugin before building a native menu bar utility.
Any helper observes local workflow state and invokes the existing uploader; it owns neither parsing nor image encoding.
Native packaging, permissions, notification authorization, and menu actions remain WIP.
