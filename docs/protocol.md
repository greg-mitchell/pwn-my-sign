# Dory BLE protocol

This documents one owner's sign, observed through Dory Android app 1.5.0 on a Pixel 8 running Android 17.
The format below has also been used successfully by the Python sender on macOS.
Firmware identity and chip model have not been determined. Treat unobserved commands as unknown.

## Evidence

Two successful Android updates were captured on 2026-10-22 in America/Los_Angeles (UTC−07:00):

| Image | Connected | Image writes | Disconnected |
| --- | --- | --- | --- |
| TEST A | 11:42:20.907692 | 11:42:24.006614–11:43:56.771509 | 11:43:58.621584 |
| TEST B | 11:44:29.423813 | 11:44:32.514338–11:46:05.184848 | 11:46:06.450710 |

The extracted `btsnoop_hci.log` is 1,329,771 bytes, from 11:41:33–11:55:13.
The source Android bug report, raw logs, and app-rendered TEST A / TEST B image payloads stay private.
Public fixtures are independently generated patterns; see [provenance](provenance.md).

The Mac replay took 109.2469 seconds, including discovery and connection, with confirmed sign image change.
The generated PNG upload took 108.5904 seconds. I took a photo, which shows the unique generated identifier and intended
layout. See [display calibration](display-calibration.md) for photo alignment notes.

## Services and characteristics

The UUIDs match [Nordic UART Service](https://docs.nordicsemi.com/r/bundle/nrf5_sdk_v15.2.0/page/ble_sdk_app_nus_eval.html).
UUID reuse alone does not establish the chip model.

| Purpose | UUID | Captured properties |
| --- | --- | --- |
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | Primary service |
| Host → sign | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | Read, write, write without response |
| Sign → host | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | Read, notify |

In the captures, the write value handle is `0x002a`, the notification value handle is `0x002c`, and its CCCD is `0x002d`.
The sender discovers by UUID rather than assuming those handles are stable.

## Observed upload sequence

1. Press the sign's physical button and connect over BLE.
2. Discover the service and negotiate ATT MTU 517 in the Android sessions.
3. Enable notifications by writing `01 00` to the CCCD.
4. Write the two bytes `21 49` (ASCII `!I`) to the host → sign characteristic, **without response**, as a separate write.
5. Write exactly 460,800 image bytes in **1,920 writes of 240 bytes**, also without response.
6. Disconnect after the image stream. No separate finish/refresh command was present in either capture.

The current sender subscribes to notifications, waits two seconds, checks that the platform permits at least 240 bytes
per write, sends `!I`, waits 20 ms, and streams 240-byte chunks with a conservative 50 ms pause between chunks.
It waits two seconds before disconnecting. This pacing worked on the owner's Mac; Android's captured pacing was bursty.
Changing chunk size, reducing pacing, or relying on disconnect as a refresh trigger requires a separate experiment.

No notification or application-level completion acknowledgement appeared in the captured sessions.
An upload command returning zero means its transfer calls completed; physical display confirmation remains separate.

## Image encoding

- Native canvas: **1280 × 720**.
- Payload: **460,800 bytes**, four bits per pixel, two pixels per byte.
- Values: `0` is black, `15` is white; decoded 8-bit preview values are `level × 17`.
- Rows arrive top to bottom. Pixels within each row arrive **right to left**.
- The high nibble is the first pixel in the stream; the low nibble is the next pixel.

For source row `y` and byte position `j` in `[0, 640)`, the high nibble represents source pixel
`(1279 − 2j, y)` and the low nibble represents `(1278 − 2j, y)`.

The encoder converts input to grayscale, reverses each row, rounds to the nearest of 16 levels, and packs adjacent nibbles.
It requires exact input dimensions and performs no resizing or cropping. Source dimensions and row direction were verified
by local captured-payload round trips, public marked-corner tests, and the generated-image photograph.
Content margins belong in layout generation, as described in [display calibration](display-calibration.md).

## Identity, authorization, and limits

The observed advertised name and the Mac's local UUID are kept in `private/device.json`.
macOS device identifiers differ from Bluetooth MAC addresses and are local to the scanning computer.
See [Bleak's macOS notes](https://bleak.readthedocs.io/en/stable/backends/macos.html).

No app authentication exchange, SMP traffic, or HCI encryption-change event was observed in these two sessions.

Physical wake is required on the tested unit. Note that Dory documents approximately 1,000 updates, see 
[Dory's product information](https://dorysign.com/products/dory-sign) and [FAQ](https://dorysign.com/pages/faq).

## Reproduction tools

After `uv sync --locked`:

```sh
uv run python scripts/investigation/analyze_capture.py private/BUGREPORT.zip private/reextracted
```

The scratch parser reads HCI packets, reconstructs ACL/L2CAP messages, decodes ATT, extracts write streams,
and reconstructs diagnostic PNGs. It is an investigation tool, not a general-purpose Bluetooth parser.
Android's [Bluetooth debugging instructions](https://source.android.com/docs/core/connect/bluetooth/verifying_debugging)
explain HCI snoop logging and report extraction.
