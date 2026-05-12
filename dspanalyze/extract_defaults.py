"""Extract factory default parameter values from a preset-load capture.

Reads a USB capture of a preset load (typically the F00 factory preset),
stitches the 9 × 50-byte config pages back into the 450-byte config blob,
runs the protocol parser, and emits a TOML file.

Output is the raw protocol form (matches ``minidsp.protocol.parse_preset_params``)
plus the three footer parameters not currently exposed by the parser
(test tone mode, sine freq index, delay display unit). Consumers can use
the converters in ``minidsp.protocol`` to derive human-friendly values.
"""

from __future__ import annotations

from pathlib import Path

import tomli_w

from dspanalyze.config import load_config
from dspanalyze.decode import decode_packets
from dspanalyze.readers import read_capture

# Config page response: payload = [0x24, page_idx, 50 bytes]
_CONFIG_PAGE_OPCODE = 0x24
_CONFIG_PAGE_DATA_SIZE = 50
_CONFIG_PAGES_EXPECTED = 9
_CONFIG_BLOB_SIZE = _CONFIG_PAGES_EXPECTED * _CONFIG_PAGE_DATA_SIZE  # 450

# Footer-byte offsets that parse_preset_params doesn't currently return.
# Documented in analysis/protocol.md "Preset Structure".
_TEST_TONE_MODE_OFFSET = 420
_TEST_TONE_FREQ_OFFSET = 422
_DELAY_UNIT_OFFSET = 424


class ExtractDefaultsError(RuntimeError):
    pass


def stitch_config_pages(capture_path: Path) -> bytes:
    """Decode capture, grab the 9 config_page responses, return the 450-byte blob.

    If the capture contains more than one full set of pages (e.g. multiple
    preset loads), the LAST complete sequence wins — matching what the device
    ends up showing the host.
    """
    config = load_config()
    packets = read_capture(str(capture_path))
    if not packets:
        raise ExtractDefaultsError(f"No HID packets found in {capture_path}")

    commands = decode_packets(packets, config)

    # Collect (page_idx, data) tuples in capture order.
    pages: list[tuple[int, bytes]] = []
    for cmd in commands:
        if cmd.opcode != _CONFIG_PAGE_OPCODE or cmd.direction != "in":
            continue
        payload = cmd.frame.payload
        if len(payload) < 2 + _CONFIG_PAGE_DATA_SIZE:
            continue
        page_idx = payload[1]
        data = bytes(payload[2:2 + _CONFIG_PAGE_DATA_SIZE])
        pages.append((page_idx, data))

    if len(pages) < _CONFIG_PAGES_EXPECTED:
        raise ExtractDefaultsError(
            f"Capture contains only {len(pages)} config_page responses, "
            f"need {_CONFIG_PAGES_EXPECTED}"
        )

    # Take the LAST 9 pages by capture order, then reorder by page index.
    last_set = pages[-_CONFIG_PAGES_EXPECTED:]
    indices = [p for p, _ in last_set]
    if sorted(indices) != list(range(_CONFIG_PAGES_EXPECTED)):
        raise ExtractDefaultsError(
            f"Last {_CONFIG_PAGES_EXPECTED} config pages have unexpected indices: "
            f"{indices} (need 0..{_CONFIG_PAGES_EXPECTED - 1})"
        )
    last_set.sort(key=lambda t: t[0])
    blob = b"".join(data for _, data in last_set)

    if len(blob) != _CONFIG_BLOB_SIZE:
        raise ExtractDefaultsError(
            f"Stitched config blob is {len(blob)} bytes, expected {_CONFIG_BLOB_SIZE}"
        )
    return blob


def build_defaults_dict(config_blob: bytes, source_capture: str) -> dict:
    """Build the factory_defaults structure from a 450-byte config blob.

    Returns parse_preset_params output plus footer-byte parameters
    (test_tone_mode, test_tone_freq, delay_unit) and a metadata block.

    Within each table, scalar/array fields come before arrays-of-tables —
    required for valid TOML serialization (a table can't have scalar keys
    after an array-of-tables sub-section).
    """
    from minidsp.protocol import parse_preset_params

    if len(config_blob) != _CONFIG_BLOB_SIZE:
        raise ExtractDefaultsError(
            f"config_blob must be {_CONFIG_BLOB_SIZE} bytes, got {len(config_blob)}"
        )

    parsed = parse_preset_params(config_blob)
    if parsed is None:
        raise ExtractDefaultsError("parse_preset_params returned None")

    # Reorder so scalars/scalar-arrays precede arrays-of-tables (TOML rule).
    # parse_preset_params returns: names, gains, mutes, phases, link_flags,
    # routings, gates, delays, crossovers, compressors, peqs.
    params = {
        "names":            parsed["names"],
        "gains":            parsed["gains"],
        "mutes":            parsed["mutes"],
        "phases":           parsed["phases"],
        "link_flags":       parsed["link_flags"],
        "routings":         parsed["routings"],
        "delays":           parsed["delays"],
        "test_tone_mode":   config_blob[_TEST_TONE_MODE_OFFSET],
        "test_tone_freq":   config_blob[_TEST_TONE_FREQ_OFFSET],
        "delay_unit":       config_blob[_DELAY_UNIT_OFFSET],
        "gates":            parsed["gates"],
        "crossovers":       parsed["crossovers"],
        "compressors":      parsed["compressors"],
        "peqs":             [
            # channel_bypass (scalar) must precede bands (array of tables).
            {"channel_bypass": p["channel_bypass"], "bands": p["bands"]}
            for p in parsed["peqs"]
        ],
    }

    return {
        "schema_version": 1,
        "preset": "F00",
        "preset_name": "Default Preset",
        "source_capture": source_capture,
        "encoding": "raw",
        "channels": ["InA", "InB", "InC", "InD", "Out1", "Out2", "Out3", "Out4"],
        "params": params,
    }


def extract_defaults(capture_path: Path, output_path: Path) -> dict:
    """End-to-end extraction. Returns the dict that was written."""
    blob = stitch_config_pages(capture_path)
    data = build_defaults_dict(blob, source_capture=capture_path.name)
    output_path.write_bytes(tomli_w.dumps(data).encode("utf-8"))
    return data
