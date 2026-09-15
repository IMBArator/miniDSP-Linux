# Development

Setup, testing, the protocol-analysis workflow, and the release workflow for
contributors.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — manages the virtual environment and
  dependencies

### Linux

- Kernel HID driver — the library talks to `/dev/hidraw*` directly, no libusb
- Read/write access to `/dev/hidraw*` — see the udev rule under
  [Permissions](index.md#permissions)

### Windows

- No driver installation and no udev equivalent — Windows binds its built-in
  HID driver to the DSP automatically
- [hidapi](https://pypi.org/project/hidapi/) is installed by `uv sync` through
  a `sys_platform == 'win32'` marker, so it lands on Windows only (see
  [ADR-0024](decisions/0024-support-windows-through-a-hidapi-transport.md))
- Wireshark with USBPcap is needed **only** for `dspanalyze capture`, not for
  controlling the device

## Development environment

```bash
git clone https://github.com/IMBArator/miniDSP-Linux.git
cd miniDSP-Linux
uv sync              # creates .venv, installs core deps
uv sync --extra dev  # also installs pytest for development
```

On Windows the same commands run unchanged in PowerShell — install uv with
`winget install astral-sh.uv` first; it provisions Python itself. Prefix
commands with `uv run` (`uv run minidsp dump`, `uv run pytest -v`).

### Testing changes against the Qt GUI

[miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt) consumes
this library as a pinned release wheel. To try local protocol changes in the
GUI before they are released, override the pin **in the Qt checkout**:

```bash
cd ../miniDSP-Linux-qt
uv pip install --reinstall --no-cache ../miniDSP-Linux/
uv run --no-sync minidspqt        # --no-sync keeps the override in place
```

The details (why `--no-cache` matters, how the override is reverted) are in
the Qt project's own
[Development page](https://imbarator.github.io/miniDSP-Linux-qt/development/).

## Running tests

```bash
make sync            # runs `uv sync --extra dev`
make test            # uv run pytest -v
```

No hardware is needed: the device layer is exercised through a `FakeTransport`
(the injection seam introduced with
[ADR-0024](decisions/0024-support-windows-through-a-hidapi-transport.md)),
and the Windows hidapi path runs against a stubbed `hid` module, so the whole
suite behaves identically on Linux and Windows. The protocol tests assert
command builders byte-for-byte against frames from real captures
([ADR-0001](decisions/0001-verify-every-protocol-claim-against-device-captures.md)).

### GNU make on Windows (optional)

`make` is not part of a Windows install. It is not required — every target
that matters day to day is a one-line `uv` invocation you can type directly
(`uv sync --extra dev`, `uv run pytest -v`, `uv build`,
`uv run mkdocs build`). If you prefer the targets, install GNU make (for
example `winget install ezwinports.make`); `sync`, `install`, `test`,
`build`, `docs`, and `docs-serve` are shell-agnostic and work as-is.

`version` and `publish` shell out to bash scripts;
`capture-enable`/`capture-disable` manage usbmon and dumpcap capabilities and
are Linux-only; `clean`, `docs-clean`, and the `analyze-all`/`check-all`
loops need a POSIX shell — or Git Bash, which ships with Git for Windows.

## Protocol analysis workflow

Every protocol claim in this repository is backed by a USB capture
([ADR-0001](decisions/0001-verify-every-protocol-claim-against-device-captures.md)).
The loop for discovering or verifying an opcode:

```bash
# One-time (Linux): load usbmon and grant non-root capture access
make capture-enable

# Record the manufacturer software performing ONE isolated action
uv run dspanalyze capture --output-dir analysis/usb_captures

# Decode it (writes a .meta.toml sidecar next to the capture)
make analyze FILE=analysis/usb_captures/capture_....pcapng
make analyze-no-poll FILE=...     # without 0x40 level-poll noise

# Compare the config reads inside one capture to find changed bytes
make diff-config FILE=...

# Guard existing knowledge: protocol assertions over all captures
make check-all

# Revoke capture access again
make capture-disable
```

Findings then travel together in one pass: `dspanalyze/protocol_config.toml`
(analyzer knowledge), `minidsp/protocol.py` + tests (runtime), and
[protocol.md](protocol.md) (the specification). The full CLI reference is on
the [DSP-Analyze CLI Usage](dspanalyze-usage.md) page; capture inventory
conventions are in
[ADR-0010](decisions/0010-record-capture-metadata-in-toml-sidecars.md).

Two generated package resources have their own regeneration tools:
`minidsp/factory_defaults.toml` via `dspanalyze extract-defaults` (from an
F00-load capture) and `minidsp/calibration.toml` via `dspanalyze calibrate`
(against a known signal source).

## Releasing

The release flow uses two helper scripts under
[`scripts/`](https://github.com/IMBArator/miniDSP-Linux/tree/main/scripts),
wired into the Makefile:

```bash
# 1. Bump version in pyproject.toml + uv.lock, prepend a new CHANGELOG.md
#    section (git-cliff), commit `chore(release): vX.Y.Z`, tag vX.Y.Z,
#    optionally push.
make version VERSION=X.Y.Z

# 2. Push the commit + tag if you skipped the prompt above.
git push && git push origin vX.Y.Z

# 3. Build the artifacts that publish.sh will attach.
make build           # wheel + sdist into dist/

# 4. Create the GitHub Release, upload wheel + sdist, and deploy the docs to
#    GitHub Pages. Needs GITHUB_TOKEN (PAT with `repo` scope) in the
#    environment.
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
make publish         # or: make publish VERSION=X.Y.Z
```

Release notes are extracted from the `## [X.Y.Z]` section of the
[Changelog](changelog.md), which `make version` generates from Conventional
Commits via `cliff.toml` — a hand-curated section survives later releases and
flows to the GitHub Release verbatim
([ADR-0021](decisions/0021-drive-the-changelog-from-conventional-commits-with-git-cliff.md)).
Tags matching `-rc`, `-beta`, or `-alpha` are auto-flagged as prereleases.
`version.sh` refuses to run from a dirty tree, a non-main branch, a duplicate
tag, or a version regression, and previews the changelog before committing
([ADR-0023](decisions/0023-write-release-automation-in-plain-bash-against-the-github-api.md)).

Downstream: the Qt GUI pins this library to a published release wheel (its
ADR-0003), so after publishing a version its PEP 508 pin can be bumped — its
Development page currently lists the v1.3.0 wheel (Windows transport) as its
open release blocker.

## Repository structure

```
minidsp/                  Python control package
  __main__.py             Entry point (delegates to cli.main)
  device.py               Open/close, send/recv, command methods, config read
  transport.py            HID I/O backends: hidraw (Linux), hidapi (Windows)
  protocol.py             Frame encoding/decoding, all command builders
  calibration.toml        Level meter calibration (REF_LEVEL + anchor points)
  factory_defaults.toml   F00 factory-preset parameter values (raw protocol form)
  defaults.py             load_factory_defaults() — parses the bundled TOML
  cli.py                  CLI subcommands: dump, levels, mute, unmute

dspanalyze/               Protocol analysis toolchain
  cli.py                  Entry point: analyze, check, capture, diff-config, list-captures, calibrate, extract-defaults
  calibrate.py            Level meter calibration tool (capture, show, apply, reset)
  extract_defaults.py     Stitch F00 config pages → factory_defaults.json
  protocol_config.toml    All protocol knowledge (opcodes, fields, value formats)
  decode.py               Frame → structured command decoder
  capture.py              tshark-based USB capture with device auto-detect
  check.py                Protocol assertion framework
  readers/                pcapng and Wireshark text export parsers
  output/                 claude / human / raw output formatters

tests/                    Protocol and device-layer unit tests (pytest)
docs/                     MkDocs site sources
  decisions/              Architecture decision records (MADR)
analysis/                 Reverse engineering reference
  protocol.md             Full protocol specification
  feature-list.md         DSP feature inventory with protocol status
  usb_captures/           Wireshark USBPcap captures (.pcapng + .meta.toml)
  resources/              Screenshots, manual PDF

CLAUDE.md                 Agent/contributor working notes
scripts/                  version.sh + publish.sh (release automation)
Makefile                  Targets for test, build, docs, analysis, release
```

## Architecture decisions

Lasting design decisions — and the positions the project abandoned along the
way — are recorded as MADR files under
[Architecture Decisions](decisions/index.md). Read the relevant record before
proposing a change in an area it covers; several document alternatives that
were already tried here.
