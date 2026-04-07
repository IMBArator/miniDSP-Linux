"""Compare config page reads within a capture to find parameter changes.

Extracts all 0x24 (config_page) responses, groups them into complete
9-page config reads, then diffs consecutive reads byte-by-byte.
Annotates changes with known field names from the config structure.
"""

from __future__ import annotations

from dspanalyze.decode import DecodedCommand

CONFIG_PAGES = 9
CONFIG_PAGE_SIZE = 50
OP_CONFIG_RESP = 0x24

# Known fields within the 450-byte stitched config blob.
# Each entry: (absolute_offset, size, name)
# Derived from protocol.md config structure documentation.

_INPUT_BLOCK_START = 16
_INPUT_BLOCK_SIZE = 24
_INPUT_FIELDS = [
    (0, 3, "name"),
    (10, 2, "gate_attack"),
    (12, 2, "gate_release"),
    (14, 2, "gate_hold"),
    (16, 2, "gate_threshold"),
    (18, 2, "gain"),
    (20, 1, "phase"),
    (22, 1, "link_flags"),
]

_OUTPUT_BLOCK_START = 112
_OUTPUT_BLOCK_SIZE = 74
_OUTPUT_FIELDS = [
    (0, 3, "name"),
    (6, 2, "unknown_param_a"),
    (8, 1, "routing_mask"),
    (9, 1, "padding"),
    (10, 2, "xover_hipass_freq"),
    (12, 2, "xover_lopass_freq"),
    (14, 1, "xover_hipass_slope"),
    (15, 1, "xover_lopass_slope"),
    (16, 42, "peq_bands"),   # 7 bands × 6 bytes = 42 bytes (unverified, needs PEQ capture)
    (58, 1, "comp_ratio"),
    (59, 1, "comp_knee"),
    (60, 2, "comp_attack"),
    (62, 2, "comp_release"),
    (64, 2, "comp_threshold"),
    (66, 2, "gain"),
    (68, 1, "phase"),
    (69, 1, "unknown_post_gain"),
    (70, 2, "delay"),
    (72, 1, "link_flags"),
]

_FOOTER_FIELDS = [
    (408, 2, "input_mute_bitmask"),
    (410, 2, "output_mute_bitmask"),
]

_CHANNEL_NAMES = ["InA", "InB", "InC", "InD", "Out1", "Out2", "Out3", "Out4"]


def _field_at(offset: int) -> str:
    """Map an absolute config offset to a human-readable field name."""
    # Preset header (first 16 bytes)
    if offset < _INPUT_BLOCK_START:
        if offset < 2:
            return "preset_marker"
        return f"preset_name[{offset - 2}]"

    # Input blocks (4 x 24 bytes starting at offset 16)
    if offset < _OUTPUT_BLOCK_START:
        rel = offset - _INPUT_BLOCK_START
        ch_idx = rel // _INPUT_BLOCK_SIZE
        within = rel % _INPUT_BLOCK_SIZE
        ch_name = _CHANNEL_NAMES[ch_idx] if ch_idx < 4 else f"input_{ch_idx}"
        for foff, fsize, fname in _INPUT_FIELDS:
            if foff <= within < foff + fsize:
                return f"{ch_name}.{fname}"
        return f"{ch_name}.byte_{within}"

    # Output blocks (4 x 74 bytes starting at offset 112)
    output_end = _OUTPUT_BLOCK_START + 4 * _OUTPUT_BLOCK_SIZE
    if offset < output_end:
        rel = offset - _OUTPUT_BLOCK_START
        ch_idx = rel // _OUTPUT_BLOCK_SIZE
        within = rel % _OUTPUT_BLOCK_SIZE
        ch_name = _CHANNEL_NAMES[4 + ch_idx] if ch_idx < 4 else f"output_{ch_idx}"
        for foff, fsize, fname in _OUTPUT_FIELDS:
            if foff <= within < foff + fsize:
                return f"{ch_name}.{fname}"
        return f"{ch_name}.byte_{within}"

    # Footer
    for foff, fsize, fname in _FOOTER_FIELDS:
        if foff <= offset < foff + fsize:
            return fname

    return f"footer_byte_{offset}"


def extract_config_reads(commands: list[DecodedCommand]) -> list[tuple[float, bytes]]:
    """Extract complete config reads from decoded commands.

    Returns list of (timestamp, 450-byte blob) for each complete read.
    """
    reads: list[tuple[float, bytes]] = []
    pages: dict[int, bytes] = {}
    first_ts = 0.0

    for cmd in commands:
        if cmd.opcode != OP_CONFIG_RESP or cmd.direction != "in":
            continue

        page_idx = cmd.fields.get("page", -1)
        page_data = cmd.fields.get("data", b"")
        if not isinstance(page_data, bytes) or len(page_data) != CONFIG_PAGE_SIZE:
            continue
        if not isinstance(page_idx, int) or not (0 <= page_idx < CONFIG_PAGES):
            continue

        if page_idx == 0:
            pages = {}
            first_ts = cmd.frame.raw.timestamp

        pages[page_idx] = page_data

        if len(pages) == CONFIG_PAGES:
            blob = b"".join(pages[i] for i in range(CONFIG_PAGES))
            reads.append((first_ts, blob))
            pages = {}

    return reads


def diff_config_reads(reads: list[tuple[float, bytes]]) -> str:
    """Diff consecutive config reads and return formatted output."""
    if len(reads) < 2:
        return f"Only {len(reads)} config read(s) found — need at least 2 to diff."

    lines: list[str] = []
    lines.append(f"Found {len(reads)} config reads in capture\n")

    for i in range(1, len(reads)):
        ts_a, blob_a = reads[i - 1]
        ts_b, blob_b = reads[i]
        lines.append(f"--- Read {i} ({ts_a:.3f}s)")
        lines.append(f"+++ Read {i + 1} ({ts_b:.3f}s)")

        diffs = []
        for offset in range(min(len(blob_a), len(blob_b))):
            if blob_a[offset] != blob_b[offset]:
                field = _field_at(offset)
                diffs.append((offset, blob_a[offset], blob_b[offset], field))

        if not diffs:
            lines.append("  (identical)\n")
            continue

        lines.append(f"  {len(diffs)} byte(s) changed:\n")
        lines.append(f"  {'Offset':>6}  {'Old':>5}  {'New':>5}  Field")
        lines.append(f"  {'──────':>6}  {'─────':>5}  {'─────':>5}  {'─' * 30}")
        for offset, old, new, field in diffs:
            lines.append(f"  {offset:>6}  0x{old:02x}   0x{new:02x}   {field}")
        lines.append("")

    return "\n".join(lines)
