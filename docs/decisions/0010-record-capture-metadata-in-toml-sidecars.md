---
status: accepted
date: 2026-04-04
decision-makers: Maximilian Zettler
---

# Record per-capture metadata in .meta.toml sidecar files

## Context and Problem Statement

The capture corpus grew past twenty files with names like
`capture_20260409_213417_output_peq_gain.pcapng`. Answering "which capture
demonstrates X?" or "has this file been re-analyzed since the PEQ fix?"
required opening each file in the analyzer. The corpus needed an inventory
that stays truthful as knowledge changes.

## Decision Drivers

* Captures are evidence ([ADR-0001](0001-verify-every-protocol-claim-against-device-captures.md));
  evidence needs a catalogue.
* Whether a capture contains *unknown* opcodes is exactly the signal that
  directs the next reverse-engineering session — and it changes when the
  protocol map improves.
* Binary pcapng files are opaque in diffs and listings; their descriptions
  should be text under version control.

## Considered Options

* A generated `.meta.toml` sidecar per capture, refreshed on each analyze run
* A single hand-maintained inventory table in `protocol.md`
* No metadata; rely on file naming

## Decision Outcome

Chosen option: **sidecars** (`9c615a9`). `dspanalyze analyze` writes a
`.meta.toml` next to each capture with stats, opcode counts, an
`has_unknown_opcodes` flag, and a `last_analyzed` timestamp;
`dspanalyze list-captures` renders the corpus from the sidecars (`18029f6`).
Re-analysis updates the sidecar, so recognition of a formerly unknown opcode
is visible as a plain diff (`886fb3d` after the 0x2d discovery).

The prose capture index in `protocol.md` still exists for narrative context
(what was being tested and what it proved); the sidecars carry the mechanical
facts.

### Consequences

* Good, because "what does this capture contain and when did we last look"
  is answerable without opening Wireshark.
* Good, because sidecar diffs document knowledge progress (unknown → known)
  in the git history.
* Neutral, because `last_analyzed` bumps generate churn commits after bulk
  re-analysis (`bc57449`, `6ce7ba6`, `c322f91`).
* Bad, because sidecars can go stale if analyze isn't re-run; the timestamp
  makes that visible but doesn't prevent it.

### Confirmation

Every `.pcapng` under `analysis/usb_captures/` has a committed `.meta.toml`;
`dspanalyze list-captures` fails loudly on missing metadata.

## More Information

* `9c615a9`, `18029f6`, `886fb3d`, `bc57449`.
