---
status: accepted
date: 2026-04-04
decision-makers: Maximilian Zettler
---

# Build a dedicated analysis package (dspanalyze) instead of throwaway scripts

## Context and Problem Statement

Early protocol work was done with one-off scripts (`analysis/extract_hid.py`,
`extract_gain_commands.py`) run against Wireshark text exports. Every new
question meant a new script or a hand-edited old one; results were not
reproducible, decoding knowledge was duplicated per script, and nothing
verified that new discoveries didn't contradict old ones. With dozens of
capture sessions planned, the analysis process itself needed engineering.

## Decision Drivers

* Reverse engineering is iterative: the same captures get re-analyzed as
  knowledge improves, so analysis must be repeatable.
* Decoding knowledge should live in one place, not be re-embedded per script.
* The workflow spans capture → decode → diff → assert; ad-hoc scripts cover
  one step each and compose poorly.
* `CLAUDE.md` codifies the working rule: prefer committed tools over one-off
  one-liners so runs are reproducible.

## Considered Options

* A proper installable package (`dspanalyze`) with subcommands for the whole
  workflow
* Keep growing per-question scripts in `analysis/`
* Analyze inside Wireshark with custom Lua dissectors

## Decision Outcome

Chosen option: **the `dspanalyze` package**, built in five deliberate phases
(`e6a6cbe`…`18029f6`): analyze (decode any capture), pcapng reading + metadata
sidecars, check (assertions), capture (tshark orchestration with device
auto-detect), and list-captures. Later additions (`diff-config` `c6e8485`,
`calibrate` `595666e`, `extract-defaults` `7d8253e`) slotted into the same
CLI. The legacy scripts were deleted once superseded (`9d897cc`). Repeatable
invocations are wrapped as Makefile targets (`make analyze FILE=...`).

This reverses the original scripts-in-`analysis/` position.

### Consequences

* Good, because every capture in the repository can be re-decoded with current
  knowledge in one command — which is how several early misreadings were
  caught.
* Good, because the tool has its own tests (`tests/test_dspanalyze/`), so the
  analysis itself is trustworthy.
* Good, because output modes serve their consumers explicitly (`claude` for
  LLM-assisted analysis, `human` tables, `raw` hex).
* Neutral, because the analyzer ships in the same distribution as the runtime
  library even though end users rarely need it.
* Bad, because tooling investment competes with actual protocol work — five
  phases of CLI before the next opcode was decoded.

### Confirmation

`pyproject.toml` installs the `dspanalyze` entry point; the Makefile targets
delegate to it; the legacy scripts are gone from `analysis/`.

## More Information

* `e6a6cbe`, `9c615a9`, `e3cd9a9`, `8cb82fb`, `18029f6` — the five phases;
  `9d897cc` — legacy script deletion; `dspanalyze/USAGE.md` — full CLI
  reference.
