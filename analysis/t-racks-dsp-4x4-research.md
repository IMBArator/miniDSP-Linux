# Thomann T.Racks DSP 4x4 — USB Protocol Analysis & Linux Implementation Research

**Date:** 2026-04-01
**Status:** No complete Linux implementation exists yet. The binary command protocol has been substantially reverse-engineered for the related DSP 408 model. The USB HID transport layer for the DSP 4x4 Mini remains undocumented.

---

## Table of Contents

1. [Device Overview](#1-device-overview)
2. [OEM Manufacturer](#2-oem-manufacturer)
3. [Hardware Internals](#3-hardware-internals)
4. [USB Interface Details](#4-usb-interface-details)
5. [T.Racks DSP Product Family & Protocol Variants](#5-tracks-dsp-product-family--protocol-variants)
6. [Existing Reverse Engineering Work](#6-existing-reverse-engineering-work)
7. [Musicrown Binary Protocol Reference](#7-musicrown-binary-protocol-reference)
8. [Linux Status & Known Workarounds](#8-linux-status--known-workarounds)
9. [Comparable Reverse Engineering Projects](#9-comparable-reverse-engineering-projects)
10. [Recommended Approach for Linux Support](#10-recommended-approach-for-linux-support)
11. [Tools & Resources](#11-tools--resources)
12. [Forum Threads & Community Discussions](#12-forum-threads--community-discussions)
13. [Conclusions & Next Steps](#13-conclusions--next-steps)

---

## 1. Device Overview

The **Thomann T.Racks DSP 4x4 Mini** is a compact digital speaker management system / crossover DSP with:

- 4 analog inputs, 4 analog outputs
- PEQ (parametric EQ), GEQ (graphic EQ), crossover filters (hi-pass / lo-pass)
- Delay, gain, mute, matrix routing
- 24-bit AD/DA, 48 kHz sampling rate
- USB connection for configuration via Windows-only software ("T.Racks DSP Processor Editor")
- No front-panel display or physical controls for DSP parameters — **USB is the only configuration interface**

Variants in the same form factor:
- **DSP 4x4 Mini** — base model
- **DSP 4x4 Mini Pro** — adds FIR filter capability
- **DSP 4x4 Mini Amp** — integrated amplifier version

Product page: https://www.thomannmusic.com/the_t.racks_dsp_4x4_mini.htm

---

## 2. OEM Manufacturer

All T.Racks DSP products are manufactured by **Musicrown** (Dongguan Musicrown Electronic Technology Co., Ltd.), a subsidiary of **Longjoin International Holdings Limited**, based in Dongguan / Guangzhou, China.

**Evidence:**
- The device identifies itself on USB as **"Musicrown Dsp Process"**
- Musicrown's product catalog includes equivalent models (DC24, DFX24, DFX48, DM46, DF4.4MN, etc.)
- Musicrown explicitly offers OEM/ODM services for professional audio equipment

**Musicrown website:** http://en.musicrown-audio.com

This is significant because it means all T.Racks DSP models share the same Musicrown firmware and protocol family, just with different hardware configurations and transport layers.

---

## 3. Hardware Internals

Based on the diyAudio teardown thread ("T.racks 4x4 miniDSP undressed"):

| Component | Identification |
|-----------|---------------|
| **Main DSP** | 64-pin IC, **markings deliberately removed**. Likely **Analog Devices ADSP-BF592 (Blackfin)** or possibly ADAU145x/146x family, based on the presence of external SDRAM (ADAU1701 does not use external SDRAM). |
| **DACs** | 2x **PCM5102A** (Texas Instruments) |
| **ADCs** | **PCM1802** (Texas Instruments) |
| **Memory** | External SDRAM on PCB |
| **Other ICs** | RT3609 (Chinese semiconductor, no public datasheet) |
| **Construction** | Stacked PCB design |

The DSP chip markings are intentionally sanded off to prevent identification — a common OEM practice to protect the bill of materials.

**Source:** https://www.diyaudio.com/community/threads/t-racks-4x4-minidsp-undressed.394296/

---

## 4. USB Interface Details

### Identification

| Property | Value |
|----------|-------|
| **USB Vendor ID** | `0x0168` |
| **USB Product ID** | `0x0821` |
| **Device String** | `"Musicrown Dsp Process"` |
| **USB Class** | HID (Human Interface Device) |
| **HID Version** | 1.10 |
| **USB Speed** | Full Speed (12 Mbps) |

### Linux Kernel Recognition

```
hid-generic 0003:0168:0821.0006: input,hidraw5: USB HID v1.10 Device [Musicrown Dsp Process]
```

The device auto-binds to the `hid-generic` driver and appears as `/dev/hidrawN`.

### Key Points

- The device does **NOT** use USB Audio Class — it is purely a HID device for parameter control
- There is no audio streaming over USB; all audio is analog I/O
- The proprietary Musicrown binary protocol is carried inside USB HID reports
- HID was chosen because it requires **no custom drivers** on any OS — the OS provides native HID class drivers
- Typical HID report size for Full Speed USB is **64 bytes**

---

## 5. T.Racks DSP Product Family & Protocol Variants

The T.Racks DSP range splits into two distinct families with different connectivity:

### Compact Models (USB HID only)

| Model | I/O | Transport |
|-------|-----|-----------|
| DSP 4x4 Mini | 4in/4out | **USB HID** (`0168:0821`) |
| DSP 4x4 Mini Pro | 4in/4out + FIR | **USB HID** |
| DSP 4x4 Mini Amp | 4in/4out + amp | **USB HID** |

### Rack-Mount Models (USB + RS232/485 + Ethernet)

| Model | I/O | Transport |
|-------|-----|-----------|
| DSP 204 | 2in/4out | USB + RS232 + Ethernet |
| DSP 206 | 2in/6out | USB + RS232 + Ethernet |
| DSP 306 | 3in/6out | USB + RS232 + Ethernet |
| DSP 408 | 4in/8out | USB + RS232 + **Ethernet (TCP port 9761)** |
| FIR DSP 408 | 4in/8out + FIR | USB + RS232 + Ethernet |

The rack-mount models use **TCP port 9761** with a default device IP of **192.168.3.100** when communicating over Ethernet. The underlying binary command protocol is the same across all models — only the transport layer differs.

---

## 6. Existing Reverse Engineering Work

### Primary Project: `Aeternitaas/dsp-408-ui`

- **Repository:** https://github.com/Aeternitaas/dsp-408-ui
- **Description:** "A modern way to connect and tweak your T.Racks DSP 408"
- **Language:** Dart (Flutter)
- **License:** GPL-3.0
- **Stars:** 22
- **Created:** February 2026, actively developed
- **Platforms:** Windows, Android, Linux
- **Target device:** T.Racks DSP 408 (rack-mount model with Ethernet)
- **Communication:** TCP socket over local network (NOT USB HID)

#### What Has Been Reverse-Engineered

The project has **substantially decoded the Musicrown binary protocol** through Wireshark/pcap analysis of the official Windows editor software. The repository includes:

- Multiple Python analysis scripts (`analyze_pcap.py`, `analyze2.py` through `analyze5.py`, `ap_final.py`)
- A **Wireshark Lua dissector** (`wireshark_scripts/data_text.lua`)
- Full Flutter/Dart implementation of parameter control
- Detailed protocol documentation in code comments and issues

#### Relevance to DSP 4x4 Mini

The binary command protocol is **very likely identical** for the DSP 4x4 Mini since:
1. All devices are manufactured by Musicrown
2. All use the same "T.Racks DSP Processor Editor" software family
3. The protocol is designed to be transport-agnostic

The DSP 4x4 Mini carries the same binary commands over USB HID reports instead of TCP sockets. The **missing piece** is understanding the HID report framing.

---

## 7. Musicrown Binary Protocol Reference

All protocol details below are sourced from the `dsp-408-ui` reverse engineering effort and apply to the DSP 408 over TCP. They are expected to be identical for the DSP 4x4 Mini at the command level.

### Frame Structure

```
10 02 [addr] [dir] [len] [cmd] [data...] 10 03 [checksum]
```

| Field | Size | Description |
|-------|------|-------------|
| `10 02` | 2 bytes | Start-of-frame delimiter |
| `addr` | 1 byte | Device address |
| `dir` | 1 byte | Direction / message type |
| `len` | 1 byte | Length of data payload |
| `cmd` | 1 byte | Command identifier |
| `data` | variable | Command-specific payload |
| `10 03` | 2 bytes | End-of-frame delimiter |
| `checksum` | 1 byte | XOR of all data bytes, initialized to 1 |

### Handshake

```
TX: 10 02 00 01 01 10 10 03 11
```

### Command Reference

| Command | Code | Description |
|---------|------|-------------|
| **Gain** | `0x34` | Set channel gain. Channels `0x00`-`0x0B`. Dual resolution: coarse 0.5 dB steps below -20 dB, fine 0.1 dB steps above -20 dB. |
| **Mute** | `0x35` | Mute/unmute channel |
| **PEQ** | `0x33` | Parametric EQ. 8 bands for inputs, 9 for outputs. Fields: gain, frequency, Q, filter type, bypass. Frequency uses log scale 20 Hz–20 kHz over 300 steps. Q uses log scale 0.40–128.00 over 255 steps. |
| **GEQ** | `0x48` | 31-band graphic EQ. Value encoding: `(dB * 10) + 120` |
| **Hi-Pass Filter** | `0x32` | High-pass crossover filter |
| **Lo-Pass Filter** | `0x31` | Low-pass crossover filter |
| **Matrix Routing** | `0x3a` | Input-to-output routing. Bitmask: In A=`0x01`, In B=`0x02`, In C=`0x04`, In D=`0x08` |
| **Metering** | `0x40` | Request/response for level meters. Response contains 12 channels of IEEE 754 half-precision (float16) meter levels (3 bytes per channel: float16_lo, float16_hi, peak_byte). |
| **Config Dump Request** | `0x27` | Request full configuration dump |
| **Config Dump Response** | `0x24` | Configuration data, 29 chunks (`0x00`-`0x1C`), carrying full preset data |
| **Get Preset** | `0x29` | Request a specific preset |
| **Get All Presets** | `0x2c` | Request list of all presets. 20 user presets available. |

### Checksum Calculation

```python
def calculate_checksum(data_bytes):
    checksum = 1
    for byte in data_bytes:
        checksum ^= byte
    return checksum
```

---

## 8. Linux Status & Known Workarounds

### Current State

- **No native Linux control software exists** for the DSP 4x4 Mini
- The device is **recognized** by the Linux kernel as a HID device
- The official Windows editor software does **NOT work under Wine** — Wine's HID passthrough fails to bridge the USB HID device

### Wine Failure Details

The WineHQ forum thread confirms that when running the T.Racks DSP Processor Editor under Wine:
- The software shows "Link Broken" and continuously scans for the device
- Wine's `winebus` cannot properly pass through HID devices
- This is a fundamental Wine limitation for USB HID, not a simple configuration issue

### Working Workaround

Run the Windows editor inside a **full virtual machine** with USB device passthrough:

1. **VirtualBox** (with Extension Pack for USB 2.0 support) — create a USB device filter for VID `0168` / PID `0821`
2. **GNOME Boxes** / **virt-manager** (KVM/QEMU) — use SPICE USB redirection or manual USB host passthrough

This is confirmed working by multiple users.

---

## 9. Comparable Reverse Engineering Projects

### miniDSP — `minidsp-rs` (Best Reference)

- **Repository:** https://github.com/mrene/minidsp-rs
- **Language:** Rust
- **Transport:** USB HID (same as T.Racks DSP 4x4 Mini)
- **VID:PID:** `2752:0011` (for 2x4HD)
- **HID report size:** 64 bytes fixed-length
- **Methodology:** Captured USB HID traffic on macOS while using official plugin, then replayed commands
- **Command format example:** `0x14 [addr_u16] [len_u8]` for reading float parameters
- **Debug capability:** `RUST_LOG=trace` provides frame hex dumps; `minidsp debug send` allows raw command experimentation
- **Earlier Node.js version:** https://github.com/mrene/node-minidsp
- **Python port:** https://github.com/markubiak/python3-minidsp

**This is the closest successful precedent** — same USB HID transport, same device class, fully documented. The `minidsp-rs` codebase is the best reference for implementing a USB HID controller for the T.Racks.

### Behringer DCX2496

- **Protocol:** MIDI SysEx over RS232 serial (NOT USB HID)
- **Baud rate:** 38400, 8N1
- **SysEx header:** `F0 00 20 32 [deviceID] 0E [function] [data] F7`
- **Key projects:**
  - [DuinoDCX](https://github.com/lasselukkari/DuinoDCX) — ESP32 WiFi controller
  - [UltradrivePi](https://github.com/geftactics/UltradrivePi) — Raspberry Pi RS232 controller
- **Protocol document:** http://jipihorn.free.fr/Projets%20en%20cours/Centrale/Doc/DCX%20protocol.pdf

### DBX DriveRack PA2

- **Protocol:** Text-based TCP over network
- **Port:** 19272
- **Discovery:** HiQnet protocol over UDP broadcast
- **Commands:** `get`, `set`, `connect`, `sub` (subscribe)
- **Path format:** `\\Node\Wizard\SV\LoadedConfigString\*`
- **Reference:** https://gist.github.com/ForsakenHarmony/8526cbf73e9bea9cf9811490fb743fc9

### USB Protocol Classes Used by Audio DSP Devices

| Protocol | Devices | Notes |
|----------|---------|-------|
| **USB HID** | miniDSP, T.Racks/Musicrown, many Chinese OEM DSPs | Most common. Fixed 64-byte reports. No driver needed. |
| **USB CDC (Serial)** | Some older/simpler devices | Appears as virtual COM port. |
| **MIDI SysEx** | Behringer DCX2496, DEQ2496 | Over RS232 or USB-MIDI. |
| **TCP/IP (Ethernet)** | DBX DriveRack PA2, installation DSPs | Network-based. |
| **Vendor-specific USB** | Some proprietary implementations | Requires custom drivers. |

---

## 10. Recommended Approach for Linux Support

### Phase 1: Capture HID Report Descriptor

```bash
# Find the hidraw device
ls /sys/class/hidraw/

# Get the HID report descriptor (binary)
cat /sys/class/hidraw/hidraw0/device/report_descriptor | xxd

# Or use hid-recorder (from hid-tools package)
sudo hid-recorder /dev/hidraw0

# Convert to human-readable format
sudo pip install hid-tools
sudo hid-decode /sys/class/hidraw/hidraw0/device/report_descriptor
```

This reveals the HID report structure: report IDs, report sizes, usage pages.

### Phase 2: Capture USB Traffic

**Method A: usbmon + Wireshark (on Linux host with VM)**

```bash
# Load usbmon kernel module
sudo modprobe usbmon

# Find bus number
lsusb | grep 0168

# Start Wireshark on the appropriate usbmon interface
# Filter: usb.idVendor == 0x0168
wireshark -i usbmon1 -f "host 1.5"  # adjust bus.device numbers
```

1. Start capture on Linux host
2. Pass USB device to Windows VM
3. Open T.Racks DSP Processor Editor in the VM
4. Change **one parameter at a time** (e.g., change Input A gain from 0 dB to -1 dB)
5. Stop capture, analyze the HID reports

**Method B: USBPcap (on Windows directly)**

If a Windows machine is available, USBPcap can capture directly while the editor runs natively.

### Phase 3: Correlate with Known Protocol

Compare captured HID report payloads against the known Musicrown binary protocol commands from `dsp-408-ui`:

- Look for the `10 02 ... 10 03 [checksum]` frame structure inside HID reports
- Determine if commands are sent as single HID reports or chunked across multiple reports
- Identify the HID report ID(s) used for command/response
- Check for any HID-specific header bytes wrapping the protocol frames

### Phase 4: Implement Controller

Recommended implementation stack:

**Python (for prototyping):**
```python
import hid

# Open device
device = hid.device()
device.open(0x0168, 0x0821)

# Send command (example: handshake)
device.write([0x00, 0x10, 0x02, 0x00, 0x01, 0x01, 0x10, 0x10, 0x03, 0x11])

# Read response
response = device.read(64)
print(response)
```

**Rust (for production quality):**
- Use the `hidapi` crate (same approach as `minidsp-rs`)
- Reference the `minidsp-rs` architecture for HID communication patterns

### Phase 5: Build UI

- The `dsp-408-ui` Flutter codebase could potentially be adapted
- Replace TCP socket transport with USB HID transport
- Core protocol logic (command encoding/decoding, parameter mapping) should be reusable

---

## 11. Tools & Resources

### USB Analysis Tools

| Tool | Description | Link |
|------|-------------|------|
| **Wireshark + usbmon** | USB packet capture on Linux | Built into kernel |
| **USBPcap** | USB packet capture on Windows | https://desowin.org/usbpcap/ |
| **hid-tools** | HID report descriptor decoder, recorder | `pip install hid-tools` |
| **hidrd-convert** | HID descriptor format converter | Part of `hidrd` package |
| **OpenViszla** | FPGA-based USB protocol analyzer | https://github.com/openvizsla/ov_ftdi |
| **Alex Taradov USB sniffer** | Low-cost LS/FS/HS sniffer | https://github.com/ataradov/usb-sniffer |

### Development Libraries

| Library | Language | Description |
|---------|----------|-------------|
| **HIDAPI** | C | Cross-platform HID library |
| **python-hid** / **hidapi** | Python | Python bindings for HIDAPI |
| **hidapi** crate | Rust | Rust bindings for HIDAPI |
| **node-hid** | Node.js | Node.js bindings for HIDAPI |
| **PyUSB** / **libusb** | Python/C | Lower-level USB access (if HID is insufficient) |

### Reference Documentation

- Linux HIDRAW documentation: https://docs.kernel.org/hid/hidraw.html
- Wireshark USB capture setup: https://wiki.wireshark.org/CaptureSetup/USB
- USB HID reverse engineering guide: https://popovicu.com/posts/how-to-reverse-engineer-usb-hid-on-linux/
- USB reverse engineering (Hackaday): https://hackaday.com/2018/05/25/usb-reverse-engineering-a-universal-guide/
- VirtualBox USB eavesdropping technique: https://slomkowski.eu/tutorials/eavesdropping-usb-and-writing-driver-in-python/

### Key Repositories

| Repository | Relevance |
|------------|-----------|
| [Aeternitaas/dsp-408-ui](https://github.com/Aeternitaas/dsp-408-ui) | **Same manufacturer protocol** (TCP transport). Protocol docs, Wireshark dissector, pcap analysis scripts. |
| [mrene/minidsp-rs](https://github.com/mrene/minidsp-rs) | **Same transport layer** (USB HID). Best reference for HID communication patterns. |
| [mrene/node-minidsp](https://github.com/mrene/node-minidsp) | Earlier Node.js miniDSP implementation. |
| [markubiak/python3-minidsp](https://github.com/markubiak/python3-minidsp) | Python miniDSP implementation. |
| [lasselukkari/DuinoDCX](https://github.com/lasselukkari/DuinoDCX) | Behringer DCX2496 controller (different protocol, but similar device class). |

---

## 12. Forum Threads & Community Discussions

| Source | Topic | Key Finding |
|--------|-------|-------------|
| [WineHQ Forums](https://forum.winehq.org/viewtopic.php?t=34000) | T.Racks DSP HID under Wine | USB IDs confirmed (`0168:0821`). Wine's winebus cannot bridge HID to the Windows editor. |
| [Tuxicoman blog](https://tuxicoman.jesuislibre.net/2021/05/thomann-t-racks-mini-dsp-4x4.html) | T.Racks Mini DSP 4x4 on Linux | Confirmed USB HID identity. Author used Windows VM (GNOME Boxes) as workaround. |
| [Audiofanzine (French)](https://fr.audiofanzine.com/mao/forums/t.734120,configuration-dsp-4x4-mini-sous-linux.html) | Configuration DSP 4x4 Mini sous Linux | Device recognized as hidraw. Wine shows "Link Broken" scanning message. |
| [debianforum.de](https://debianforum.de/forum/viewtopic.php?t=190190) | Steuersoftware T.Racks DSP | DSP 204 owner tried RS232 via minicom at 9600 baud; eventually used Wine + Ethernet. |
| [diyAudio - teardown](https://www.diyaudio.com/community/threads/t-racks-4x4-minidsp-undressed.394296/) | Hardware teardown | Chip identification attempts. DSP markings removed. PCM5102A DACs, PCM1802 ADC. |
| [diyAudio - newbie](https://www.diyaudio.com/community/threads/t-racks-dsp-4x4-mini-newbie-questions.341676/) | General usage | Usage discussion and tips. |
| [Audio Science Review](https://www.audiosciencereview.com/forum/index.php?threads/thomann-t-racks-dsp-4x4-mini-review.33306/) | Measurements | Objective measurements and review of DSP 4x4 Mini. |
| [Lautsprecherforum.eu](https://www.lautsprecherforum.eu/viewtopic.php?style=2&t=7774) | DSP 4x4 Mini review | German-language user review. |

---

## 13. Conclusions & Next Steps

### Summary

| Aspect | Status |
|--------|--------|
| OEM manufacturer identified | **Yes** — Musicrown (Dongguan, China) |
| USB interface documented | **Yes** — HID, VID `0168`, PID `0821` |
| Binary command protocol decoded | **Yes** — via `dsp-408-ui` project (TCP transport for DSP 408) |
| USB HID report framing documented | **No** — this is the key missing piece |
| Native Linux controller | **No** — does not exist yet |
| Wine compatibility | **No** — HID passthrough fails |

### What's Already Solved

The hard part — understanding the Musicrown binary command protocol (frame structure, command codes, parameter encoding for EQ/gain/crossover/routing/metering/presets) — is **already done** by the `dsp-408-ui` project.

### What Remains

1. **Capture the HID report descriptor** from the DSP 4x4 Mini to understand report IDs and sizes
2. **Capture USB HID traffic** while the Windows editor communicates with the device
3. **Determine the HID transport framing** — how binary protocol frames are packed into HID reports (likely straightforward — possibly just raw bytes in a single 64-byte report with padding)
4. **Implement a Linux controller** using Python/HIDAPI for prototyping, with potential Rust/Flutter port for production use

### Estimated Effort

Given that the protocol is already known and USB HID is a well-understood transport:
- HID capture and framing analysis: **1-2 days** (requires Windows install or VM)
- Basic Python CLI controller: **1-2 days** after framing is understood
- Full GUI application: **1-2 weeks** (or adapt `dsp-408-ui` Flutter codebase)

### Critical Path

The single blocking dependency is access to a **Windows installation** (VM or bare metal) with the official T.Racks DSP Processor Editor to capture USB HID traffic. Everything else can proceed once the HID report framing is understood.
