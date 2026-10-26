---
status: accepted
date: 2026-10-26
decision-makers: Maximilian Zettler
---

# Transfer presets the way the editor does

## Context and Problem Statement

Saving a `.unt` needs every stored preset, but the library could only read the
*active* one; recalling each slot with `0x20` would change the live audio. Two
captures of the manufacturer editor (`capture_20261026_221454` save,
`capture_20261026_222715` restore) showed its sequences: save reads the
header block (`0x19`) and each stored slot with `0x24` select + `0x28` page
reads, without recall; restore sends `0x23`, a header write (`0x1a`) that
includes the lock PIN field, `0x25` page writes and a reboot (`0x04`). Some
details stay open — notably whether `0x23` erases slots the file leaves empty.

## Decision Drivers

* Only capture-verified behaviour
  ([ADR-0001](0001-verify-every-protocol-claim-against-device-captures.md)).
* Saving must not disturb the audio.
* A restore rewrites preset flash and reboots the device; its PIN side effect
  could lock a user out later.
* Every step is validated ([ADR-0015](0015-validate-every-device-response-instead-of-fire-and-forget.md)).

## Considered Options

* Replicate the editor's sequences exactly, with guard rails on restore
* Save by recalling each slot (`0x20`) and restoring the active one afterwards
* Implement save only and leave restore until the open questions are settled

## Decision Outcome

Chosen option: **replicate the editor** (`7ee1f99`, `6814953`).
`read_stored_presets()` / `export_unt()` follow the save sequence and pick the
slots by name (not `"Default Preset"`), so the exported file equals the
editor's. `restore_unt()` follows the restore sequence but:

* requires `confirm=True` and refuses a file without presets (`0x23` might
  erase everything);
* keeps the device's current lock PIN by default (read via `0x19`, spliced into
  the `0x1a` data); `keep_device_pin=False` sends the file header like the editor;
* writes 419 bytes per slot like the editor, never touches F00
  ([ADR-0016](0016-refuse-to-overwrite-the-factory-preset-slot.md)), and closes
  the handle after the reboot command.

### Consequences

* Good, because saving is non-intrusive and byte-identical to the editor.
* Good, because a restore cannot silently change the lock PIN.
* Bad, because a restore's effect on slots that are empty in the file is not
  verified; it is documented and printed by `minidsp restore-unt`.
* Bad, because preset bytes 419–428 (test tone, delay display unit, Out1 PEQ
  channel bypass) are not restored — the editor does not send them either.

### Confirmation

`tests/test_device.py` drives both sequences against a fake device built from
the editor's file and compares the frames with the captured ones; the CLI
refuses `restore-unt` without `--yes`.

## More Information

* `analysis/protocol.md`, "Preset File Transfer (.unt Save / Restore)";
  [ADR-0025](0025-the-library-owns-the-unt-file-format.md) for the file format.
