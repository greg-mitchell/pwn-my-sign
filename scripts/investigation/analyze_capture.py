import collections
import datetime
import json
import struct
import sys
import uuid
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

from greg_mitchell.pwn_my_sign.frame_codec import decode_frame

archive = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("private")
out.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as z:
    raw = z.read("FS/data/misc/bluetooth/logs/btsnoop_hci.log")
(out / "btsnoop_hci.log").write_bytes(raw)
assert raw[:8] == b"btsnoop\0"
assert struct.unpack(">II", raw[8:16]) == (1, 1002)
position = 16
buffers = {}
att = []
connections = []
fragment_counts = collections.Counter()
pending_read_types = {}
while position + 24 <= len(raw):
    original, length, flags, drops, stamp = struct.unpack(
        ">IIIIQ", raw[position : position + 24]
    )
    position += 24
    packet = raw[position : position + length]
    position += length
    time = (
        datetime.datetime.fromtimestamp(
            (stamp - 0x00DCDDB30F2F8000) / 1e6, datetime.UTC
        )
        .astimezone(ZoneInfo("America/Los_Angeles"))
        .isoformat()
    )
    if len(packet) >= 7 and packet[:2] == b"\x04\x3e" and packet[3] in (1, 10):
        connections.append(
            {
                "time": time,
                "handle": int.from_bytes(packet[5:7], "little"),
                "kind": "connect",
            }
        )
    if len(packet) >= 7 and packet[:2] == b"\x04\x05":
        connections.append(
            {
                "time": time,
                "handle": int.from_bytes(packet[4:6], "little"),
                "kind": "disconnect",
                "reason": packet[6],
            }
        )
    if not packet or packet[0] != 2:
        continue
    handle_flags, acl_length = struct.unpack("<HH", packet[1:5])
    handle = handle_flags & 0xFFF
    boundary = (handle_flags >> 12) & 3
    direction = "rx" if flags & 1 else "tx"
    fragment_counts[boundary] += 1
    fragment = packet[5:]
    assert len(fragment) == acl_length
    key = handle, direction
    if boundary in (0, 2):
        buffers[key] = (time, bytearray(fragment))
    elif boundary == 1 and key in buffers:
        buffers[key][1].extend(fragment)
    else:
        continue
    start, payload = buffers[key]
    if len(payload) < 4:
        continue
    l2length, cid = struct.unpack("<HH", payload[:4])
    if len(payload) < l2length + 4:
        continue
    assert len(payload) == l2length + 4
    del buffers[key]
    if cid != 4:
        continue
    value = bytes(payload[4:])
    item = {
        "time": start,
        "connection": handle,
        "direction": direction,
        "opcode": value[0],
        "hex": value.hex(),
    }
    if value[0] == 8:
        pending_read_types[handle] = value[5:].hex()
    elif value[0] == 9:
        item["read_type"] = pending_read_types.get(handle)
    if value[0] in (0x12, 0x52, 0x1B, 0x1D, 0x0A) and len(value) >= 3:
        item["attribute"] = int.from_bytes(value[1:3], "little")
    att.append(item)

(out / "att.json").write_text(json.dumps(att, indent=2) + "\n")
print("Output:", out)
print("Connections:", json.dumps(connections, indent=2))
print("ACL fragment boundaries:", dict(fragment_counts))
for connection in sorted({item["connection"] for item in att}):
    items = [item for item in att if item["connection"] == connection]
    print("\nCONNECTION", hex(connection), "ATT messages", len(items))
    counts = collections.Counter(
        (item["direction"], hex(item["opcode"]), item.get("attribute"))
        for item in items
    )
    print("Counts:", dict(counts))
    for index, item in enumerate(items):
        packet = bytes.fromhex(item["hex"])
        if (
            item["opcode"] in (0x52, 0x12)
            and len(packet) > 40
            and index > 0
            and items[index - 1]["opcode"] == item["opcode"]
            and len(bytes.fromhex(items[index - 1]["hex"])) > 40
        ):
            continue
        print(item["time"], item["direction"], "len", len(packet), packet[:100].hex())
        if item["opcode"] == 0x11:
            size = packet[1]
            for offset in range(2, len(packet), size):
                entry = packet[offset : offset + size]
                service = (
                    str(uuid.UUID(bytes=entry[4:20][::-1]))
                    if len(entry) == 20
                    else entry[4:][::-1].hex()
                )
                print(
                    "SERVICE",
                    int.from_bytes(entry[:2], "little"),
                    int.from_bytes(entry[2:4], "little"),
                    service,
                )
        if item["opcode"] == 0x09 and item.get("read_type") == "0328":
            size = packet[1]
            for offset in range(2, len(packet), size):
                entry = packet[offset : offset + size]
                characteristic = (
                    str(uuid.UUID(bytes=entry[5:21][::-1]))
                    if len(entry) == 21
                    else entry[5:][::-1].hex()
                )
                print(
                    "CHARACTERISTIC",
                    "decl",
                    int.from_bytes(entry[:2], "little"),
                    "properties",
                    hex(entry[2]),
                    "value",
                    int.from_bytes(entry[3:5], "little"),
                    characteristic,
                )
    for attribute in sorted(
        {item["attribute"] for item in items if "attribute" in item}
    ):
        writes = [
            bytes.fromhex(item["hex"])[3:]
            for item in items
            if item.get("attribute") == attribute and item["opcode"] in (0x12, 0x52)
        ]
        if not writes:
            continue
        stream = b"".join(writes)
        destination = out / f"connection-{connection:04x}-attribute-{attribute:04x}.bin"
        destination.write_bytes(stream)
        print(
            "WRITE STREAM",
            destination.name,
            "bytes",
            len(stream),
            "chunks",
            len(writes),
            "sizes",
            dict(collections.Counter(map(len, writes))),
        )
        print("FIRST", stream[:128].hex(), "LAST", stream[-64:].hex())
        if stream.startswith(b"!I") and len(stream) == 460802:
            label = {64: "test-a", 65: "test-b"}.get(
                connection, f"connection-{connection:04x}"
            )
            (out / f"{label}.frame").write_bytes(stream[2:])
            decode_frame(stream[2:]).save(out / f"{label}.png")
print("Incomplete ACL buffers:", len(buffers))
