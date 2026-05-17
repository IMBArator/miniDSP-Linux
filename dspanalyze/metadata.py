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
    """Return the ``.meta.toml`` sidecar path for a capture file.

    The sidecar is co-located with the capture and named by appending
    ``.meta.toml`` to the original filename — e.g. ``foo.pcapng`` →
    ``foo.pcapng.meta.toml``.

    Args:
        capture_path: Path to a capture file (``.pcapng`` or ``.txt``).

    Returns:
        Path to the sidecar file. Existence is not checked.
    """
    p = Path(capture_path)
    return p.with_suffix(p.suffix + ".meta.toml")


def generate_metadata(
    capture_path: str | Path,
    commands: list[DecodedCommand],
    description: str = "",
    notes: str = "",
) -> dict:
    """Build the sidecar metadata dict from a list of decoded commands.

    Computes capture-level statistics (packet counts, opcode tallies, duration,
    checksum/unknown-opcode flags) and combines them with the user-supplied
    description/notes into a TOML-serializable structure.

    Args:
        capture_path: Path to the source capture file. Only the filename and
            suffix are read for the ``capture`` section; the file is not opened.
        commands: Decoded commands produced by :mod:`dspanalyze.decode`.
        description: Free-text feature label (typically what was captured).
        notes: Free-text additional notes.

    Returns:
        Dict with three top-level sections:

        - ``'capture'``: ``file`` (basename), ``format`` (extension without dot).
        - ``'description'``: ``feature``, ``notes`` (verbatim inputs).
        - ``'analysis'``: ``packet_count``, ``out_packets``, ``in_packets``,
            ``duration_seconds`` (rounded to 2 dp), ``opcodes_seen`` (sorted hex
            strings), ``opcode_counts`` (dict, descending frequency),
            ``has_unknown_opcodes``, ``has_checksum_errors``, and
            ``last_analyzed`` (ISO 8601 timestamp, seconds precision).
    """
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
    """Generate the metadata dict and persist it to the sidecar file on disk.

    If the sidecar already exists, the existing ``description.feature`` and
    ``description.notes`` fields are preserved when the caller passes empty
    strings — this lets re-analysis update statistics without clobbering
    human-authored prose. All ``analysis`` fields are always overwritten.

    Args:
        capture_path: Path to the capture file; the sidecar path is derived
            via :func:`meta_path_for`.
        commands: Decoded commands (forwarded to :func:`generate_metadata`).
        description: Feature label to write. Empty string means "keep the
            existing value if any".
        notes: Notes to write. Empty string means "keep the existing value
            if any".

    Returns:
        Path to the written sidecar file.

    Side effects:
        Creates or overwrites the ``.meta.toml`` file next to the capture.
    """
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
