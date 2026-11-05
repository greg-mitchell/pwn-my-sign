# Native desktop process protocol

The native menu bar app starts exactly one checkout executable:

```text
/absolute/checkout/.venv/bin/mysign workflow desktop --config /absolute/private/desktop.toml
```

The Python child owns polling, workflow image state, reminder history, and explicit uploads. The native parent owns
menus, notification permission/submission, Test Notification, bounded diagnostic logs, and child lifetime.
This interface does not alter image encoding or the BLE wire protocol.

## Framing

Both directions use UTF-8 JSON records terminated by LF, with a maximum of **16 KiB including the LF** per record.
Every record carries `version: 1` and `type`. Python's frozen Pydantic models own serialization. Diagnostics belong
only on stderr. Nullable output fields are emitted as `null`.

One reader thread uses buffered binary `readline` and feeds a bounded 64-record queue. The main thread validates
records with Pydantic and waits through `Queue.get(timeout=...)`. Invalid and oversized input is diagnosed and
discarded without becoming an action. Oversized lines are drained in bounded pieces; partial records at EOF are
discarded. Positive receive deadlines still expire when invalid input continues, including already queued records.
The worker owns a duplicated input descriptor and its own buffer, so a blocked read cannot hold Python's global
stdin buffer lock during shutdown. macOS `kqueue` detects parent EOF before new polls independently of reader-thread
scheduling. Queue shutdown releases a worker blocked on backpressure; a read still blocked at process exit ends with
the child. Only framing runs in the background; workflow operations and Bluetooth remain on the main thread.
Output is serialized completely before writing, then explicitly flushed; an oversized output is rejected before writing.
Human menu text is limited and controls are replaced with spaces before JSON escaping.

## Python to native

### View

```json
{"version":1,"type":"view","revision":3,"phase":"update_available","message":"An unsent image is available.","upload_available":true,"retained":false,"last_check":"2026-11-05T12:00:00+00:00","last_result":null,"error":null}
```

| Field | Contract |
| --- | --- |
| `revision` | Nonnegative integer, increasing whenever a changed view is emitted. |
| `phase` | One of the phases below. |
| `message` | Human status, at most 1000 characters. |
| `upload_available` | Whether an explicit Upload action is currently available. |
| `retained` | When true, label that action **Upload retained image** and retain poll-failure context. |
| `last_check` | Last successful check as an ISO 8601 timestamp, or `null`. |
| `last_result` | Last upload result, at most 1000 characters, or `null`. |
| `error` | Current error context, at most 1000 characters, or `null`. |

Phases are `starting`, `checking`, `up_to_date`, `update_available`, `preparing_upload`, `waiting_for_button`,
`sending`, `completed`, `skipped`, `poll_failed`, and `upload_failed`.

The native app rejects out-of-order revisions. Disable Check during `checking`, `preparing_upload`,
`waiting_for_button`, and `sending`. Disable Upload when `upload_available` is false. The native app disables workflow
actions immediately when sending an action, before the next view arrives. Identical views are not repeatedly emitted.

### Notification request

```json
{"version":1,"type":"notification","id":"unique-token","kind":"button","title":"Sign ready to upload","body":"Press the sign's button now."}
```

Kinds are `update_available`, `button`, `completed`, and `failed`. IDs are unique nonempty tokens of at most 128
characters. Titles contain at most 100 characters and bodies at most 1000.

The native app checks current notification settings for each request. It requests authorization when undetermined,
reports denial when denied, and uses the submission completion handler when authorized. Its delegate requests
foreground banner/list/sound presentation. Focus and user settings can still prevent a visible banner.
Errors appear in the menu; a successful retry clears an old notification error. Test Notification is entirely native
and changes no workflow state.

## Native to Python

### Acknowledgment

```json
{"version":1,"type":"ack","id":"unique-token","submitted":true,"error":null}
```

An unsuccessful submission uses `submitted: false` and an error of at most 1000 characters. The child waits for a
matching ID and accepts only a positive submission acknowledgment. Unmatched acknowledgments and actions received
while waiting are discarded. The timeout defaults to 15 seconds and is configurable, positive, and finite.

A button notification timeout or denial prevents Bluetooth discovery. EOF ends the controller and unwinds locks.
Acknowledgment proves submission, never visible delivery. Notification failure after successful transfer cannot change
`last-sent.png` or turn its completed result into an upload failure.

### Menu action

```json
{"version":1,"type":"action","action":"upload","revision":3}
```

Actions are `upload` and `check`. The revision must match the exact current view. Stale actions cannot retry an upload,
including actions buffered during a failed transfer. Quit is not an input action: the parent sends SIGTERM and waits
asynchronously for the child to unwind.

## Controller and state

Poll immediately after startup, then wait the configured interval after a completed poll. Do not replay missed intervals.
Poll and upload execute synchronously in the Python child; the native UI remains responsive. An explicit upload pauses
polling. After an upload attempt, perform a fresh poll before offering another image.

`desktop/machine.py` owns immutable workflow facts and a declarative table of allowed events, destination phases,
ordered effects, and view publication. Its pure `transition(state, event)` returns a decision; the controller executes
those effects and feeds their results back as events. Views are projections of workflow state, with revisions owned
by the session solely for stale-action rejection. Device progress uses the same transitions.

| Current phase | Event | Destination / work |
| --- | --- | --- |
| Starting, idle, or finished | Check or interval expiry | Checking; poll |
| Checking | Unsent image | Stay checking; inspect reminder history and request notification if needed |
| Checking | Reminder known or notification answered | Update available; remember only accepted submissions |
| Checking | Already sent | Up to date; clear reminder history |
| Checking | Poll failed | Poll failed; offer a retained unsent image if available |
| Update available, or poll failed with retained image | Upload | Preparing upload; snapshot and upload |
| Preparing upload | Validated button boundary | Waiting for button; require notification acknowledgment |
| Waiting for button | Connected | Sending |
| Upload in progress | Completed, skipped, or failed | Publish result; notify; check again |
| Any phase | Presentation failure | Preserve workflow outcome; show and report error |

Unlisted transitions do no work. Check and Upload cannot start overlapping work in busy phases.

A successful poll compares complete pending bytes with last-sent. One accepted update notification per unsent fingerprint
is retained in `desktop-reminder.json`, separate from the authoritative PNGs. Keep the view in nonactionable `checking`
while a new-image notification is awaiting acknowledgment, then emit `update_available` with any error context.
Advance history only after acknowledgment;
clear it when up to date. Failed polls retain the previous image but send no fresh update notification from that failure.
A contextual manual upload of retained content remains available when its pending image is unsent.

Typed device events identify validated discovery and connected sending boundaries. Do not parse stderr to infer phases.
Completed/skipped outcomes come from the existing snapshot operation; completion follows last-sent publication and lock
release. A newer pending image can coexist with the exact transferred snapshot.

`desktop.lock` prevents duplicate controllers. Acquisition waits briefly for an old instance to unwind; no lock is
automatically removed. Existing `poll.lock` and `upload.lock` retain their meanings. EOF is checked before every new
poll, including after an operation finishes. An operation already running when the native parent crashes may finish
before EOF is observed. A hung producer or forced kill may require documented manual stale-lock recovery.

## Explicit private configuration

```toml
command = ["/absolute/producer", "literal argument"]
device = "private device name or UUID"
interval = 300
notification_timeout = 15
# Optional overrides:
# working_directory = "~/projects/sign"
# state_directory = "~/.local/state/pwn-my-sign/another-display"
```

Unknown settings are rejected. Omitted `working_directory` means the configuration file's directory. Omitted
`state_directory` uses `${XDG_STATE_HOME:-$HOME/.local/state}/pwn-my-sign/display`, shared with terminal workflow
commands; empty or relative XDG values use the home fallback. Explicit directory overrides must be absolute after
`~` expansion; relative overrides are rejected. A relative producer executable resolves against `working_directory`,
and `~` in that executable expands. Producer arguments remain literal. Its working directory is explicitly set,
stdin is `/dev/null`, and no shell startup or activated environment is assumed. Pipelines must use an explicit producer
that propagates upstream failures.

The native build embeds absolute `MySignExecutable` and `MySignConfiguration` values in `Info.plist`, a stable bundle
identifier, and a Bluetooth usage description. It depends on the checkout and synced venv rather than bundling Python.
Ordinary Quit/sleep terminates the child and waits for cleanup. Wake waits for an existing child to actually exit before
starting a replacement. Pending actions and notification acknowledgments from an old child are discarded.
