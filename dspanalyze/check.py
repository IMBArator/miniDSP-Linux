"""Protocol assertion framework — verify protocol knowledge against captures.

Each assertion is a named check that validates some property of the decoded
commands. Assertions can target all captures or specific file patterns.
This guards against regressions as we learn more about the protocol.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dspanalyze.decode import DecodedCommand


@dataclass
class Assertion:
    """A named protocol assertion."""
    name: str
    description: str
    capture_glob: str  # "*" for all captures, or a glob pattern
    check: Callable[[list[DecodedCommand]], tuple[bool, str]]
    # check returns (passed, detail_message)


@dataclass
class AssertionResult:
    """Result of running one assertion."""
    assertion: Assertion
    passed: bool
    detail: str


def matches_capture(assertion: Assertion, filepath: str | Path) -> bool:
    """Check if an assertion applies to a given capture file."""
    if assertion.capture_glob == "*":
        return True
    return fnmatch.fnmatch(Path(filepath).name, assertion.capture_glob)


# ── Assertion implementations ──────────────────────────────


def _check_checksums(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """All frames must have valid checksums."""
    bad = [c for c in commands if not c.frame.checksum_valid]
    if bad:
        frames = ", ".join(f"#{c.frame.raw.frame_number}" for c in bad[:5])
        return False, f"{len(bad)} checksum failures: {frames}"
    return True, f"all {len(commands)} checksums valid"


def _check_frame_structure(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """All packets must have parseable frame structure (STX/ETX present)."""
    unparseable = [c for c in commands if c.opcode_name == "unparseable"]
    if unparseable:
        frames = ", ".join(f"#{c.frame.raw.frame_number}" for c in unparseable[:5])
        return False, f"{len(unparseable)} unparseable frames: {frames}"
    return True, f"all {len(commands)} frames parseable"


def _check_gain_range(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """All gain commands (0x34) must have raw values in range 0-400."""
    gain_cmds = [c for c in commands if c.opcode == 0x34 and "value" in c.fields]
    if not gain_cmds:
        return True, "no gain commands found"
    out_of_range = [c for c in gain_cmds
                    if isinstance(c.fields["value"], int) and not (0 <= c.fields["value"] <= 400)]
    if out_of_range:
        vals = [c.fields["value"] for c in out_of_range[:5]]
        return False, f"{len(out_of_range)} gain values out of range: {vals}"
    return True, f"all {len(gain_cmds)} gain values in 0-400"


def _check_mute_values(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """All mute commands (0x35) must have state 0 or 1."""
    mute_cmds = [c for c in commands if c.opcode == 0x35 and "state" in c.fields]
    if not mute_cmds:
        return True, "no mute commands found"
    bad = [c for c in mute_cmds
           if isinstance(c.fields["state"], int) and c.fields["state"] not in (0, 1)]
    if bad:
        vals = [c.fields["state"] for c in bad[:5]]
        return False, f"{len(bad)} invalid mute states: {vals}"
    return True, f"all {len(mute_cmds)} mute states valid (0 or 1)"


def _check_channel_range(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Channel bytes in gain/mute commands must be 0-7."""
    relevant = [c for c in commands if c.opcode in (0x34, 0x35) and "channel" in c.fields]
    if not relevant:
        return True, "no gain/mute commands found"
    bad = [c for c in relevant
           if isinstance(c.fields["channel"], int) and not (0 <= c.fields["channel"] <= 7)]
    if bad:
        vals = [c.fields["channel"] for c in bad[:5]]
        return False, f"{len(bad)} invalid channel values: {vals}"
    return True, f"all {len(relevant)} channel values in 0-7"


def _check_ack_follows_write(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Write commands (gain, mute, link, activate) should be followed by ACK."""
    write_opcodes = {0x34, 0x35, 0x3b, 0x2a}
    missing_ack = 0
    total_writes = 0

    for i, cmd in enumerate(commands):
        if cmd.opcode in write_opcodes and cmd.direction == "in":
            # This is a device echo of the command — look for ACK after it
            total_writes += 1
            if i + 1 < len(commands) and commands[i + 1].opcode == 0x01:
                continue
            # Allow a gap of up to 3 packets (poll responses may interleave)
            found_ack = False
            for j in range(i + 1, min(i + 4, len(commands))):
                if commands[j].opcode == 0x01:
                    found_ack = True
                    break
            if not found_ack:
                missing_ack += 1

    if total_writes == 0:
        return True, "no write commands found"
    if missing_ack:
        return False, f"{missing_ack}/{total_writes} write commands missing ACK within 3 packets"
    return True, f"all {total_writes} write commands have ACK response"


def _check_startup_sequence(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Startup captures should begin with init(0x10) -> firmware(0x13) -> device_info(0x2c)."""
    # Get first few unique opcodes (skip duplicates from request/response pairs)
    seen_opcodes: list[int] = []
    for cmd in commands:
        if cmd.opcode not in seen_opcodes and cmd.opcode != 0x01:
            seen_opcodes.append(cmd.opcode)
        if len(seen_opcodes) >= 5:
            break

    expected_start = [0x10, 0x13, 0x2c, 0x22, 0x14]
    if seen_opcodes[:5] == expected_start:
        return True, "startup sequence matches: init->firmware->device_info->preset_header->preset_index"
    return False, f"expected {[f'0x{o:02x}' for o in expected_start]}, got {[f'0x{o:02x}' for o in seen_opcodes[:5]]}"


def _check_config_pages_complete(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Config reads (0x24 responses) should cover all 9 pages (0-8)."""
    pages = {c.fields["page"] for c in commands
             if c.opcode == 0x24 and "page" in c.fields}
    expected = set(range(9))
    if not pages:
        return True, "no config page responses found"
    missing = expected - pages
    if missing:
        return False, f"missing config pages: {sorted(missing)}"
    return True, f"all 9 config pages present (0-8)"


def _check_gain_calibration_0db(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Gain sweep to 0 dB should end at raw 280."""
    gain_cmds = [c for c in commands if c.opcode == 0x34 and "value" in c.fields]
    if not gain_cmds:
        return True, "no gain commands found"
    max_val = max(c.fields["value"] for c in gain_cmds if isinstance(c.fields["value"], int))
    if max_val == 280:
        return True, f"max gain raw value = 280 (0.0 dB)"
    return False, f"expected max gain = 280 (0.0 dB), got {max_val}"


def _check_gain_calibration_12db(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Gain sweep to +12 dB should end at raw 400."""
    gain_cmds = [c for c in commands if c.opcode == 0x34 and "value" in c.fields]
    if not gain_cmds:
        return True, "no gain commands found"
    max_val = max(c.fields["value"] for c in gain_cmds if isinstance(c.fields["value"], int))
    if max_val == 400:
        return True, f"max gain raw value = 400 (+12.0 dB)"
    return False, f"expected max gain = 400 (+12.0 dB), got {max_val}"


def _check_no_unknown_opcodes(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """All opcodes should be recognized by the protocol config."""
    unknowns = {c.opcode for c in commands if not c.is_known}
    if unknowns:
        ops = sorted(f"0x{o:02x}" for o in unknowns)
        return False, f"unknown opcodes: {', '.join(ops)}"
    return True, "all opcodes recognized"


def _check_preset_names_30(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Preset name reads should cover all 30 slots."""
    name_cmds = [c for c in commands if c.opcode == 0x29 and "slot" in c.fields]
    if not name_cmds:
        return True, "no preset name commands found"
    slots = {c.fields["slot"] for c in name_cmds if isinstance(c.fields["slot"], int)}
    expected = set(range(30))
    missing = expected - slots
    if missing:
        return False, f"missing preset slots: {sorted(missing)}"
    return True, f"all 30 preset name slots read"


# ── Assertion registry ──────────────────────────────


ASSERTIONS: list[Assertion] = [
    Assertion("checksum_valid", "All frames have valid XOR checksums", "*",
              _check_checksums),
    Assertion("frame_structure", "All packets have parseable frame structure", "*",
              _check_frame_structure),
    Assertion("no_unknown_opcodes", "All opcodes are recognized by the config", "*",
              _check_no_unknown_opcodes),
    Assertion("gain_range_0_400", "All gain values (0x34) are in range 0-400", "*",
              _check_gain_range),
    Assertion("mute_values", "All mute states (0x35) are 0 or 1", "*",
              _check_mute_values),
    Assertion("channel_range", "Channel bytes in gain/mute are 0-7", "*",
              _check_channel_range),
    Assertion("ack_follows_write", "Write commands get ACK response within 3 packets", "*",
              _check_ack_follows_write),
    Assertion("startup_sequence", "Init sequence starts with 0x10->0x13->0x2c->0x22->0x14",
              "*startup*", _check_startup_sequence),
    Assertion("config_pages_complete", "Config reads cover all 9 pages (0-8)",
              "*startup*", _check_config_pages_complete),
    Assertion("preset_names_30", "Preset name reads cover all 30 slots",
              "*startup*", _check_preset_names_30),
    Assertion("gain_cal_0db", "Gain sweep to 0 dB ends at raw 280",
              "*from -60 to 0 dB*", _check_gain_calibration_0db),
    Assertion("gain_cal_12db", "Gain sweep to +12 dB ends at raw 400",
              "*from -60 to +12 dB*", _check_gain_calibration_12db),
]


def run_assertions(
    commands: list[DecodedCommand],
    filepath: str | Path,
    assertion_name: str = "all",
) -> list[AssertionResult]:
    """Run matching assertions against decoded commands from a capture file."""
    results: list[AssertionResult] = []

    for assertion in ASSERTIONS:
        # Filter by name
        if assertion_name != "all" and assertion.name != assertion_name:
            continue
        # Filter by capture file pattern
        if not matches_capture(assertion, filepath):
            continue

        passed, detail = assertion.check(commands)
        results.append(AssertionResult(assertion=assertion, passed=passed, detail=detail))

    return results


def format_results(results: list[AssertionResult], verbose: bool = False) -> str:
    """Format assertion results as text."""
    lines: list[str] = []

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    for r in results:
        if r.passed and not verbose:
            continue
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{status}] {r.assertion.name}: {r.detail}")

    summary = f"{passed} passed, {failed} failed ({len(results)} total)"
    if failed:
        lines.append(f"\n  RESULT: {summary}")
    elif verbose:
        lines.append(f"\n  RESULT: {summary}")
    else:
        lines.append(f"  All {passed} assertions passed")

    return "\n".join(lines)
