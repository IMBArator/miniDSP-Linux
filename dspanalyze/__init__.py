"""Protocol-analysis toolchain for the t.racks DSP 4x4 Mini.

This package supports reverse-engineering and verifying the USB HID protocol
of the Musicrown-based t.racks DSP 4x4 Mini (VID/PID ``0x0168:0x0821``). All
protocol knowledge — opcodes, payload offsets, value formats — lives in the
bundled ``protocol_config.toml`` and is consumed by every module here.

Capabilities:

- **Capture** (:mod:`~dspanalyze.capture`): drive ``tshark`` to record USB
  traffic, auto-detecting the device's bus/address on Linux.
- **Read** (:mod:`~dspanalyze.readers`): dispatch ``.pcapng`` vs. Wireshark
  text exports into a common :class:`~dspanalyze.readers.RawPacket` stream.
- **Decode** (:mod:`~dspanalyze.decode`): turn raw packets into structured
  :class:`~dspanalyze.decode.DecodedCommand` instances using
  ``protocol_config.toml``.
- **Check** (:mod:`~dspanalyze.check`): run protocol assertions to catch
  regressions in our protocol model.
- **Extract defaults** (:mod:`~dspanalyze.extract_defaults`): stitch the F00
  factory preset out of a startup capture into the TOML bundled by
  :mod:`minidsp.defaults`.
- **Output** (:mod:`~dspanalyze.output`): render decoded commands as human
  tables, Claude-friendly compact summaries, or raw hex.
- **Metadata** (:mod:`~dspanalyze.metadata`): write and read per-capture
  ``.meta.toml`` sidecar files.

Invoke via ``python -m dspanalyze <subcommand>`` or the ``dspanalyze`` entry
point — see :func:`dspanalyze.cli.main`.
"""
