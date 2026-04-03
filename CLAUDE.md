# miniDSP-Linux

## Project Goal

Reverse engineer the USB HID protocol used by the **the t.racks DSP 4x4 Mini** (a Musicrown-based device) by analyzing Wireshark USBPcap captures, then build a Python tool to manage the DSP on Linux.

## Repository Layout

```
minidsp/                  # Python package — the application
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

tests/
  test_protocol.py        # protocol encoding/decoding tests

analysis/                 # Protocol reverse engineering (reference only)
  protocol.md             # full protocol specification
  t-racks-dsp-4x4-research.md
  dsp-408-ui-summary.md   # cross-reference: Aeternitaas/dsp-408-ui
  extract_hid.py          # Wireshark capture analysis scripts
  extract_gain_commands.py
  hid_packets.txt
  miniDSP USBTree output.txt
  miniDSP current settings.unt
  usb_captures/           # Wireshark USBPcap text exports
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

### Useful Wireshark filters when re-exporting
```
usb.addr == "1.17.2" && usb.transfer_type == 0x01
```

## Workflow Notes

- Document newly discovered command opcodes in `protocol.py` with comments showing the raw hex and what it controls.
- Protocol analysis artifacts go in `analysis/`, application code in `minidsp/`.
- When decoding HID payloads, note byte offsets and value ranges.
