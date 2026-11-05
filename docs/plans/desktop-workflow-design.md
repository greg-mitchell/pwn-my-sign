# Desktop workflow decision history

Historical design notes, 2026-11-05. Current behavior is defined by the [architecture](../architecture.md) and
[desktop protocol](../desktop-protocol.md). Installation instructions belong in the [desktop guide](../desktop-workflow.md).

## Decision

Use a native Swift/AppKit menu bar app with one Python workflow child. The requirements were reliable desktop
notifications, a persistent menu, simple local source builds, and no signing infrastructure.

The native app supplies the notification and Bluetooth permission identity. Python reuses the existing poller and
snapshot uploader. This preserves terminal workflows and avoids a second upload worker or scheduler.

## Alternatives investigated

| Option | Finding |
| --- | --- |
| SwiftBar streamable plugin | Menu actions worked, but notification submission did not establish visible delivery. |
| Python uploads under SwiftBar | Bluetooth scanning aborted because the responsible app lacked a usage description. |
| SwiftBar plus upload companion | A companion scan worked, but separate lifetimes required request/status persistence and restart reconciliation. |
| Native menu bar app | Visible notifications worked in a local source build; one parent and child simplified ownership. |

The native app supersedes the SwiftBar and companion proposal. No SwiftBar plugin, independently surviving upload
worker, or reattachment protocol is part of the implemented system.

## Implementation units

1. Typed upload boundaries and explicit completed/skipped outcomes.
2. Python desktop configuration, protocol, reminders, state machine, and runtime.
3. Native menu and notifications, child lifecycle, local build, and setup guide.

Review replaced manual pipe parsing with buffered input and a bounded queue, and nested controller branching with
declarative transitions. Details belong in the current architecture and protocol rather than this history.

## Acceptance status

Automated behavior and offline process checks are implemented. Local app launch, menu state, and visible notifications
have been exercised. Remaining live checks are tracked in the [implementation plan](implementation-plan.md#remaining-validation).

Personal captures, exploratory probes, and validation logs are local evidence under ignored `private/review/`.
