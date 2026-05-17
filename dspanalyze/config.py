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
    """Definition of a single field within an opcode payload.

    Attributes:
        name: Field identifier (e.g. ``"channel"``, ``"value"``).
        offset: Byte offset within the payload (after the opcode byte).
        size: Field width in bytes (1=uint8, 2=uint16 LE, >2=raw bytes/ASCII).
        format: Value format name for :func:`convert_value` dispatch
            (e.g. ``"uint8"``, ``"gain_raw"``, ``"freq_log"``, ``"ascii"``).
        note: Optional human-readable annotation from the config TOML.
    """
    name: str
    offset: int
    size: int
    format: str
    note: str = ""


@dataclass
class OpcodeDef:
    """Definition of a protocol opcode loaded from ``protocol_config.toml``.

    Attributes:
        code: Opcode byte value (e.g. ``0x34`` for gain).
        name: Short identifier string (e.g. ``"gain"``).
        direction: Expected transfer direction — ``"out"`` (host→device),
            ``"in"`` (device→host), or ``"both"``.
        description: Human-readable summary of what the opcode does.
        verified: ``True`` if the opcode has been confirmed against a real
            device capture.
        request_fields: Field definitions for host→device payloads.
        response_fields: Field definitions for device→host payloads.
    """
    code: int
    name: str
    direction: str
    description: str
    verified: bool = False
    request_fields: list[FieldDef] = field(default_factory=list)
    response_fields: list[FieldDef] = field(default_factory=list)


@dataclass
class ProtocolConfig:
    """Parsed protocol configuration loaded from ``protocol_config.toml``.

    Attributes:
        device: Raw ``[device]`` TOML table (VID, PID, report size).
        frame: Raw ``[frame]`` TOML table (STX/ETX bytes, structure).
        noise: Raw ``[noise]`` TOML table (known noise opcode patterns).
        opcodes: Map of opcode byte → :class:`OpcodeDef`.
        formats: Raw ``[formats]`` TOML tables (enum/bitmask value maps
            used by :func:`convert_value`).
    """
    device: dict
    frame: dict
    noise: dict
    opcodes: dict[int, OpcodeDef]
    formats: dict[str, dict]


def load_config(path: Path | None = None) -> ProtocolConfig:
    """Load and parse the protocol config TOML file.

    Args:
        path: Path to ``protocol_config.toml``. Defaults to the file bundled
            alongside this module (``dspanalyze/protocol_config.toml``).

    Returns:
        Populated :class:`ProtocolConfig` with all opcodes and formats parsed.
    """
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
    """Parse a TOML field dict into a sorted list of :class:`FieldDef` objects.

    Used by :func:`load_protocol_config` when reading ``request_fields`` and
    ``response_fields`` sub-tables in ``protocol_config.toml``. See that file
    for the canonical schema.

    Args:
        fields_dict: Dict mapping field name → spec dict. Each spec must be a
            ``dict`` with at least an ``offset`` key (``int``, byte offset
            into the frame payload). Optional keys: ``size`` (default ``1``,
            in bytes), ``format`` (default ``"hex"`` — name of a converter
            from the ``[formats]`` table or a built-in like ``"uint16le"``,
            ``"ascii"``), and ``note`` (default ``""``, free-text comment).

    Returns:
        :class:`FieldDef` list sorted ascending by ``offset``.

    Note:
        Entries whose spec is not a ``dict``, or whose dict lacks an
        ``offset`` key, are silently skipped. This lets the TOML schema use
        scalar values for documentation/section dividers without breaking the
        parser, but it also means a typo'd ``offest:`` will be discarded —
        verify field counts after editing the TOML.
    """
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
    """Convert a raw integer value to a human-readable string using a named format.

    Format dispatch order: hard-coded formats first (``channel``,
    ``gain_raw``, ``peq_gain``, ``freq_log``, ``q_log``, ``level_uint16``),
    then TOML-defined enum/bitmask formats, then generic types
    (``uint8``, ``uint16le``, ``ascii``, ``hex``).

    Args:
        raw_value: Raw integer (or bytes for ``hex``/``ascii`` formats).
        fmt: Format name string from the :class:`FieldDef` or caller.
        config: Loaded protocol config — provides the ``formats`` table for
            enum and bitmask lookups.

    Returns:
        Human-readable string representation. Falls back to ``str(raw_value)``
        for unrecognised format names.
    """
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
