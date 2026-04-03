"""Per-capture metadata sidecar files (.meta.toml).

Each capture gets a companion file storing analysis results,
description, and notes. Generated on first analysis, updated on re-analysis.
"""

from __future__ import annotations

import datetime
from collections import Counter
from pathlib import Path

import tomli_w

from dspanalyze.decode import DecodedCommand


def meta_path_for(capture_path: str | Path) -> Path:
    """Return the .meta.toml sidecar path for a capture file."""
    p = Path(capture_path)
    return p.with_suffix(p.suffix + ".meta.toml")


def generate_metadata(
    capture_path: str | Path,
    commands: list[DecodedCommand],
    description: str = "",
    notes: str = "",
) -> dict:
    """Build metadata dict from decoded commands."""
    capture_path = Path(capture_path)
    duration = 0.0
    if commands:
        times = [c.frame.raw.timestamp for c in commands]
        duration = max(times) - min(times)

    opcode_counts = Counter(f"0x{c.opcode:02x}" for c in commands)
    opcodes_seen = sorted(opcode_counts.keys())
    has_unknown = any(not c.is_known for c in commands)
    has_bad_chk = any(not c.frame.checksum_valid for c in commands)

    out_count = sum(1 for c in commands if c.direction == "out")
    in_count = sum(1 for c in commands if c.direction == "in")

    return {
        "capture": {
            "file": capture_path.name,
            "format": capture_path.suffix.lstrip("."),
        },
        "description": {
            "feature": description,
            "notes": notes,
        },
        "analysis": {
            "packet_count": len(commands),
            "out_packets": out_count,
            "in_packets": in_count,
            "duration_seconds": round(duration, 2),
            "opcodes_seen": opcodes_seen,
            "opcode_counts": dict(opcode_counts.most_common()),
            "has_unknown_opcodes": has_unknown,
            "has_checksum_errors": has_bad_chk,
            "last_analyzed": datetime.datetime.now().isoformat(timespec="seconds"),
        },
    }


def write_metadata(capture_path: str | Path, commands: list[DecodedCommand],
                   description: str = "", notes: str = "") -> Path:
    """Generate and write a .meta.toml sidecar file for a capture."""
    meta_file = meta_path_for(capture_path)
    meta = generate_metadata(capture_path, commands, description, notes)

    # Preserve existing description/notes if the file already exists
    if meta_file.exists():
        import tomllib
        with open(meta_file, "rb") as f:
            existing = tomllib.load(f)
        existing_desc = existing.get("description", {})
        if not description and existing_desc.get("feature"):
            meta["description"]["feature"] = existing_desc["feature"]
        if not notes and existing_desc.get("notes"):
            meta["description"]["notes"] = existing_desc["notes"]

    with open(meta_file, "wb") as f:
        tomli_w.dump(meta, f)

    return meta_file
