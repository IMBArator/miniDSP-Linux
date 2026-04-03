"""Read pcapng/pcap capture files via tshark subprocess.

Shells out to `tshark -T fields` to extract USB HID data — fast,
no Python pcap library needed, works with any Wireshark-supported format.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from dspanalyze.readers import RawPacket


def read_pcapng(filepath: str | Path) -> list[RawPacket]:
    """Extract HID interrupt packets from a pcapng/pcap file using tshark.

    Requires tshark to be installed and on PATH.
    """
    filepath = Path(filepath)
    tshark = shutil.which("tshark")
    if tshark is None:
        print("Error: tshark not found on PATH. Install Wireshark/tshark.",
              file=sys.stderr)
        sys.exit(1)

    # Extract fields: frame number, relative timestamp, endpoint, HID data
    # -Y filters for packets that actually contain HID data
    result = subprocess.run(
        [
            tshark, "-r", str(filepath),
            "-T", "fields",
            "-e", "frame.number",
            "-e", "frame.time_relative",
            "-e", "usb.endpoint_address",
            "-e", "usbhid.data",
            "-Y", "usbhid.data",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        print(f"tshark error: {result.stderr.strip()}", file=sys.stderr)
        return []

    packets: list[RawPacket] = []

    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue

        frame_num = int(parts[0])
        timestamp = float(parts[1])
        endpoint_str = parts[2]  # e.g. "0x02" or "0x81"
        hex_data = parts[3]

        try:
            endpoint = int(endpoint_str, 16)
        except ValueError:
            endpoint = 0

        if endpoint == 0x02:
            direction = "out"
        elif endpoint == 0x81:
            direction = "in"
        else:
            direction = "out" if endpoint < 0x80 else "in"

        try:
            hid_data = bytes.fromhex(hex_data)
        except ValueError:
            continue

        packets.append(RawPacket(
            frame_number=frame_num,
            timestamp=timestamp,
            direction=direction,
            endpoint=endpoint,
            hid_data=hid_data,
        ))

    return packets
