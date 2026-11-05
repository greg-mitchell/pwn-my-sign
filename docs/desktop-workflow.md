# macOS menu bar app

**My Sign** checks for changed images, notifies you when an upload is available, and offers Upload from its menu.
Uploads require pressing the sign's physical button.

## Build and launch

1. Complete the [Python setup](../README.md#setup). For the app, use macOS 13 or newer and Apple's Command Line Tools
   with Swift 6 or newer. Install the tools with `xcode-select --install`.
2. Prepare an executable [image producer](../README.md#image-workflows) that writes a static 1280 × 720 PNG to stdout.
3. Copy the configuration and set `device` and `command`:

   ```sh
   mkdir -p private
   cp data/desktop.example.toml private/desktop.toml
   ```

   The example runs `private/produce-image`. Scan for the device with `uv run mysign device scan`.
4. Build and open the app from the checkout root:

   ```sh
   make app
   open 'private/desktop/My Sign.app'
   ```

`make app` checks prerequisites, syncs Python dependencies, and builds and locally signs the app. Full Xcode and an
Apple developer account are unnecessary. Override paths with the `CONFIG` and `APP` Make variables.

The app uses the checkout's `.venv` and configuration at their recorded paths. Quit before rebuilding; rebuild after
moving the checkout.

## Configuration

| Setting | Default / meaning |
| --- | --- |
| `command` | Required producer argument array; arguments are literal, without an implicit shell. |
| `device` | Required sign name or ID from `device scan`. |
| `interval` | Seconds between checks, measured after each check finishes; default 300. |
| `notification_timeout` | Seconds to wait for notification submission; default 15. |
| `working_directory` | Configuration file's directory; relative producer executables resolve here. |
| `state_directory` | `$XDG_STATE_HOME/pwn-my-sign/display`, falling back to `~/.local/state/pwn-my-sign/display`. |

Directory overrides accept absolute paths and `~`. Use absolute asset paths inside producer scripts. Set
`state_directory` explicitly if Finder and your terminal have different `XDG_STATE_HOME` values, or to manage another
sign. Terminal workflow commands can share this directory using `--state`.

## Upload an image

1. Open the My Sign menu and choose **Test notification**. Allow notifications and confirm a banner appears.
2. When an update is available, choose **Upload**. Allow Bluetooth access if prompted.
3. Press the sign's button when the notification says **Press the sign's button now**. Discovery waits up to 60 seconds.
4. Check the physical display after completion. The sign's protocol does not acknowledge its refresh.

The app notifies once per unsent image and never uploads automatically. Use **Check** for an immediate check.

## Troubleshooting and removal

1. Read the latest error in the menu. Diagnostics are in `desktop-logs/` beside the configuration.
2. For missing banners, enable My Sign in macOS notification settings, check Focus, and retry **Test notification**.
   Rebuilding may require granting permissions again.
3. A failed check preserves the previous image. **Upload retained image** sends that image; **Check** retries the producer.
4. If a lock remains after a crash, follow [lock recovery](../README.md#locks-and-recovery).
5. Optionally add the app to [Login Items](https://support.apple.com/guide/mac-help/mh15189/mac).
   To remove it, quit, remove its login item, and delete the app. Workflow images remain available to terminal commands.

See [architecture](architecture.md#desktop-integration) for component ownership and lifecycle, and
[the desktop protocol](desktop-protocol.md) for the process interface.
