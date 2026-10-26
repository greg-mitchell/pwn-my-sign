# Schedule status polling

First run the [foreground workflow](../README.md#github-workflow) successfully. These examples poll every five minutes
and leave uploads as manual terminal actions. They do not wake the sign. Failed polls retain potentially stale pending
images; check the scheduler's errors before sending retained content.

Replace every example path with your absolute checkout, map, policy, and state paths. Run `uv sync` in the checkout
after dependency changes; scheduled jobs invoke its existing `.venv/bin/mysign` directly. Keep that checkout and
environment available. Use one state directory for every invocation targeting the same device.
The workflow locks reject overlap, including overlapping invocations from different schedulers.

## Linux: systemd user timer

Create `~/.config/systemd/user/mysign-poll.service` with:

```ini
[Unit]
Description=Prepare the latest GitHub status sign image

[Service]
Type=oneshot
ExecStart=/home/you/pwn-my-sign/.venv/bin/mysign workflow poll --state /home/you/.local/state/pwn-my-sign/github --map /home/you/pwn-my-sign/private/images.toml --policy /home/you/pwn-my-sign/data/github-actions.toml
```

Create `~/.config/systemd/user/mysign-poll.timer` with:

```ini
[Unit]
Description=Poll GitHub status every five minutes

[Timer]
OnStartupSec=1min
OnUnitInactiveSec=5min

[Install]
WantedBy=timers.target
```

Explicit setup and inspection commands:

```sh
systemctl --user daemon-reload
systemctl --user enable --now mysign-poll.timer
systemctl --user list-timers mysign-poll.timer
journalctl --user -u mysign-poll.service
```

Stop future polling with `systemctl --user disable --now mysign-poll.timer`.
An active service finishes separately. This user timer runs while the user service manager is available;
it does not configure login persistence. The journal collects errors without needing a custom log directory.
Systemd's [timer reference](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
defines activation intervals and avoids restarting a service that is already active.

## Linux or macOS: cron

Create the state/log directory first. In `crontab -e`, add an entry using your actual paths:

```cron
PATH=/usr/bin:/bin
*/5 * * * * /home/you/pwn-my-sign/.venv/bin/mysign workflow poll --state /home/you/.local/state/pwn-my-sign/github --map /home/you/pwn-my-sign/private/images.toml --policy /home/you/pwn-my-sign/data/github-actions.toml >> /home/you/.local/state/pwn-my-sign/github/poll.log 2>&1
```

On macOS substitute `/Users/you/...` paths. Quote paths containing spaces. The commands use the checkout's Python
environment rather than shell startup configuration. Rotate the log as needed and remove the crontab entry
to stop scheduling. Cron does not provide the workflow lock; the command does.
See the [crontab reference](https://man7.org/linux/man-pages/man5/crontab.5.html) for its environment and command syntax.

## macOS: launchd user agent

Create the state/log directory first. Save this as `~/Library/LaunchAgents/local.mysign.github-poll.plist`, replacing
each path. `ProgramArguments` passes each value literally: use absolute paths rather than `~`, `$HOME`, or shell quotes.
Escape XML special characters in paths if needed.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>local.mysign.github-poll</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/you/pwn-my-sign/.venv/bin/mysign</string>
        <string>workflow</string>
        <string>poll</string>
        <string>--state</string>
        <string>/Users/you/.local/state/pwn-my-sign/github</string>
        <string>--map</string>
        <string>/Users/you/pwn-my-sign/private/images.toml</string>
        <string>--policy</string>
        <string>/Users/you/pwn-my-sign/data/github-actions.toml</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/you/.local/state/pwn-my-sign/github/poll.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/you/.local/state/pwn-my-sign/github/poll.log</string>
</dict>
</plist>
```

Validate and explicitly load it:

```sh
plutil -lint "$HOME/Library/LaunchAgents/local.mysign.github-poll.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.mysign.github-poll.plist"
launchctl print "gui/$(id -u)/local.mysign.github-poll"
```

Unload with `launchctl bootout "gui/$(id -u)/local.mysign.github-poll"`; remove the plist to prevent future login loading.
The user agent requires a logged-in session. Inspect and rotate `poll.log`; no desktop notifications are configured.
See Apple's [launchd job guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
for `ProgramArguments`, interval scheduling, and log paths. Check local `man launchctl` for commands on your macOS release.
