# miniDSP-Linux

## IMPORTANT


- explain in single sentences what you are doing so we can learn from it.
- commit using conventional commits and commit grouped by topic.
- automatically commit after significant changes.
- you are allowed to use subagents if applicable for tasks. use models that are effective.
- avoid using commands that generate friction and need user input while exploring/researching.
- always use tools that we commited to, e.g. use the analyse tool instead of creating python/bash one-liners.
- if you need complex one-liners to explore/research, suggest adding these to a make file for repeatability.
- suggest additional pre-made tools if it makes things easier or more effective
- remember that claude usage is expensive, try to be economical when processing data. use agents with lower grade modles if bulk processing is needed.
- always feel free to suggest improvements to the code and to the process!
- be more explanative so the humans can learn along the way.
- always remember to update the protocol implementation and documentation as well as the feature list. but always make sure the results are verified before changing docs and code. and always ask. it is curcial to never change protocol docs and code without confirmation!

## Project Goal

Reverse engineer the USB HID protocol used by the **the t.racks DSP 4x4 Mini** (a Musicrown-based device) by analyzing Wireshark USBPcap captures, then build a Python tool to manage the DSP on Linux.

## Repository Layout

```
minidsp/                  # Python package — the runtime control application
  __init__.py
  __main__.py             # entry point (--gui or CLI)
  device.py               # USB HID open/close, send/recv, config read
  protocol.py             # frame encoding/decoding, command builders, parsers
  cli.py                  # CLI (mute/unmute)
  gui/                    # PySide6 GUI
    app.py                # QApplication entry, dark theme
    main_window.py        # main window with 8 channel strips
    channel_strip.py      # fader + meter + mute + compressor LED
    level_meter.py        # custom QPainter dB-scaled meter
    device_thread.py      # QThread polling + command coalescing

dspanalyze/               # Protocol analysis toolchain
  __init__.py
  __main__.py             # python -m dspanalyze entry
  cli.py                  # argparse: analyze, check, capture, list-captures
  config.py               # load protocol_config.toml, value format converters
  protocol_config.toml    # all protocol knowledge (opcodes, fields, formats)
  decode.py               # frame → structured command decoder
  capture.py              # tshark-based USB capture with device auto-detect
  check.py                # protocol assertion framework (12 assertions)
  metadata.py             # per-capture .meta.toml sidecar files
  readers/
    __init__.py            # RawPacket dataclass, read_capture() dispatcher
    pcapng.py              # tshark -T fields based pcapng reader
    wireshark_text.py      # Wireshark text export parser
  output/
    __init__.py
    claude.py              # compact structured output for Claude
    human.py               # terminal table with summary
    raw.py                 # raw hex dump

tests/
  test_protocol.py        # protocol encoding/decoding tests
  test_dspanalyze/        # analysis tool tests

analysis/                 # Protocol reverse engineering (reference only)
  protocol.md             # full protocol specification
  feature-list.md         # DSP feature inventory with protocol status
  t-racks-dsp-4x4-research.md
  dsp-408-ui-summary.md   # cross-reference: Aeternitaas/dsp-408-ui
  extract_hid.py          # legacy analysis script (superseded by dspanalyze)
  extract_gain_commands.py
  hid_packets.txt
  miniDSP USBTree output.txt
  miniDSP current settings.unt
  usb_captures/           # Wireshark captures (.txt exports + .pcapng)
  resources/              # screenshots, manual PDF

pyproject.toml            # build system, dependencies, entry points
Makefile                  # convenience targets for analysis workflows
```

## Device Info

- **VID/PID:** `0x0168`:`0x0821` (Musicrown "Dsp Process")
- **USB:** 1.1 Full-Speed, HID class, bus powered (100 mA)
- **Communication:** URB_INTERRUPT transfers, 64-byte HID reports
- **OUT endpoint:** 0x02 (host → device), **IN endpoint:** 0x81 (device → host)

## Protocol Summary

See `analysis/protocol.md` for the full reverse-engineered specification.

- Frame format: `10 02 [SRC] [DST] [LEN] [PAYLOAD] 10 03 [XOR_CHK]`
- Checksum: XOR of length byte + all payload bytes
- Key commands: `0x10` init, `0x27` read config (9 pages × 50 bytes), `0x34` gain, `0x35` mute, `0x40` poll levels, `0x12` activate
- Level response: 28-byte payload, 8 channels × 3-byte triplets `[val_lo, val_hi, instant]` (uint16 LE linear amplitude)
- Gain encoding: dual resolution raw 0–400 (0.5 dB/step below −20 dB, 0.1 dB/step above)
- Config pages reconstruct the `.unt` preset structure byte-for-byte

### Cross-reference

- `dsp-408-ui` (Aeternitaas/dsp-408-ui) — same Musicrown protocol over TCP for DSP 408
- Confirmed: PEQ, GEQ, crossover, routing, preset commands from that project apply here

## Workflow Notes

- Document newly discovered command opcodes in `protocol.py` with comments showing the raw hex and what it controls.
- Protocol analysis artifacts go in `analysis/`, application code in `minidsp/`.
- When decoding HID payloads, note byte offsets and value ranges.
