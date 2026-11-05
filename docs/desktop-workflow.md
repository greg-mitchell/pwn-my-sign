# macOS desktop workflow

The optional **My Sign** menu bar app checks for a changed image, notifies you once when a new image needs uploading,
and offers Upload from its menu. After you choose Upload, it validates the image, submits a notification telling you
to press the sign's button, and starts discovery. The existing Python workflow owns polling, snapshots, locks, and
recording completed transfers. No SwiftBar installation or separate scheduled job is needed.

## Build from source

Use the checkout and synced Python environment from the [README](../README.md#setup). Install Apple's command-line
developer tools if `xcrun swift --version` is unavailable. The app uses Swift 6 and macOS 13 or newer; the tools on the
machine must support Swift 6. A full Xcode project, Apple account, developer membership, certificate setup, and
notarization service are unnecessary for a local build. The build command applies an ad hoc signature automatically.

1. Prepare an executable image producer as described in the [workflow recipes](../README.md#image-workflows).
   It must emit one static 1280 × 720 PNG and exit zero, with diagnostics on stderr.
2. Copy [the example configuration](../data/desktop.example.toml) to ignored `private/desktop.toml`:

   ```sh
   cp data/desktop.example.toml private/desktop.toml
   ```

3. Edit `device` to the name or UUID found by `mysign device scan`. Set `command` to your producer's literal arguments.
   Paths for `working_directory` and `state_directory` resolve relative to the configuration file. The producer
   executable resolves relative to `working_directory`; the example copied into `private/` uses the checkout root and
   `private/produce-image`. Other producer arguments remain literal. Use absolute paths to assets and other executables
   inside producer scripts, without depending on shell startup files or an activated environment.
4. Build and open the app from the checkout root:

   ```sh
   uv run mysign workflow desktop-build --config private/desktop.toml --output 'private/desktop/My Sign.app'
   open 'private/desktop/My Sign.app'
   ```

Keep the checkout, configuration, and `.venv` at those paths. The app records their absolute locations in its bundle;
it does not copy Python, artwork, fonts, or configuration into a distribution. Run `uv sync --locked` after dependency
changes. Quit the app before rebuilding. A failed build or signing step preserves an existing built app.

The app has one stable bundle identifier and installation path, but a local signature does not guarantee privacy
permission persistence across changed binary builds. macOS may ask for permission again after rebuilding. Keep using
the same app location; do not modify the signed bundle after building it. Moving the checkout requires rebuilding.
See [Apple's explanation of code identity](https://developer.apple.com/documentation/technotes/tn3127-inside-code-signing-requirements/).

## First launch and notifications

Use **Test notification** in the My Sign menu, allow notifications if macOS asks, and verify a visible banner. The
native app checks current notification settings on each request and reports permission or submission errors in its
menu. A successful retry clears an earlier notification error. If notifications are denied, enable them for My Sign
in macOS notification settings and test again. Focus and notification presentation preferences can suppress or delay
banners even when submission succeeds; the menu remains available.

The disposable native probe delivered visible notifications on the development Mac, including a menu-triggered
retry after permission was allowed. That is evidence for the native integration choice, not a substitute for testing
the installed app's permissions. The probe used a different bundle identity, so its grant does not grant the built app
permission automatically.

The app checks immediately and then waits `interval` seconds after each check completes. It remembers the last
notified unsent image across ordinary restarts and clears that reminder history when the desired image is up to date.
Dismissing a notification does not mark an image sent. There are no recurring reminders, snooze, or automatic uploads.

Choose **Upload** when an unsent image is available. Allow Bluetooth access for My Sign if asked. Press the sign's
button when the app says **Press the sign's button now**. The discovery window is 60 seconds; a missed window leaves
the image available for explicit retry. The menu stays responsive during the transfer and disables duplicate workflow
actions. Completed means the transfer calls finished and the uploaded snapshot was recorded; check the physical sign
to confirm its refresh, because the protocol provides no completion acknowledgment.

The Python process will not scan until the app confirms successful button-notification submission. Denial,
submission failure, a disconnected app, or a prompt acknowledgment timeout stops preparation. A failure to notify
after transfer completion does not undo the completed transfer or its last-sent record.

## Failures, quit, and sleep

Producer failure preserves the previous pending image, shows the error and last successful check, and retries at the
normal interval. If the retained image differs from last-sent, **Upload retained image** is an explicit manual action
with that failure context; it is not presented as a fresh source update.

Quit cancels the Python helper and waits for its cleanup. Sleep requests the same cancellation; wake starts one fresh
helper only after the previous process has actually stopped. Missed checks are not replayed. A parent crash closes
the helper's input; it exits before another poll, possibly after finishing its current operation.

One `desktop.lock` per state directory prevents duplicate controllers. Existing `poll.lock` and `upload.lock` retain
their meanings, so terminal operations can share the same state directory. Startup briefly waits for a previous
controller to unwind. It does not automatically delete locks.

A hung producer or a forced kill can require [manual lock recovery](../README.md#locks-and-recovery). Confirm the
owning process and its children have stopped before removing lock files. Never infer successful transfer from a
vanished process; `last-sent.png` remains the authoritative record of completed transfer calls. Removing only
`desktop-reminder.json` resets reminder history without changing image state.

Diagnostics are kept in bounded local logs alongside the private configuration. The menu's latest workflow and
notification errors are the first place to look. No notification or transfer uses shell command interpretation.

## Login and removal

Optionally add the built app using macOS Login Items. The build does not enable login startup or install launchd,
cron, or another scheduler. See [Apple's login-item instructions](https://support.apple.com/guide/mac-help/mh15189/mac).

To remove it, quit My Sign, remove its login item if you added one, and delete the built app. Keep or remove the private
configuration and logs as desired. Workflow images remain usable from the terminal. No third-party app is modified.

## Validation

Run `uv run poe check-all` from the checkout root. Python behavior tests inject effects and do not use Bluetooth,
network, subprocesses, threads, or real waits. Native tests cover framing, action gating, notification retries, and
sleep/wake process coordination without launching the app. The native test task skips platforms other than macOS.

Before relying on unattended checks, validate the actual installed app:

- Test a visible notification and useful menu behavior with permission denied and then enabled.
- Test Bluetooth permission grant/denial and one real upload with correct button timing.
- Check that repeated clicks do not duplicate uploads and newer pending content survives an older snapshot transfer.
- Quit, relaunch, and sleep/wake during a producer and during transfer; inspect image state and locks.
- Rebuild, recreate the environment, and check permissions and paths again. Check login startup if enabled.

These hardware and operating-system transitions require live acceptance; automated unit tests do not establish them.
The design and process contract are recorded in [the design](desktop-workflow-design.md) and
[the JSON protocol](desktop-protocol.md).
