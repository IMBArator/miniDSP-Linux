# Development

How to work on miniDSP-Linux from a checkout: set it up, run it, test, check
and build it, and use the protocol-analysis tooling. `make help` lists every
target. How changes get in is in [CONTRIBUTING.md](../CONTRIBUTING.md); how the
code is built inside, and why, is in [architecture.md](architecture.md).

## Requirements

Beyond the [README's requirements](../README.md#requirements) (Python 3.11+,
uv, access to `/dev/hidraw*` on Linux):

- GNU make: the targets are the way to set up, test, check and build. On
  Windows: `winget install ezwinports.make`.
- For protocol analysis: Wireshark's `tshark`; on Linux the `usbmon` kernel
  module (`make capture-enable` loads it), on Windows USBPcap.

## Setting up

```bash
git clone https://github.com/IMBArator/miniDSP-Linux.git
cd miniDSP-Linux
make sync            # .venv with all dependencies, including the dev tools
```

On Windows the same commands run in PowerShell once uv
(`winget install astral-sh.uv`, which provisions Python itself) and GNU make
are installed. hidapi, the Windows HID backend, is installed on Windows only.

## Running from the checkout

```bash
uv run minidsp dump
uv run dspanalyze analyze analysis/usb_captures/<capture>.pcapng --decode
```

## Tests and checks

```bash
make test            # the test suite
make check           # ruff (lint) and ty (types); also make check-ruff, make check-ty
make fix-ruff        # apply ruff's safe automatic fixes
```

No hardware is needed: the device layer runs against a `FakeTransport`, and
the Windows hidapi path against a stubbed `hid` module, so the suite behaves
the same on Linux and Windows. The protocol tests assert the command builders
byte for byte against frames from real captures.

On Linux, `make check-ty` currently reports findings in the Windows-only code
in `minidsp/transport.py` and `dspanalyze/capture.py`; they stay visible until
they are fixed on Windows.

## Building

```bash
make build           # wheel and sdist into dist/
make docs            # the docs site into site/ (MkDocs Material)
make docs-serve      # live preview at http://127.0.0.1:8000
make clean           # remove the build output; make docs-clean removes site/
```

## Windows notes

`sync`, `install`, `test`, `check`, `fix-ruff`, `build`, `docs` and
`docs-serve` work in PowerShell as they are. `version` and `publish` run bash
scripts, and `clean`, `docs-clean` and the `analyze-all`/`analyze-check` loops
need a POSIX shell, for example Git Bash, which comes with Git for Windows.
`capture-enable` and `capture-disable` are Linux-only.

## Protocol analysis workflow

The loop for discovering or verifying an opcode. What has to happen with the
results is in
[CONTRIBUTING.md](../CONTRIBUTING.md#protocol-work-the-device-and-releases);
every command is described in [DSPanalyze CLI Usage](../dspanalyze/USAGE.md).

```bash
# One-time (Linux): load usbmon and grant non-root capture access
make capture-enable

# Record the manufacturer's editor performing ONE isolated action
uv run dspanalyze capture -d "what was done" -n "notes"

# Decode it (writes a .meta.toml sidecar next to the capture)
make analyze FILE=analysis/usb_captures/capture_....pcapng
make analyze-no-poll FILE=...     # without the 0x40 level-poll noise
make analyze-summary FILE=...     # statistics only

# Compare the config reads inside one capture to find the changed bytes
make diff-config FILE=...

# Protocol assertions, for one capture or for all of them
uv run dspanalyze check analysis/usb_captures/capture_....pcapng
make analyze-check                # names every failing capture, fails if any did

# Revoke capture access again
make capture-disable
```

Two package resources have their own tools: `minidsp/factory_defaults.toml`
is regenerated with `uv run dspanalyze extract-defaults` from an F00-load
capture, and `minidsp/calibration.toml` is fitted with
`uv run dspanalyze calibrate` against a known signal source (the steps are in
the [README](../README.md#level-meter-calibration-dspanalyze-calibrate)).

## Testing changes in the Qt GUI

[miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt) uses this
library as a pinned release wheel. To try local changes in the GUI before a
release, install this checkout into the Qt project's environment; how to do
that, and how to undo it, is on the Qt project's
[Development page](https://imbarator.github.io/miniDSP-Linux-qt/development/).
