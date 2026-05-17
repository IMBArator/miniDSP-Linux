"""Runtime control library for the t.racks DSP 4x4 Mini.

This package provides a Python interface to the Musicrown-based DSP 4x4 Mini
(USB VID/PID ``0x0168:0x0821``) over USB HID. The primary entry point is the
:class:`~minidsp.device.DSPmini` class, which opens the kernel ``/dev/hidraw``
node, acquires an exclusive advisory lock, and exposes high-level methods for
every implemented opcode (gain, mute, PEQ, crossover, delay, routing, presets,
PIN lock, level polling, …).

Modules:
    device: :class:`DSPmini` — USB HID open/close, send/recv, command helpers.
    protocol: Frame encoding/decoding, command builders, response parsers,
        and value-format converters (raw ↔ dB / Hz / ms / Q).
    cli: ``python -m minidsp`` command-line entry point.
    defaults: Bundled F00 factory-preset values
        (see :func:`~minidsp.defaults.load_factory_defaults`).

See ``analysis/protocol.md`` in the source tree for the full reverse-engineered
protocol specification.
"""
