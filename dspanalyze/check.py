"""Protocol assertion framework — verify protocol knowledge against captures.

Each assertion is a named check that validates some property of the decoded
commands. Assertions can target all captures (``capture_glob == "*"``) or
specific file patterns (e.g. ``"*startup*"``). Together they guard against
regressions as protocol knowledge evolves.

Registered assertions (see :data:`ASSERTIONS`):

- ``checksum_valid`` — every frame's XOR checksum is correct.
- ``frame_structure`` — every packet parses as a valid STX/ETX frame.
- ``no_unknown_opcodes`` — every opcode is in ``protocol_config.toml``.
- ``gain_range_0_400`` — gain commands (0x34) carry raw values in 0–400.
- ``mute_values`` — mute commands (0x35) carry state ∈ {0, 1}.
- ``channel_range`` — channel bytes in gain/mute fall in 0–7.
- ``ack_follows_write`` — every write command is followed by an ACK (0x01)
  within 3 packets.
- ``startup_sequence`` — startup captures open with
  ``0x10 → 0x13 → 0x2C → 0x22 → 0x14``.
- ``config_pages_complete`` — startup captures contain all 9 config pages.
- ``preset_names_30`` — startup captures read all 30 preset name slots.
- ``gain_cal_0db`` / ``gain_cal_12db`` — gain-sweep captures end at the
  expected raw maxima (280 = 0 dB, 400 = +12 dB).

All check functions share the contract: take a ``list[DecodedCommand]``,
return ``(passed: bool, detail: str)`` where ``detail`` is a short human
message suitable for CLI output.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dspanalyze.decode import DecodedCommand


@dataclass
class Assertion:
    """A named protocol assertion.

    Attributes:
        name: Short identifier used to select the assertion on the CLI.
        description: Human-readable description of what the assertion checks.
        capture_glob: Filename glob pattern — ``"*"`` for all captures, or a
            pattern such as ``"*startup*"`` to target specific files.
        check: Callable that receives decoded commands and returns
            ``(passed, detail_message)``.
    """
    name: str
    description: str
    capture_glob: str
    check: Callable[[list[DecodedCommand]], tuple[bool, str]]


@dataclass
class AssertionResult:
    """Result of running a single assertion against a capture.

    Attributes:
        assertion: The :class:`Assertion` that was evaluated.
        passed: ``True`` if the check passed, ``False`` if it failed.
        detail: Human-readable explanation returned by the check function.
    """
    assertion: Assertion
    passed: bool
    detail: str


def matches_capture(assertion: Assertion, filepath: str | Path) -> bool:
    """Return whether an assertion applies to the given capture file.

    Args:
        assertion: The assertion to test.
        filepath: Path to the capture file (only the filename is checked).

    Returns:
        ``True`` if ``assertion.capture_glob`` is ``"*"`` or the filename
        matches the glob pattern.
    """
    if assertion.capture_glob == "*":
        return True
    return fnmatch.fnmatch(Path(filepath).name, assertion.capture_glob)


# ── Assertion implementations ──────────────────────────────


def _check_checksums(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Assert that every frame carries a valid XOR checksum.

    Inspects ``cmd.frame.checksum_valid`` (computed by the decoder against
    ``LEN ⊕ payload bytes``).

    Args:
        commands: Decoded commands from a single capture.

    Returns:
        ``(True, detail)`` if all checksums are valid; ``(False, detail)``
        where ``detail`` lists the first five offending frame numbers.
    """
    bad = [c for c in commands if not c.frame.checksum_valid]
    if bad:
        frames = ", ".join(f"#{c.frame.raw.frame_number}" for c in bad[:5])
        return False, f"{len(bad)} checksum failures: {frames}"
    return True, f"all {len(commands)} checksums valid"


def _check_frame_structure(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Assert that every packet parses as a valid STX/ETX-framed payload.

    Commands the decoder could not frame are marked
    ``opcode_name == "unparseable"``; this check flags any such entries.

    Args:
        commands: Decoded commands from a single capture.

    Returns:
        ``(True, detail)`` when all frames parsed; ``(False, detail)`` listing
        the first five unparseable frame numbers.
    """
    unparseable = [c for c in commands if c.opcode_name == "unparseable"]
    if unparseable:
        frames = ", ".join(f"#{c.frame.raw.frame_number}" for c in unparseable[:5])
        return False, f"{len(unparseable)} unparseable frames: {frames}"
    return True, f"all {len(commands)} frames parseable"


def _check_gain_range(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Assert that every 0x34 gain command carries a raw value in 0–400.

    Range 0–400 corresponds to the dual-resolution encoding (0.5 dB/step
    below −20 dB, 0.1 dB/step above). Values outside this range indicate
    either a corrupt frame or an unknown firmware extension.

    Args:
        commands: Decoded commands from a single capture.

    Returns:
        ``(True, detail)`` if all in range or no gain commands present;
        ``(False, detail)`` listing the first five offending values.
    """
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
    """Assert that every 0x35 mute command's state byte is 0 or 1.

    The mute command carries a single boolean state (0 = unmute, 1 = mute);
    any other value would indicate a misdecoded field or unknown variant.

    Args:
        commands: Decoded commands from a single capture.

    Returns:
        ``(True, detail)`` if all valid or no mute commands present;
        ``(False, detail)`` listing the first five offending states.
    """
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
    """Assert that channel bytes in gain/mute commands fall in 0–7.

    The DSP exposes 8 unified channels (inputs 0–3, outputs 4–7). Values
    outside this range indicate either a corrupt frame or a misinterpreted
    field offset.

    Args:
        commands: Decoded commands from a single capture.

    Returns:
        ``(True, detail)`` if all valid or no relevant commands present;
        ``(False, detail)`` listing the first five offending channel values.
    """
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
    """Assert that every write command is followed by an ACK (0x01) packet.

    Considers write opcodes ``{0x34 gain, 0x35 mute, 0x3B link, 0x2A prepare-link}``
    when seen as the device's echo (``direction == "in"``). The ACK may not be
    the immediately next packet — up to three intervening packets (typically
    unsolicited 0x40 level polls) are tolerated.

    Args:
        commands: Decoded commands from a single capture, in capture order.

    Returns:
        ``(True, detail)`` if every write found a matching ACK or no writes
        were present; ``(False, detail)`` reporting how many writes lacked an
        ACK within the 3-packet window.

    Note:
        Heuristic: a 3-packet ACK window can produce false negatives on
        traces with heavy poll interleaving. Re-run with the affected window
        widened if needed.
    """
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
    """Assert that a startup capture opens with the canonical handshake sequence.

    Collects the first five unique opcodes (ignoring duplicates and bare ACK
    packets, opcode 0x01) and compares them to the expected handshake:
    ``[0x10 init, 0x13 firmware, 0x2C device_info, 0x22 preset_header,
    0x14 preset_index]``.

    Args:
        commands: Decoded commands from a startup capture
            (only applied to files matching ``*startup*``).

    Returns:
        ``(True, detail)`` on exact match; ``(False, detail)`` showing
        expected and observed opcode lists.
    """
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
    """Assert that a startup capture contains all 9 config-page responses (pages 0–8).

    Looks at every 0x24 response with a ``page`` field and verifies that
    each page index 0–8 appears at least once. A capture with no 0x24
    responses passes vacuously (the trace may have been trimmed).

    Args:
        commands: Decoded commands from a startup capture.

    Returns:
        ``(True, detail)`` if all pages are present (or none observed);
        ``(False, detail)`` listing the missing page indices.
    """
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
    """Assert that a sweep-to-0 dB capture peaks at raw gain 280.

    Raw 280 is the dual-resolution encoding for 0.0 dB. Used as a sentinel
    to detect regressions in the raw↔dB calibration table.

    Args:
        commands: Decoded commands from a ``*from -60 to 0 dB*`` capture.

    Returns:
        ``(True, detail)`` if the maximum observed gain raw is exactly 280
        (or no gain commands present); ``(False, detail)`` reporting the
        observed maximum otherwise.
    """
    gain_cmds = [c for c in commands if c.opcode == 0x34 and "value" in c.fields]
    if not gain_cmds:
        return True, "no gain commands found"
    max_val = max(c.fields["value"] for c in gain_cmds if isinstance(c.fields["value"], int))
    if max_val == 280:
        return True, f"max gain raw value = 280 (0.0 dB)"
    return False, f"expected max gain = 280 (0.0 dB), got {max_val}"


def _check_gain_calibration_12db(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Assert that a sweep-to-+12 dB capture peaks at raw gain 400.

    Raw 400 is the upper limit of the dual-resolution encoding and corresponds
    to +12.0 dB. Sentinel for the high end of the calibration table.

    Args:
        commands: Decoded commands from a ``*from -60 to +12 dB*`` capture.

    Returns:
        ``(True, detail)`` if the maximum observed gain raw is exactly 400
        (or no gain commands present); ``(False, detail)`` reporting the
        observed maximum otherwise.
    """
    gain_cmds = [c for c in commands if c.opcode == 0x34 and "value" in c.fields]
    if not gain_cmds:
        return True, "no gain commands found"
    max_val = max(c.fields["value"] for c in gain_cmds if isinstance(c.fields["value"], int))
    if max_val == 400:
        return True, f"max gain raw value = 400 (+12.0 dB)"
    return False, f"expected max gain = 400 (+12.0 dB), got {max_val}"


def _check_no_unknown_opcodes(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Assert that every observed opcode is registered in ``protocol_config.toml``.

    Unknown opcodes are flagged by the decoder via ``cmd.is_known == False``;
    encountering one means either the config is out of date or the device
    firmware emitted an undocumented message.

    Args:
        commands: Decoded commands from a single capture.

    Returns:
        ``(True, detail)`` if no unknowns were seen; ``(False, detail)``
        listing every distinct unknown opcode in ``0xNN`` form.
    """
    unknowns = {c.opcode for c in commands if not c.is_known}
    if unknowns:
        ops = sorted(f"0x{o:02x}" for o in unknowns)
        return False, f"unknown opcodes: {', '.join(ops)}"
    return True, "all opcodes recognized"


def _check_preset_names_30(commands: list[DecodedCommand]) -> tuple[bool, str]:
    """Assert that a startup capture reads preset names for all 30 user slots.

    The manufacturer software reads every preset name during startup
    (opcode 0x29, slot field 0–29). Any missing slot in a startup capture
    points to a truncated trace or a protocol change.

    Args:
        commands: Decoded commands from a startup capture.

    Returns:
        ``(True, detail)`` if all 30 slots are present (or no 0x29
        commands observed); ``(False, detail)`` listing the missing slot
        indices.
    """
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
    """Run matching assertions against decoded commands from a capture file.

    Filters the global :data:`ASSERTIONS` list by both ``assertion_name`` and
    the capture filename glob, then runs each matching assertion.

    Args:
        commands: Decoded commands from the capture.
        filepath: Path to the capture file (used for glob matching).
        assertion_name: Name of a specific assertion to run, or ``"all"``
            to run every assertion that matches the capture filename.

    Returns:
        List of :class:`AssertionResult` for each assertion that was run,
        in registry order.
    """
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
    """Format assertion results as a human-readable text block.

    Args:
        results: List of :class:`AssertionResult` from :func:`run_assertions`.
        verbose: When ``True``, include passing assertions in the output.
            Failures are always shown.

    Returns:
        Multi-line string with one line per shown result and a summary footer.
    """
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
