# Architecture Decisions

This directory holds the project's architecture decision records, written in
the [MADR](https://adr.github.io/madr/) format — one file per decision, each
stating the problem, the options that were actually available, and why one was
chosen. The convention and template are shared with the sibling project
[miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt).

The records were written retrospectively from the commit history and the
existing documentation. They describe real decisions and cite the commits that
made them, but the reasoning is reconstructed rather than captured at the
time. Each record is dated with the day the decision was made. See
[ADR-0000](0000-record-architecture-decisions-as-madr-files.md) for why the
log exists.

To add a record, copy [adr-template.md](adr-template.md) to the next number and
add a line to the relevant table below.

## Scope and foundation

| ADR | Decision |
|-----|----------|
| [0001](0001-verify-every-protocol-claim-against-device-captures.md) | Verify every protocol claim against device captures before documenting or implementing it |
| [0002](0002-speak-to-the-device-through-hidraw-without-a-usb-library.md) | Speak to the device through /dev/hidraw without a USB library |
| [0003](0003-license-under-gpl-3-0.md) | License under GPL-3.0 with an interoperability notice |
| [0004](0004-keep-this-repository-library-first-and-develop-the-gui-separately.md) | Keep this repository library-first; develop the GUI in a separate repository |
| [0005](0005-cross-reference-dsp-408-ui-but-trust-only-on-device-verification.md) | Cross-reference dsp-408-ui, but trust only on-device verification |

## Analysis toolchain

| ADR | Decision |
|-----|----------|
| [0006](0006-build-a-dedicated-analysis-package-instead-of-throwaway-scripts.md) | Build a dedicated analysis package (dspanalyze) instead of throwaway scripts |
| [0007](0007-encode-protocol-knowledge-in-a-declarative-toml.md) | Encode the analyzer's protocol knowledge in a declarative TOML file |
| [0008](0008-drive-usb-capture-and-parsing-through-tshark-subprocesses.md) | Drive USB capture and pcapng parsing through tshark subprocesses |
| [0009](0009-guard-protocol-knowledge-with-capture-assertions.md) | Guard protocol knowledge with an assertion framework over captures |
| [0010](0010-record-capture-metadata-in-toml-sidecars.md) | Record per-capture metadata in .meta.toml sidecar files |
| [0011](0011-make-minidsp-protocol-the-single-source-of-conversions-and-constants.md) | Make minidsp.protocol the single source of truth for conversions and constants |

## Runtime library

| ADR | Decision |
|-----|----------|
| [0012](0012-serialise-device-access-with-an-exclusive-flock-on-the-hidraw-fd.md) | Serialise device access with an exclusive flock on the hidraw fd |
| [0013](0013-fail-fast-on-unready-devices-and-retry-the-init-handshake.md) | Retry the init handshake at open, and fail fast when the device is not ready |
| [0014](0014-raise-typed-oserror-subclasses-for-device-failures.md) | Raise typed exceptions for device failure states |
| [0015](0015-validate-every-device-response-instead-of-fire-and-forget.md) | Validate every device response instead of fire-and-forget |
| [0016](0016-refuse-to-overwrite-the-factory-preset-slot.md) | Refuse to overwrite the factory preset slot in the library |
| [0017](0017-bundle-factory-defaults-as-a-package-resource-in-raw-protocol-form.md) | Bundle factory defaults as a generated TOML package resource in raw protocol form |
| [0018](0018-add-observability-with-stdlib-logging-behind-verbosity-flags.md) | Add observability with stdlib logging behind -v/-vv, configured only at the entry point |
| [0019](0019-ship-level-meter-calibration-as-an-editable-package-resource.md) | Ship level-meter calibration as an editable package resource with a fitting workflow |
| [0024](0024-support-windows-through-a-hidapi-transport.md) | Support Windows through a platform-selected hidapi transport |

## Build, release, and documentation

| ADR | Decision |
|-----|----------|
| [0020](0020-manage-the-project-with-uv-and-hatchling.md) | Manage the project with uv and Hatchling, and commit the lockfile |
| [0021](0021-drive-the-changelog-from-conventional-commits-with-git-cliff.md) | Drive the changelog from Conventional Commits with git-cliff, prepending to a hand-curatable file |
| [0022](0022-publish-docs-as-an-mkdocs-site-that-transcludes-sources-in-place.md) | Publish docs as an MkDocs Material site that transcludes sources in place |
| [0023](0023-write-release-automation-in-plain-bash-against-the-github-api.md) | Write release automation in plain bash against the GitHub API |

## Decisions that reversed an earlier position

Several records document a position the project actively abandoned. These are
the most useful entries to read before proposing a change in the same area,
because the alternative has already been tried here.

| ADR | Previous position | Why it was abandoned |
|-----|-------------------|----------------------|
| [0004](0004-keep-this-repository-library-first-and-develop-the-gui-separately.md) | PySide6 GUI bundled in this repo behind a `gui` extra | Coupled release cadence and dependencies; the GUI needed its own architecture and packaging |
| [0006](0006-build-a-dedicated-analysis-package-instead-of-throwaway-scripts.md) | Per-question scripts in `analysis/` | Not reproducible; decoding knowledge duplicated per script |
| [0011](0011-make-minidsp-protocol-the-single-source-of-conversions-and-constants.md) | Conversion formulas copied per package | The analyzer's `q_log` copy drifted (divided by 255 instead of 100) |
| [0013](0013-fail-fast-on-unready-devices-and-retry-the-init-handshake.md) | Silently accept init timeouts | 20+ seconds of doomed commands before the caller noticed |
| [0015](0015-validate-every-device-response-instead-of-fire-and-forget.md) | Fire-and-forget activate; naive ACK check on preset name | Store-preset failed every time because 0x26 answers with a 16-byte echo, not an ACK |
| [0018](0018-add-observability-with-stdlib-logging-behind-verbosity-flags.md) | Silent failure swallowing plus a hardcoded `basicConfig(DEBUG)` in the GUI | Undiagnosable CLI failures; library overrode the host application's logging |
| [0020](0020-manage-the-project-with-uv-and-hatchling.md) | setuptools + pip; `uv.lock` in `.gitignore` | Lockfile determinism won; the ignore was reverted a week later |
| [0021](0021-drive-the-changelog-from-conventional-commits-with-git-cliff.md) | Regenerate CHANGELOG.md wholesale; skip docs commits | Wiped hand-curated sections; docs corrections are user-visible in a spec-centric project |
