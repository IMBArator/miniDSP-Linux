#!/usr/bin/env python3
"""
Extract HID interrupt transfer payloads from a Wireshark text export.
Looks for URB_INTERRUPT packets on endpoints 0x02 (OUT) and 0x81 (IN)
and decodes the miniDSP framing:
  10 02 [SRC] [DST] [LEN] [PAYLOAD...] 10 03 [CHK]
"""

import re
import sys

CAPTURE_FILE = "/home/max/src/miniDSP-Linux/miniDSP Capture - Start and close windows edit software.txt"

def decode_frame(raw_hex):
    """
    Decode the miniDSP frame from 64-byte HID payload hex string.
    Returns dict with frame fields or None if not a valid frame.
    """
    try:
        data = bytes.fromhex(raw_hex)
    except ValueError:
        return None

    if len(data) < 6:
        return None

    # Frame starts with 10 02
    if data[0] != 0x10 or data[1] != 0x02:
        return {"raw": raw_hex, "note": f"No 10 02 header (starts with {data[0]:02x} {data[1]:02x})"}

    src = data[2]
    dst = data[3]
    length = data[4]

    # Payload is length bytes starting at offset 5
    payload = data[5:5 + length]

    # After payload: expect 10 03 [CHK]
    trailer_start = 5 + length
    if trailer_start + 2 < len(data):
        t0 = data[trailer_start]
        t1 = data[trailer_start + 1]
        chk = data[trailer_start + 2] if trailer_start + 2 < len(data) else None
    else:
        t0 = t1 = chk = None

    # Compute expected checksum: XOR of length byte and all payload bytes
    expected_chk = length
    for b in payload:
        expected_chk ^= b

    opcode = payload[0] if len(payload) > 0 else None
    payload_hex = payload.hex() if payload else ""

    trailer_ok = (t0 == 0x10 and t1 == 0x03)
    chk_ok = (chk == expected_chk) if chk is not None else False

    return {
        "src": src,
        "dst": dst,
        "length": length,
        "opcode": opcode,
        "payload_hex": payload_hex,
        "trailer_ok": trailer_ok,
        "chk": chk,
        "expected_chk": expected_chk,
        "chk_ok": chk_ok,
        "raw": raw_hex,
    }

def parse_capture(filepath):
    packets = []

    # Regex for the summary line at the top of each packet block
    # Format: "     NNN  TIMESTAMP  SOURCE  DEST  PROTO  LEN  INFO"
    pkt_header_re = re.compile(
        r'^\s+(\d+)\s+([\d.]+)\s+(\S+)\s+(\S+)\s+\S+\s+\d+\s+(.*?)\s*$'
    )

    with open(filepath, 'r', errors='replace') as f:
        lines = f.readlines()

    current_pkt = None
    i = 0
    while i < len(lines):
        line = lines[i]

        # Detect packet header line (summary table row)
        m = pkt_header_re.match(line)
        if m:
            pkt_num = int(m.group(1))
            timestamp = m.group(2)
            source = m.group(3)
            dest = m.group(4)
            info = m.group(5)
            current_pkt = {
                "num": pkt_num,
                "time": timestamp,
                "source": source,
                "dest": dest,
                "info": info,
                "endpoint": None,
                "direction": None,
                "hid_hex": None,
            }
            i += 1
            continue

        if current_pkt is not None:
            # Look for Endpoint line
            ep_m = re.match(r'\s+Endpoint:\s+(0x[0-9a-fA-F]+),\s+Direction:\s+(\w+)', line)
            if ep_m:
                current_pkt["endpoint"] = ep_m.group(1).lower()
                current_pkt["direction"] = ep_m.group(2).upper()
                i += 1
                continue

            # Look for HID Data line (contains the hex payload on the same line after the colon)
            hid_m = re.match(r'\s*(?:HID Data|Leftover Capture Data):\s*([0-9a-fA-F]+)', line)
            if hid_m:
                current_pkt["hid_hex"] = hid_m.group(1).lower()
                # If the hex spans multiple lines (continuation lines have only hex)
                j = i + 1
                while j < len(lines):
                    cont = lines[j].strip()
                    if re.match(r'^[0-9a-fA-F]+$', cont):
                        current_pkt["hid_hex"] += cont.lower()
                        j += 1
                    else:
                        break
                i = j
                # Commit this packet if it's a URB_INTERRUPT with HID data
                if (current_pkt["hid_hex"] and
                        "URB_INTERRUPT" in current_pkt.get("info", "")):
                    packets.append(dict(current_pkt))
                continue

        i += 1

    return packets

def main():
    packets = parse_capture(CAPTURE_FILE)

    print(f"{'='*100}")
    print(f"Total HID URB_INTERRUPT packets with data: {len(packets)}")
    print(f"{'='*100}\n")

    for pkt in packets:
        num = pkt["num"]
        ts = pkt["time"]
        src = pkt["source"]
        dst = pkt["dest"]
        info = pkt["info"]
        ep = pkt["endpoint"] or "?"
        direction = pkt["direction"] or "?"
        hid_hex = pkt["hid_hex"]

        # Determine direction label from endpoint
        if ep == "0x02" or direction == "OUT":
            dir_label = "OUT (host→device)"
        elif ep == "0x81" or direction == "IN":
            dir_label = "IN  (device→host)"
        else:
            dir_label = f"{direction} ep={ep}"

        # Pretty-print the 64-byte payload in groups of 8
        raw = hid_hex
        grouped = []
        for g in range(0, len(raw), 2):
            grouped.append(raw[g:g+2])
        formatted_rows = []
        for row in range(0, len(grouped), 8):
            formatted_rows.append(" ".join(grouped[row:row+8]))
        payload_display = "\n         ".join(formatted_rows)

        print(f"Pkt #{num:5d}  t={ts}  {dir_label}")
        print(f"  Info   : {info}")
        print(f"  Payload: {payload_display}")

        # Decode the frame
        frame = decode_frame(hid_hex)
        if frame:
            if "note" in frame:
                print(f"  Frame  : {frame['note']}")
            else:
                opcode_str = f"0x{frame['opcode']:02x}" if frame['opcode'] is not None else "N/A"
                chk_str = f"0x{frame['chk']:02x}" if frame['chk'] is not None else "N/A"
                exp_str = f"0x{frame['expected_chk']:02x}"
                chk_ok = "OK" if frame["chk_ok"] else f"BAD (expected {exp_str})"
                trailer = "OK" if frame["trailer_ok"] else "MISSING/BAD"
                print(f"  Frame  : src=0x{frame['src']:02x} dst=0x{frame['dst']:02x} "
                      f"len={frame['length']}  opcode={opcode_str}  "
                      f"trailer={trailer}  chk={chk_str} [{chk_ok}]")
                print(f"  PldHex : {frame['payload_hex']}")
        print()

if __name__ == "__main__":
    main()
