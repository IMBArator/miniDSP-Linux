#!/usr/bin/env python3
"""
Extract and decode HID interrupt transfer payloads from a Wireshark text export.
Focuses on opcode 0x34 (input gain commands) for the T.racks DSPmini 4x4.

Frame format: 10 02 [SRC] [DST] [LEN] [PAYLOAD...] 10 03 [XOR_CHK]
"""

import re
import struct

CAPTURE_FILE = "/home/max/src/miniDSP-Linux/miniDSP Capture - move input gain fader ch3 from -60 to 0 dB.txt"

# Regex patterns
PACKET_HEADER_RE = re.compile(
    r'^\s+(\d+)\s+([\d.]+)\s+(\S+)\s+(\S+)\s+\S+\s+\d+\s+URB_INTERRUPT\s+(in|out)\s*$'
)
HID_DATA_RE = re.compile(r'^HID Data:\s+([0-9a-fA-F]+)\s*$')
FRAME_NUMBER_RE = re.compile(r'^\s+Frame Number:\s+(\d+)\s*$')

def decode_frame(hid_hex):
    """
    Decode a miniDSP HID frame.
    Returns dict with keys: src, dst, length, payload, checksum_ok, opcode
    or None if the hex doesn't look like a valid miniDSP frame.
    """
    try:
        data = bytes.fromhex(hid_hex)
    except ValueError:
        return None

    if len(data) < 8:
        return None

    # Framing: 10 02 [SRC] [DST] [LEN] [PAYLOAD...] 10 03 [CHK]
    if data[0] != 0x10 or data[1] != 0x02:
        return None

    src = data[2]
    dst = data[3]
    length = data[4]

    # payload occupies bytes 5 .. 5+length-1
    payload_start = 5
    payload_end = payload_start + length
    if payload_end + 2 > len(data):
        return None  # not enough bytes

    payload = data[payload_start:payload_end]

    # After payload: 10 03 CHK
    if data[payload_end] != 0x10 or data[payload_end + 1] != 0x03:
        return None

    checksum = data[payload_end + 2]

    # Verify XOR checksum: length XOR all payload bytes
    expected_chk = length
    for b in payload:
        expected_chk ^= b
    checksum_ok = (checksum == expected_chk)

    opcode = payload[0] if payload else None

    return {
        "src": src,
        "dst": dst,
        "length": length,
        "payload": payload,
        "checksum_ok": checksum_ok,
        "opcode": opcode,
    }


def parse_capture(filepath):
    """
    Parse the Wireshark text export and yield records for every
    URB_INTERRUPT transfer that carries a 64-byte HID payload.

    Each yielded dict has:
        frame_number, timestamp, direction, hid_hex, decoded
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    results = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].rstrip("\n")

        # Look for the summary line that starts a packet block:
        #   "     79 0.181959   host   1.17.2   USB   91   URB_INTERRUPT out"
        m = PACKET_HEADER_RE.match(line)
        if m:
            pkt_num    = int(m.group(1))
            timestamp  = m.group(2)
            src_addr   = m.group(3)
            dst_addr   = m.group(4)
            direction  = m.group(5)  # "in" or "out"

            # Scan forward in this packet block for the actual Frame Number
            # and the HID Data line.
            frame_number = pkt_num  # fallback
            hid_hex = None
            j = i + 1
            while j < n:
                l = lines[j].rstrip("\n")
                # Stop when we hit the next packet header (blank line then "No.")
                if PACKET_HEADER_RE.match(l):
                    break
                fm = FRAME_NUMBER_RE.match(l)
                if fm:
                    frame_number = int(fm.group(1))
                hm = HID_DATA_RE.match(l)
                if hm:
                    hid_hex = hm.group(1)
                    break
                j += 1

            if hid_hex and len(hid_hex) == 128:  # 64 bytes = 128 hex chars
                decoded = decode_frame(hid_hex)
                results.append({
                    "frame_number": frame_number,
                    "timestamp": timestamp,
                    "direction": direction,
                    "src_addr": src_addr,
                    "dst_addr": dst_addr,
                    "hid_hex": hid_hex,
                    "decoded": decoded,
                })

            i = j
            continue

        i += 1

    return results


def main():
    records = parse_capture(CAPTURE_FILE)

    gain_cmds  = []
    poll_count = 0
    ack_count  = 0
    level_resp_count = 0
    other_count = 0

    for rec in records:
        d = rec["decoded"]
        if d is None:
            other_count += 1
            continue

        opcode = d["opcode"]
        payload = d["payload"]

        if opcode == 0x34:
            # Input gain command: 34 [ch] [val_lo] [val_hi]
            if len(payload) >= 4:
                channel = payload[1]
                raw_val = struct.unpack_from("<H", payload, 2)[0]
                gain_cmds.append({
                    "frame": rec["frame_number"],
                    "ts": rec["timestamp"],
                    "channel": channel,
                    "raw_val": raw_val,
                    "direction": rec["direction"],
                })
            else:
                other_count += 1

        elif opcode == 0x40:
            poll_count += 1

        elif opcode == 0x00 and d["length"] == 0:
            # Zero-length payload = ACK / status response
            ack_count += 1

        elif opcode == 0x01:
            # ACK / command-response from device (1-byte payload 0x01)
            ack_count += 1

        elif d["length"] >= 0x1c:
            # 28-byte (or longer) level response
            level_resp_count += 1

        else:
            other_count += 1

    # --- Print gain commands ---
    print(f"{'='*70}")
    print(f"  INPUT GAIN COMMANDS (opcode 0x34)")
    print(f"{'='*70}")
    print(f"{'Packet':>8}  {'Timestamp':>12}  {'Channel':>7}  {'RawValue':>9}  Dir")
    print(f"{'-'*8}  {'-'*12}  {'-'*7}  {'-'*9}  ---")
    for g in gain_cmds:
        print(f"{g['frame']:>8}  {g['ts']:>12}  {g['channel']:>7}  {g['raw_val']:>9}  {g['direction']}")

    print()
    print(f"{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Total gain (0x34) packets : {len(gain_cmds)}")

    if gain_cmds:
        vals = [g["raw_val"] for g in gain_cmds]
        unique_sorted = sorted(set(vals))
        print(f"  Min raw value             : {min(vals)}")
        print(f"  Max raw value             : {max(vals)}")
        print(f"  All unique values (asc)   : {unique_sorted}")
        channels = sorted(set(g["channel"] for g in gain_cmds))
        print(f"  Channels seen             : {channels}")

    print()
    print(f"  Non-gain packet breakdown:")
    print(f"    Poll packets (0x40)     : {poll_count}")
    print(f"    ACK/empty packets       : {ack_count}")
    print(f"    Level response packets  : {level_resp_count}")
    print(f"    Other / unrecognised    : {other_count}")
    total_hid = len(records)
    print(f"    ─────────────────────────")
    print(f"    Total HID-64 packets    : {total_hid}")

    # Sanity: dump all unique opcodes seen for reference
    opcodes_seen = {}
    for rec in records:
        d = rec["decoded"]
        if d and d["opcode"] is not None:
            op = d["opcode"]
            opcodes_seen[op] = opcodes_seen.get(op, 0) + 1
    print()
    print(f"  All opcodes observed:")
    for op, cnt in sorted(opcodes_seen.items()):
        print(f"    0x{op:02x}  → {cnt} packet(s)")


if __name__ == "__main__":
    main()
