---
status: accepted
date: 2026-08-28
decision-makers: Maximilian Zettler
---

# Support Windows through a platform-selected hidapi transport

## Context and Problem Statement

Device control was Linux-only by construction: `device.py` opened
`/dev/hidrawN` directly ([ADR-0002](0002-speak-to-the-device-through-hidraw-without-a-usb-library.md))
and imported `fcntl` at module scope, so on Windows the import failed before
anything could run — taking the `minidsp` CLI and `dspanalyze calibrate` down
with it. Meanwhile the analysis toolchain already worked there (USBPcap
capture, PowerShell device detection), and the captures this project is built
on were recorded on Windows in the first place. Users on Windows could analyse
the protocol but not talk to their DSP.

Everything above the two I/O methods — every command builder, the eight-step
`read_config`, the response validation — is already platform-neutral. The
question was only how to reach the device on Windows, and how much of the
Linux path to risk in the process.

## Decision Drivers

* The Linux path is the proven one and must stay byte-identical: same
  syscalls, same flock semantics, same log lines and error messages.
* Windows has no hidraw node and no `flock`; whatever replaces them must
  provide the same single-instance guarantee, including release on crash
  ([ADR-0012](0012-serialise-device-access-with-an-exclusive-flock-on-the-hidraw-fd.md)).
* A Linux install must not grow a native dependency it never uses.
* The protocol layer is verified against captures
  ([ADR-0001](0001-verify-every-protocol-claim-against-device-captures.md))
  and must not be touched to accommodate a second platform.

## Considered Options

* A `Transport` interface with a hidraw implementation and a hidapi
  implementation, selected by platform
* `hidapi` on every platform, replacing hidraw
* Platform branches inside `device.py`
* Stay Linux-only; document Windows as unsupported

## Decision Outcome

Chosen option: **a `Transport` interface with two implementations**
(`minidsp/transport.py`). The hidraw code moved there verbatim as
`HidrawTransport`; `HidapiTransport` is new and used only on Windows;
`default_transport()` picks by `sys.platform`, and `DSPmini` takes an optional
transport so the choice can be overridden or faked. `DeviceClosedError` moved
along with the I/O it guards and is re-exported from `device.py`, as is
`find_hidraw_device`.

Three details are worth recording, because each is a place a wrong guess would
have broken everything silently:

* **Report ID.** The DSP uses unnumbered reports. hidapi still wants a leading
  report number on write, so `HidapiTransport.write` sends
  `b"\x00" + report` (65 bytes) and `read` returns the bare 64 data bytes.
  This is confined to the transport — `protocol.build_frame` is unchanged and
  the frames on the wire are identical on both platforms.
* **Timeouts.** hidapi stays in blocking mode and each read passes
  `timeout_ms` through, so the existing 500 / 2000 / 3000 ms command timeouts
  keep their meaning without a second timeout mechanism.
* **Single-instance guard.** A named Win32 mutex (`Local\minidsp-hid-0168-0821`,
  created via `ctypes`, `ERROR_ALREADY_EXISTS` meaning "another process has
  it") replaces the flock. Windows abandons a mutex when its owner dies, which
  is the property that made flock the right choice on Linux: no stale lock, no
  cleanup path.

`hidapi` is a hard dependency gated by a platform marker
(`sys_platform == 'win32'`), not an extra, so Windows works straight after
`uv sync` while Linux resolves exactly as before.

### Consequences

* Good, because Windows users get the full CLI and library, not just the
  analysis tooling.
* Good, because the transport seam made `device.py` unit-testable for the
  first time — a `FakeTransport` now drives the init-retry loop, the config
  read, the lock error and the store-preset sequence with no hardware.
* Good, because the Linux path did not change: same fd, same flock, same
  `select` timeout, same messages.
* Bad, because a second transport is a second thing to keep correct, and only
  one of them is exercised by CI on Linux.
* Neutral, because the `Local\` namespace scopes the mutex to one login
  session — two users on the same machine are not guarded against each other.
  The protocol offers no way to detect that, and it is not a realistic setup
  for a desk-side DSP.
* Neutral, because a blocking hidapi read delays Ctrl+C by up to the current
  timeout (worst case 3 s, during a preset store).

### Confirmation

`make test` covers the device layer through `FakeTransport`, and the hidapi
report-ID and timeout handling through a stubbed `hid` module, so both run on
Linux. `uv sync` on Linux resolves without `hidapi`. The remaining
confirmation is on-hardware: a Windows machine with the DSP attached runs a
checklist (init, dump, level watch, mute, preset load and store, lock
conflict, process kill, unplug/replug) before Windows is documented as
verified.

## Pros and Cons of the Options

### Transport interface with hidraw + hidapi

* Good, because each platform keeps its native, best-fit mechanism
* Good, because the injection point makes the device layer testable
* Bad, because it adds an abstraction where there was a direct call

### hidapi everywhere

* Good, because there would be one transport to maintain and test
* Bad, because it adds a native wheel to every Linux install for no gain
* Bad, because it hides the fd, giving up flock — the very reason
  [ADR-0012](0012-serialise-device-access-with-an-exclusive-flock-on-the-hidraw-fd.md)
  works — and it would rewrite the one path that is known to work

### Platform branches inside device.py

* Good, because no new module
* Bad, because the protocol logic would be interleaved with two I/O
  strategies, and the Linux path would be edited to add Windows

### Stay Linux-only

* Good, because zero risk to what works
* Bad, because the device's own vendor software is Windows-only; users there
  have no free alternative, which is the point of this project

## More Information

* `ff55876` — the transport extraction, the hidapi transport with its
  marker-gated dependency, and the `FakeTransport` device tests;
  `d6de28d` — the shared tshark discovery for the pcapng reader.
* Amends [ADR-0002](0002-speak-to-the-device-through-hidraw-without-a-usb-library.md):
  its "hidapi fallback" defect note is resolved — hidapi now exists as a real
  transport, chosen by platform rather than as a fallback. hidraw remains the
  only Linux transport, for the reasons that record gives.
* Scopes [ADR-0012](0012-serialise-device-access-with-an-exclusive-flock-on-the-hidraw-fd.md)
  to Linux: the flock reasoning stands there; Windows reaches the same
  guarantee with a named mutex.
* `setup-windows.bat` was removed with this change: it predated uv, pinned a
  Python version, named a setuptools backend the project no longer uses, and
  advertised a `python -m minidsp` that could not have worked. The README's
  uv-based Windows instructions replace it.
