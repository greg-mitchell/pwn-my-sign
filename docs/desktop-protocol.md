# Native desktop process protocol

The native menu bar app starts exactly one checkout executable:

```text
/absolute/checkout/.venv/bin/mysign workflow desktop --config /absolute/private/desktop.toml
```

The Python child owns polling, workflow image state, reminder history, and explicit uploads. The native parent owns
menus, notification permission/submission, Test Notification, bounded diagnostic logs, and child lifetime.
The [architecture](architecture.md#desktop-integration) defines ownership, state transitions, and interaction order.
This reference defines the process wire contract; it does not alter image encoding or the BLE wire protocol.

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

## Session boundaries

Keep the view in nonactionable `checking` while an update notification awaits acknowledgment, then emit
`update_available` with any error context. Device callbacks supply phases; diagnostics are never protocol input.

Pending actions and notification acknowledgments belong to one child session. Discard them when that child exits;
a replacement starts with a new session. EOF prevents the child from starting another poll, though an operation
already running may finish first.

Configuration settings are documented in the [desktop guide](desktop-workflow.md#configuration).
