---
status: accepted
date: 2026-04-04
decision-makers: Maximilian Zettler
---

# Drive USB capture and pcapng parsing through tshark subprocesses

## Context and Problem Statement

The analyzer must read `.pcapng` USB captures (from Linux usbmon and Windows
USBPcap) and, ideally, record new ones itself. Python-side options are pcap
parsing libraries (scapy, pyshark, dpkt) or shelling out to the Wireshark CLI
tools that every capture workflow already requires.

## Decision Drivers

* Wireshark/tshark is already installed on any machine doing this work — the
  captures come from it.
* USB-link-layer framing (usbmon vs USBPcap pseudo-headers) is genuinely
  gnarly; tshark's dissectors already handle both.
* The analysis toolchain should stay dependency-light like the runtime
  library.

## Considered Options

* `tshark` subprocesses: `-T fields` for reading, `dumpcap`/`tshark` for
  capturing
* pyshark (which itself wraps tshark)
* scapy / dpkt native parsing

## Decision Outcome

Chosen option: **tshark subprocesses**. Reading uses `tshark -T fields`
(`readers/pcapng.py`, `9c615a9`); capture orchestrates tshark with device
auto-detection via sysfs (`8cb82fb`). Two platform realities were absorbed
into this layer rather than pushed onto users:

* On Linux/usbmon tshark exposes HID payloads as `usb.capdata`, on
  Windows/USBPcap as `usbhid.data`; the reader tries both (`95dbbd9`).
* BPF capture filters cannot express USB display-filter semantics, so capture
  is two-pass: record everything, then filter by `usb.device_address` into a
  small artifact (`b03515a`).

Capture privileges are handled by `make capture-enable`/`capture-disable`
targets that manage dumpcap capabilities and the usbmon module (`27ac39b`,
`2ac3b39`).

### Consequences

* Good, because zero pcap-parsing dependencies and correct handling of both
  capture pseudo-header formats from day one.
* Good, because captures produced by the tool are pre-filtered to DSP traffic
  and small enough to commit ([ADR-0001](0001-verify-every-protocol-claim-against-device-captures.md)
  depends on this).
* Neutral, because tshark becomes a runtime requirement of the *analysis*
  tool only — the control library is unaffected.
* Bad, because field extraction is stringly-typed; a tshark output format
  change would break the reader silently.
* Bad, because subprocess orchestration (Ctrl+C handling, `proc.terminate()`
  portability) took real iteration to get right (`b03515a`).

### Confirmation

`tests/test_dspanalyze/` covers the readers against checked-in captures; the
reader's dual-field fallback is exercised by both usbmon and USBPcap files in
`analysis/usb_captures/`.

## More Information

* `9c615a9`, `8cb82fb`, `95dbbd9`, `b03515a`, `27ac39b`, `2ac3b39`, `c070ed8`.
