# Notes for coding agents

Read [CONTRIBUTING.md](CONTRIBUTING.md) before you change anything. It covers
branches, commits, the checks, the code conventions, protocol work and
releases, and what you must not do. The [README](README.md) explains how to
install and use miniDSP-Linux, and the [developer guide](docs/development.md)
how to set it up, run, test and build it from a checkout.
[docs/architecture.md](docs/architecture.md) explains the design, with the
module map and the invariants. Read the invariants before you change the code
they protect.

Architecture decisions are recorded as MADR files in
[docs/decisions/](docs/decisions/index.md). Read the records of an area before
you propose a change there. When a change makes or reverses a decision, add or
update a record as CONTRIBUTING.md describes, in the same change.

## How to work here

* Protocol docs and protocol code change only with verified results and the
  maintainer's confirmation: show the capture evidence and ask before you
  touch `minidsp/protocol.py`, `dspanalyze/protocol_config.toml`,
  `analysis/protocol.md` or the feature list.
* Decode captures with the committed tools (`make analyze …`,
  `uv run dspanalyze …`), not with ad-hoc scripts or one-liners. If the tools
  lack something you need, suggest extending `dspanalyze` or adding a make
  target.
* Captures are large and mostly level-poll noise: start with
  `make analyze-summary` or `make analyze-no-poll` before you decode a whole
  capture.
* Don't run anything that writes to a connected DSP (restoring a `.unt` file,
  storing presets, setting a PIN) or that needs sudo (`make capture-enable`)
  unless the maintainer asks for it.
* Don't add AI attribution (co-author trailers, "generated with" footers) to
  commits, pull requests or files.
