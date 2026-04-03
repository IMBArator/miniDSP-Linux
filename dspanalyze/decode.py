"""Decode raw HID packets into structured protocol commands.

Pipeline: RawPacket -> ParsedFrame -> DecodedCommand
Uses minidsp.protocol for frame parsing and the TOML config for field extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dspanalyze.config import ProtocolConfig, FieldDef, convert_value
from dspanalyze.readers import RawPacket
from minidsp.protocol import parse_frame


@dataclass
class ParsedFrame:
    """A validated miniDSP protocol frame extracted from a HID report."""
    raw: RawPacket
    src: int
    dst: int
    length: int
    payload: bytes
    checksum_valid: bool


@dataclass
class DecodedCommand:
    """A fully decoded protocol command with field values."""
    frame: ParsedFrame
    opcode: int
    opcode_name: str
    direction: str          # "out" or "in"
    verified: bool          # whether this opcode is capture-verified
    is_known: bool          # whether config has a definition for this opcode
    fields: dict[str, int | str | bytes] = field(default_factory=dict)
    human_fields: dict[str, str] = field(default_factory=dict)
    description: str = ""


def parse_raw_packet(pkt: RawPacket) -> ParsedFrame | None:
    """Parse a RawPacket into a validated ParsedFrame.

    Uses minidsp.protocol.parse_frame for the actual frame validation,
    but also handles the case where we want to inspect invalid frames.
    """
    data = pkt.hid_data
    result = parse_frame(data)

    if result is not None:
        src, dst, length, payload = result
        return ParsedFrame(
            raw=pkt,
            src=src,
            dst=dst,
            length=length,
            payload=payload,
            checksum_valid=True,
        )

    # Try to extract what we can from an invalid frame
    if len(data) >= 5 and data[0] == 0x10 and data[1] == 0x02:
        src = data[2]
        dst = data[3]
        length = data[4]
        payload = data[5:5 + length] if 5 + length <= len(data) else data[5:]
        return ParsedFrame(
            raw=pkt,
            src=src,
            dst=dst,
            length=length,
            payload=payload,
            checksum_valid=False,
        )

    return None


def _extract_field_value(payload: bytes, fdef: FieldDef) -> int | str | bytes:
    """Extract a raw value from payload bytes according to field definition."""
    offset = fdef.offset
    size = fdef.size

    if offset + size > len(payload):
        return 0

    if fdef.format == "ascii":
        raw_bytes = payload[offset:offset + size]
        return raw_bytes.decode("ascii", errors="replace").rstrip(" \x00")

    if fdef.format == "hex":
        return payload[offset:offset + size]

    if size == 1:
        return payload[offset]
    elif size == 2:
        # Little-endian uint16
        return payload[offset] + payload[offset + 1] * 256
    else:
        return payload[offset:offset + size]


def decode_frame(frame: ParsedFrame, config: ProtocolConfig) -> DecodedCommand:
    """Decode a ParsedFrame into a DecodedCommand using protocol config."""
    payload = frame.payload
    opcode = payload[0] if len(payload) > 0 else 0xFF

    odef = config.opcodes.get(opcode)
    direction = frame.raw.direction

    if odef is None:
        return DecodedCommand(
            frame=frame,
            opcode=opcode,
            opcode_name=f"unknown_0x{opcode:02x}",
            direction=direction,
            verified=False,
            is_known=False,
            description=f"Unknown opcode 0x{opcode:02x}",
        )

    # Pick appropriate field list based on direction
    if direction == "out":
        field_defs = odef.request_fields
    else:
        field_defs = odef.response_fields
    # Fallback: if no fields for this direction, try the other —
    # but only if the payload is large enough to actually contain those fields
    if not field_defs:
        alt_fields = odef.response_fields if direction == "out" else odef.request_fields
        if alt_fields:
            max_end = max(f.offset + f.size for f in alt_fields)
            if max_end <= len(payload):
                field_defs = alt_fields

    # Extract field values
    fields: dict[str, int | str | bytes] = {}
    human_fields: dict[str, str] = {}

    for fdef in field_defs:
        raw_val = _extract_field_value(payload, fdef)
        fields[fdef.name] = raw_val
        # Convert to human-readable form
        if isinstance(raw_val, (int, float)):
            human_fields[fdef.name] = convert_value(raw_val, fdef.format, config)
        elif isinstance(raw_val, str):
            human_fields[fdef.name] = raw_val
        elif isinstance(raw_val, bytes):
            human_fields[fdef.name] = raw_val.hex()

    return DecodedCommand(
        frame=frame,
        opcode=opcode,
        opcode_name=odef.name,
        direction=direction,
        verified=odef.verified,
        is_known=True,
        fields=fields,
        human_fields=human_fields,
        description=odef.description,
    )


def decode_packets(packets: list[RawPacket], config: ProtocolConfig) -> list[DecodedCommand]:
    """Decode a list of raw packets into decoded commands.

    Packets that fail frame parsing are included as unknown commands
    so nothing is silently dropped.
    """
    commands: list[DecodedCommand] = []

    for pkt in packets:
        frame = parse_raw_packet(pkt)
        if frame is None:
            # Include as an unparseable entry
            commands.append(DecodedCommand(
                frame=ParsedFrame(
                    raw=pkt, src=0, dst=0, length=0,
                    payload=b"", checksum_valid=False,
                ),
                opcode=0xFF,
                opcode_name="unparseable",
                direction=pkt.direction,
                verified=False,
                is_known=False,
                description="Could not parse frame from HID data",
            ))
            continue

        commands.append(decode_frame(frame, config))

    return commands
