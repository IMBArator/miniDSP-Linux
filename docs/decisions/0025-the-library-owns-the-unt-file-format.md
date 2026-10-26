---
status: accepted
date: 2026-10-26
decision-makers: Maximilian Zettler
---

# The library owns the .unt file format

## Context and Problem Statement

`.unt` is the manufacturer editor's preset file: a 50-byte header and 30 slots
of 432 bytes. Until now the reader and writer lived in the Qt app
(`minidspqt/unt_loader.py`, `unt_writer.py`, a bundled `blank.unt`), which kept a
private copy of the preset field offsets next to the library's
`parse_preset_params()`. With the editor's save and restore traffic captured,
the library can produce and consume `.unt` files directly from the device —
so the format has to live where the device code is.

## Decision Drivers

* One source for preset offsets and conversions
  ([ADR-0011](0011-make-minidsp-protocol-the-single-source-of-conversions-and-constants.md)).
* Library first, GUI separate
  ([ADR-0004](0004-keep-this-repository-library-first-and-develop-the-gui-separately.md)):
  the CLI and any other consumer need the format too.
* An unedited load → save must give the same bytes — not every byte of the
  format is understood (the Qt app's ADR-0016 rule).

## Considered Options

* Move the format into `minidsp/unt.py` with byte-preserving, in-place edits
* Keep it in the Qt app and have the library hand over raw blobs only
* Rebuild every file from the parsed model

## Decision Outcome

Chosen option: **`minidsp/unt.py`** (`c72d46e`, `630bf58`). `UntFile` holds the
13010 raw bytes and edits fields in place; `pack_preset_params()` in
`minidsp.protocol` is the inverse of `parse_preset_params()` and patches only
modelled fields (it also keeps flag bits the parser ignores). `blank()` is
generated from constants instead of shipping a binary template, and unused
slots follow the editor's layout (430 × `0x64` + CRLF). `slots_to_save()`
encodes the editor's rule for which slots a file contains.

### Consequences

* Good, because the offsets exist once, and a file built from device data is
  byte-identical to the editor's (tested against
  `miniDSP current settings 261026.unt`).
* Good, because unknown bytes round-trip; slots can now also be cleared.
* Neutral, because the Qt app has to migrate to the library API and drop its
  copies.
* Bad, because the generated blank differs from the Qt `blank.unt` in the
  CRLF of each unused slot — the library follows the editor-saved files.

### Confirmation

`tests/test_unt.py` round-trips all three fixture files byte for byte;
`tests/test_protocol.py` checks `pack_preset_params(parse_preset_params(b), b) == b`
for every fixture slot.

## More Information

* `analysis/protocol.md`, "Configuration File Format (.unt)";
  [ADR-0026](0026-transfer-presets-the-way-the-editor-does.md) for the device side.
