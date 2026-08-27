---
status: accepted
date: 2026-08-27
decision-makers: Maximilian Zettler
---

# Record architectural decisions as MADR files

## Context and Problem Statement

This repository carries two kinds of hard-won knowledge: the reverse-engineered
protocol itself (documented in [protocol.md](../protocol.md)) and the *decisions*
about how the library, the analysis toolchain, and the release machinery are
built. The first kind is well documented; the second lived only in unusually
detailed commit messages and scattered prose. Several positions were reversed
along the way (the bundled GUI, the ignored `uv.lock`, fire-and-forget ACKs,
regenerating the changelog), and nothing recorded what the current position is
or why the previous one was abandoned.

The sibling project [miniDSP-Linux-qt](https://github.com/IMBArator/miniDSP-Linux-qt)
already keeps an MADR log (its ADR-0000) and has found it useful for exactly
this purpose.

## Decision Drivers

* Decisions with lasting consequences should be findable without reading ~140
  commit bodies.
* Reversals need first-class records so settled questions are not re-litigated.
* Both sibling projects should use the same convention, so a reader of one log
  can navigate the other.
* The project already publishes an MkDocs site, so records should render there
  at no extra cost.

## Considered Options

* Markdown Any Decision Records (MADR), matching the Qt project
* Nygard's original lightweight ADR template
* A single long `DECISIONS.md`
* Continue relying on commit messages

## Decision Outcome

Chosen option: **MADR**, one file per decision under `docs/decisions/`,
numbered `NNNN-title-with-dashes.md`. The template
([adr-template.md](adr-template.md)) is copied verbatim from miniDSP-Linux-qt
so both repositories share one convention. Each record is dated with the day
the decision was *made* (taken from the deciding commit), not the day the
record was written.

### Consequences

* Good, because each decision gets a stable, linkable identity (`ADR-0012`)
  usable from code comments, commits, and the sibling project's records.
* Good, because the records render into the MkDocs site (see
  [ADR-0022](0022-publish-docs-as-an-mkdocs-site-that-transcludes-sources-in-place.md)).
* Neutral, because the initial batch is retrospective: the records cite the
  commits that made each decision, but the reasoning is reconstructed from
  those commits rather than captured at the time.
* Bad, because records go stale silently; keeping them current is a review
  responsibility.

### Confirmation

A decision is recorded if `docs/decisions/` contains a file for it and
[index.md](index.md) lists it.

## More Information

* [MADR project](https://adr.github.io/madr/)
* miniDSP-Linux-qt ADR-0000, which weighs the four options above in detail;
  the same trade-offs apply here and are not repeated.
