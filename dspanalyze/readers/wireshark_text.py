"""Parse Wireshark text export files into RawPacket sequences.

Ported from analysis/extract_hid.py — handles the specific text export format
produced by Wireshark's "File > Export Packet Dissections > As Plain Text".
"""

from __future__ import annotations

import re
from pathlib import Path

from dspanalyze.readers import RawPacket


# Regex for the packet summary line at the top of each packet block
# Format: "     NNN  TIMESTAMP  SOURCE  DEST  PROTO  LEN  INFO"
_PKT_HEADER_RE = re.compile(
    r"^\s+(\d+)\s+([\d.]+)\s+(\S+)\s+(\S+)\s+\S+\s+\d+\s+(.*?)\s*$"
)

# Regex for endpoint line within a packet
_ENDPOINT_RE = re.compile(
    r"\s+Endpoint:\s+(0x[0-9a-fA-F]+),\s+Direction:\s+(\w+)"
)

# Regex for HID data line (may be labeled "HID Data" or "Leftover Capture Data")
_HID_DATA_RE = re.compile(
    r"\s*(?:HID Data|Leftover Capture Data):\s*([0-9a-fA-F]+)"
)

# Continuation lines are just hex digits
_HEX_CONT_RE = re.compile(r"^[0-9a-fA-F]+$")


def read_wireshark_text(filepath: str | Path) -> list[RawPacket]:
    """Parse a Wireshark text export and return HID interrupt packets.

    Extracts URB_INTERRUPT packets that contain HID data, determines
    direction from endpoint (0x02=OUT, 0x81=IN), and returns structured
    RawPacket instances.
    """
    filepath = Path(filepath)
    with open(filepath, "r", errors="replace") as f:
        lines = f.readlines()

    packets: list[RawPacket] = []
    current: dict | None = None
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check for packet header (summary table row)
        m = _PKT_HEADER_RE.match(line)
        if m:
            current = {
                "num": int(m.group(1)),
                "time": float(m.group(2)),
                "info": m.group(5),
                "endpoint": None,
                "direction": None,
                "hid_hex": None,
            }
            i += 1
            continue

        if current is not None:
            # Look for endpoint line
            ep_m = _ENDPOINT_RE.match(line)
            if ep_m:
                current["endpoint"] = int(ep_m.group(1), 16)
                current["direction"] = ep_m.group(2).upper()
                i += 1
                continue

            # Look for HID data line
            hid_m = _HID_DATA_RE.match(line)
            if hid_m:
                hex_str = hid_m.group(1).lower()
                # Consume continuation lines (pure hex)
                j = i + 1
                while j < len(lines):
                    cont = lines[j].strip()
                    if _HEX_CONT_RE.match(cont):
                        hex_str += cont.lower()
                        j += 1
                    else:
                        break
                i = j

                # Only keep URB_INTERRUPT packets with HID data
                if "URB_INTERRUPT" in current.get("info", "") and hex_str:
                    current["hid_hex"] = hex_str
                    ep = current["endpoint"] or 0
                    if ep == 0x02 or current["direction"] == "OUT":
                        direction = "out"
                        endpoint = 0x02
                    elif ep == 0x81 or current["direction"] == "IN":
                        direction = "in"
                        endpoint = 0x81
                    else:
                        direction = "out" if "OUT" in current.get("info", "") else "in"
                        endpoint = ep

                    try:
                        hid_data = bytes.fromhex(hex_str)
                    except ValueError:
                        i += 1
                        continue

                    packets.append(RawPacket(
                        frame_number=current["num"],
                        timestamp=current["time"],
                        direction=direction,
                        endpoint=endpoint,
                        hid_data=hid_data,
                    ))
                continue

        i += 1

    return packets
