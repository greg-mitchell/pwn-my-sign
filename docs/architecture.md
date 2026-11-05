# Architecture

This is the conceptual model for the CLI and optional desktop app. See the [README](../README.md) for commands,
the [desktop guide](desktop-workflow.md) for setup, and the [desktop protocol](desktop-protocol.md) for JSON details.

## Composition and boundaries

```mermaid
flowchart LR
    source[Source adapter] -->|status code| selector[Image selector]
    renderer[Image renderer] -->|assets| selector
    selector -->|PNG| workflow[Python workflow]
    producer[Any image producer] -->|PNG| workflow
    workflow -->|image snapshot| sender[Device sender]
    sender -->|BLE| sign[Sign]
```

| Component | Responsibility |
| --- | --- |
| Source adapter | Validate provider data and emit a stable status code; classification policy is an explicit input. |
| Selector / renderer | Map a code to an existing image, or construct an image from explicit artwork, layout, and text. |
| Workflow | Validate desired images, compare and persist state, coordinate polling and manual uploads. |
| Device sender | Validate and encode an image, prompt for button wake, and transfer over BLE. |
| CLI | Parse arguments and delegate to domain operations with injected effects. |

Leaf commands do one operation and exit. Terminal watch and the desktop controller compose those operations into
foreground loops. External scheduling belongs to systemd, cron, or launchd; commands install no jobs.

## Stream contracts

1. Sources emit one status code and newline; selectors consume one code and emit the selected PNG's original bytes.
2. Producers emit one complete static 1280 × 720 PNG, log to stderr, and exit zero. Workflows pass literal arguments
   without an implicit shell. Producer-command mode observes exit status; piped image bytes cannot carry it.
3. Validate complete inputs before publication, output, button prompts, or Bluetooth discovery. Invalid data never
   implies a healthy source or replaces a valid image.
4. Data belongs on stdout; diagnostics, progress, and prompts belong on stderr. Nonzero exit indicates failure.

Command options and examples are in the [README](../README.md#composable-tools). Verified device behavior is in the
[BLE protocol](protocol.md).

## Workflow state

| Artifact | Meaning |
| --- | --- |
| `pending.png` | Latest complete desired image. |
| `last-sent.png` | Exact snapshot whose transfer calls last completed successfully. |

1. Publish changed pending images atomically. Failed producers preserve the previous image.
2. Snapshot pending before upload; skip when it matches last-sent. Advance last-sent only after successful transfer
   calls. A newer pending image survives an older snapshot's transfer.
3. Completion records transfer calls, not confirmation of the physical display.
4. Use one state directory per sign, shared by every terminal and desktop invocation. Separate poll and upload locks
   allow polling during a transfer while preventing overlapping instances of the same operation.
5. Polling prepares images; uploading is an explicit foreground action. Failed polls retain the last desired image
   for contextual manual upload. The terminal watcher waits for a successful poll before offering it again.

Defaults, overrides, and lock recovery are documented in the [workflow guide](../README.md#image-workflows).

## Desktop integration

| Component | Owns |
| --- | --- |
| Native macOS app | Menu, notification permissions and submission, diagnostic logs, Python child lifetime. |
| Python controller | Poll timing, reminder history, workflow state, and the existing snapshot uploader. |
| State machine | Immutable workflow facts and declarative event → state/effect decisions. |
| Protocol session | Versioned JSON records, notification acknowledgments, and view revisions. |

The native app owns one Python child. Polling and uploads run synchronously in that child; the native menu stays
responsive. Views project workflow state, and revision-matched actions prevent stale clicks from starting work.
The [transition table](../src/greg_mitchell/pwn_my_sign/desktop/machine.py) is the implementation source of truth.

```mermaid
stateDiagram-v2
    [*] --> Checking
    Checking --> Idle: poll result and reminder handling
    state "Idle: up to date, update available, or poll failed" as Idle
    Idle --> Checking: interval or Check
    Idle --> Uploading: Upload available image
    state Uploading {
        [*] --> Preparing
        Preparing --> WaitingForButton: validated snapshot
        WaitingForButton --> Sending: connected
    }
    state "Result: completed, skipped, or failed" as Result
    Uploading --> Result
    Result --> Checking: fresh poll
```

## Desktop interaction

```mermaid
sequenceDiagram
    actor Person
    participant App as Native app
    participant Controller as Python controller
    participant Workflow as Workflow / sender
    App->>Controller: Launch with explicit configuration
    Controller->>Workflow: Poll and compare image state
    opt Newly unsent image not already notified
        Controller->>App: Update notification request
        App-->>Controller: Submission acknowledgment
    end
    Controller->>App: Actionable view
    Person->>App: Upload
    App->>Controller: Action with current view revision
    Controller->>Workflow: Snapshot and validate
    Workflow->>Controller: Waiting-for-button event
    Controller->>App: Button notification request
    App-->>Controller: Submission acknowledgment
    Workflow->>Workflow: Discover, connect, transfer, record snapshot
    Controller->>App: Result view and notification request
    App-->>Controller: Submission acknowledgment
    Controller->>Workflow: Poll again
```

1. Button-notification acknowledgment gates discovery. Denial, timeout, or EOF stops preparation; acknowledgment
   establishes submission, not visible delivery. Later notification errors cannot undo a completed transfer.
2. Remember an update notification only after accepted submission, once per unsent image. This reminder history is
   separate from image state and clears when up to date.
3. Poll immediately, then wait an interval after each completed check. Upload pauses polling; missed intervals are
   not replayed. Busy phases reject new workflow actions.
4. Quit and sleep cancel the child and wait for cleanup. Wake starts a replacement only after the previous child exits.
   Parent EOF prevents another poll. `desktop.lock` prevents duplicate controllers; locks are never removed automatically.
