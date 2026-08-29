---
status: accepted
date: 2026-04-03
decision-makers: Maximilian Zettler
---

# Speak to the device through /dev/hidraw without a USB library

## Context and Problem Statement

The DSP presents itself as a USB HID device (VID `0168`, PID `0821`) moving
64-byte interrupt reports. Python has several ways to reach it: `libusb`-based
stacks (pyusb), the `hidapi` bindings, or the Linux kernel's own hidraw driver,
which exposes each HID device as a `/dev/hidrawN` character device readable
with plain `os.open`/`os.read`/`os.write`.

## Decision Drivers

* The library should install with zero native dependencies — this is also the
  foundation the Qt GUI builds on and ships inside an AppImage.
* Device discovery must be automatic (find the DSP among all HID devices).
* Claiming the device must not fight the kernel driver (libusb requires
  detaching it).
* Linux is the target platform; portability is not a driver.

## Considered Options

* Kernel hidraw device nodes, discovered via sysfs
* `hidapi` (cython-hidapi) bindings
* pyusb / libusb with kernel-driver detach

## Decision Outcome

Chosen option: **hidraw via plain file I/O**. `find_hidraw_device()` scans
`/sys/class/hidraw/hidraw*/device` for the VID:PID and the transport is
`os.open` + `select` + `os.read`/`os.write` on the node (`device.py`). No
Python package or C library is required beyond the standard library.
Permissions are handled the standard Linux way — a udev rule documented in the
README grants non-root access.

### Consequences

* Good, because the runtime dependency list stays trivially small (`tomli-w`,
  `rich`); nothing native to compile or vendor.
* Good, because the kernel driver stays bound — no detach/reattach dance, and
  the device keeps working for other tools when the library exits.
* Good, because an fd-based transport enables `fcntl.flock` single-instance
  locking ([ADR-0012](0012-serialise-device-access-with-an-exclusive-flock-on-the-hidraw-fd.md))
  and `select`-based timeouts with no extra machinery.
* Bad, because it is Linux-only; the Windows path (setup-windows.bat) exists
  only for the analysis tooling, not for device control.
* Neutral, because users must install a udev rule once for non-root access.

### Confirmation

`minidsp/device.py` contains no imports beyond the standard library for
transport; `pyproject.toml` lists no USB/HID dependency.

## Pros and Cons of the Options

### hidraw

* Good, because zero dependencies and full control over framing and timeouts
* Good, because sysfs makes VID/PID discovery a few lines of globbing
* Bad, because Linux-only

### hidapi

* Good, because cross-platform
* Bad, because it adds a native wheel dependency for functionality the kernel
  already provides here
* Bad, because it abstracts away the fd, blocking the flock approach

### pyusb / libusb

* Good, because it can reach non-HID endpoints if that were ever needed
* Bad, because it must detach the kernel HID driver to claim the interface
* Bad, because it is the heaviest dependency for the least benefit

## More Information

* `cf6c68b` — initial implementation; `ca91676` — the flock that relies on
  owning the raw fd.
* The `device.py` module docstring mentions a cython-hidapi fallback; no such
  fallback is implemented. Treat hidraw as the only transport.
* Amended by [ADR-0024](0024-support-windows-through-a-hidapi-transport.md):
  hidapi now exists as the Windows transport (selected by platform, not a
  fallback) and the false docstring is fixed; hidraw remains unchanged as the
  only Linux transport, now living in `minidsp/transport.py`.
