"""Load protocol_config.toml and provide value format converters."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from minidsp.protocol import (
    CHANNEL_NAMES,
    freq_raw_to_hz,
    level_uint16_to_dbu,
    peq_raw_to_gain,
    peq_raw_to_q,
    raw_to_db,
)


@dataclass
class FieldDef:
    """Definition of a single field within an opcode payload."""
    name: str
    offset: int
    size: int
    format: str
    note: str = ""


@dataclass
class OpcodeDef:
    """Definition of a protocol opcode."""
    code: int
    name: str
    direction: str
    description: str
    verified: bool = False
    request_fields: list[FieldDef] = field(default_factory=list)
    response_fields: list[FieldDef] = field(default_factory=list)


@dataclass
class ProtocolConfig:
    """Parsed protocol configuration."""
    device: dict
    frame: dict
    noise: dict
    opcodes: dict[int, OpcodeDef]
    formats: dict[str, dict]


def load_config(path: Path | None = None) -> ProtocolConfig:
    """Load and parse the protocol config TOML file."""
    if path is None:
        path = Path(__file__).parent / "protocol_config.toml"

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    opcodes: dict[int, OpcodeDef] = {}
    for key, val in raw.get("opcodes", {}).items():
        code = int(key, 16)
        odef = OpcodeDef(
            code=code,
            name=val.get("name", f"unknown_{code:02x}"),
            direction=val.get("direction", "unknown"),
            description=val.get("description", ""),
            verified=val.get("verified", False),
        )
        # Parse field definitions from nested tables
        fields_section = val.get("fields", {})
        for group_name, group_fields in fields_section.items():
            parsed = _parse_fields(group_fields)
            if group_name == "request":
                odef.request_fields = parsed
            elif group_name == "response":
                odef.response_fields = parsed
        opcodes[code] = odef

    return ProtocolConfig(
        device=raw.get("device", {}),
        frame=raw.get("frame", {}),
        noise=raw.get("noise", {}),
        opcodes=opcodes,
        formats=raw.get("formats", {}),
    )


def _parse_fields(fields_dict: dict) -> list[FieldDef]:
    """Parse a dict of field name -> {offset, size, format, ...} into FieldDef list."""
    result = []
    for name, spec in fields_dict.items():
        if isinstance(spec, dict) and "offset" in spec:
            result.append(FieldDef(
                name=name,
                offset=spec["offset"],
                size=spec.get("size", 1),
                format=spec.get("format", "hex"),
                note=spec.get("note", ""),
            ))
    result.sort(key=lambda f: f.offset)
    return result


# ── Value format converters ──────────────────────────────


def convert_value(raw_value: int, fmt: str, config: ProtocolConfig) -> str:
    """Convert a raw integer value to human-readable string using a named format."""
    fmt_def = config.formats.get(fmt, {})
    fmt_type = fmt_def.get("type", "")

    if fmt == "channel":
        return CHANNEL_NAMES.get(raw_value, f"ch{raw_value}")

    if fmt == "gain_raw":
        return f"{raw_to_db(raw_value):.1f} dB (raw {raw_value})"

    if fmt == "peq_gain":
        return f"{peq_raw_to_gain(raw_value):+.1f} dB"

    if fmt == "freq_log":
        return f"{freq_raw_to_hz(raw_value):.0f} Hz (raw {raw_value})"

    if fmt == "q_log":
        return f"Q={peq_raw_to_q(raw_value):.2f} (raw {raw_value})"

    if fmt == "level_uint16":
        if raw_value == 0:
            return "silent"
        return f"{level_uint16_to_dbu(raw_value):.1f} dBu (raw {raw_value})"

    if fmt_type == "enum":
        values = fmt_def.get("values", {})
        return values.get(str(raw_value), f"0x{raw_value:02x}")

    if fmt_type == "bitmask":
        bits = fmt_def.get("bits", {})
        active = [label for bit_str, label in bits.items()
                  if raw_value & (1 << int(bit_str))]
        return "|".join(active) if active else "none"

    if fmt in ("uint8", "uint16le"):
        return str(raw_value)

    if fmt == "ascii":
        return repr(raw_value) if isinstance(raw_value, str) else str(raw_value)

    if fmt == "hex":
        if isinstance(raw_value, bytes):
            return raw_value.hex()
        return f"0x{raw_value:02x}"

    return str(raw_value)
