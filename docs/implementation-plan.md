# Implementation plan

The goal is a GitHub status sign assembled from small tools and normal Unix workflows.
Physical button wake is accepted. Poll as often as useful, but send only meaningful image changes.

| Milestone | State | Acceptance criterion |
| --- | --- | --- |
| 1. Learn the protocol | Complete | Two Android captures decode, and Mac replay changes TEST B to TEST A. |
| 2. Send custom content | Complete | Newly generated image is visible, upright, and matched to its source photograph. |
| 3. Establish the project | Complete | Packaged sender and diagnostic, public offline tests, developer tooling, and maintained docs. |
| 4. Compose GitHub status | Next | Fetch a validated rollup code; select one of four static images; simulate every state offline. |
| 5. Run the workflow | WIP | Atomic pending images, comparisons, upload snapshots, scheduler recipes, and a clear terminal button prompt. |
| 6. Add convenience | Optional | Template rendering on change, notifications, or a thin menu bar helper using the existing commands. |

## Next implementation slice

1. Add `github-status` with bounded HTTP behavior, strict code extraction, stderr errors, and nonzero failure exits.
2. Add `match-image`: exact token from stdin + a mapping file → selected PNG bytes on stdout. Resolve asset paths
   relative to the configuration file. Emit no partial successful-looking output on lookup or read failure.
3. Add a simple `make-image` utility and four GitHub assets using the 32-pixel content inset. Prebuilt images are the
   initial workflow; on-demand templates are a later enhancement.
4. Add PNG stdin support to `dory-send` and verify the stream contract with offline tests.

## Workflow slice

- Turn the README recipes into runnable examples. Keep `pending` distinct from `last sent`.
- Preserve the latest complete pending image on fetch, selection, render, or send failure.
- Keep one poller and one uploader per workflow/device using scheduler supervision or a Unix lock.
- Prompt after validation and before scanning; allow the user to press the physical button during the wait.
- Retain newer pending work when a status changes during an upload. Define freshness policy before unattended use.
- Document systemd/cron and launchd without embedding a scheduler inside any executable.

## Optional desktop and rendering work

Start with the foreground terminal. Evaluate a notification or SwiftBar plugin before building a native menu bar utility.
Any helper observes local workflow state and invokes the existing uploader; it owns neither GitHub parsing nor image encoding.
Native packaging, permissions, notification authorization, and menu actions remain WIP.

Template rendering must preserve the PNG contract. Trigger it from stable status content rather than poll timestamps.
Keep full-screen backgrounds and the content inset separate from the transport encoder.
