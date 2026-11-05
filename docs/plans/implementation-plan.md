# Implementation plan

Planning and acceptance tracking, 2026-11-05. For current behavior, see the [architecture](../architecture.md).
For setup and commands, see the [README](../../README.md) and [desktop guide](../desktop-workflow.md).

## Milestones

| Milestone | State |
| --- | --- |
| Learn the BLE protocol and replay a captured image | Complete |
| Generate and send custom content | Complete |
| Package composable CLI tools with offline tests and developer checks | Complete |
| Compose GitHub source classification and private static-card selection | Complete |
| Add deterministic card rendering from explicit layout, artwork, text, and font inputs | Complete |
| Add polling, snapshots, locks, terminal reminders, and scheduler recipes | Implemented; migrated workflow needs hardware revalidation |
| Stream device discovery results with useful names and identifiers | Implemented; live verification pending |
| Add native desktop menu, notifications, and Python controller | Implemented; live acceptance pending |

## Desktop review units

| Unit | Scope | State |
| --- | --- | --- |
| Upload events | Typed validation/discovery and connected boundaries; completed/skipped outcome | Implemented |
| Controller | Configuration, bounded JSON IPC, reminders, immutable state and declarative transitions | Implemented |
| Native app | Menu, notifications, child lifetime, source build and setup | Implemented; in review |

The [desktop decision history](desktop-workflow-design.md) records the investigated alternatives. Current contracts
belong in architecture and protocol references, not acceptance plans.

## Remaining validation

1. Verify device discovery against a live sign.
2. Revalidate the migrated Python workflow with a real upload and physical refresh.
3. Exercise notification denial/recovery and Bluetooth permission grant/denial in the installed desktop app.
4. Complete a desktop upload with button timing; verify duplicate clicks and a newer pending image during transfer.
5. Quit and sleep/wake during production and transfer; inspect state, child cleanup, and locks.
6. Check rebuilding, environment recreation, and optional login startup.
7. Exercise scheduler recipes when choosing to use one; no scheduler has been installed for validation.

Automated checks cover domain behavior, native framing/menu/lifecycle behavior, and offline process shutdown.
They do not establish hardware or operating-system permission behavior. Detailed run evidence stays in ignored
`private/review/`, rather than the user guide.

## Deferred work

Dynamic rendering from live source data remains optional. Distributed standalone Python packaging, automatic uploads,
multiple-device UI, and automatic stale-lock removal are outside the desktop scope.
