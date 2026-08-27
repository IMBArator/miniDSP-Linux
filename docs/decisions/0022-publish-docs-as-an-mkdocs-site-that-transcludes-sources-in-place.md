---
status: accepted
date: 2026-05-17
decision-makers: Maximilian Zettler
---

# Publish docs as an MkDocs Material site that transcludes sources in place

## Context and Problem Statement

The project's documentation is genuinely good but was scattered by design:
`README.md` at the root, the protocol spec and feature list in `analysis/`
(next to their evidence), the analyzer reference in `dspanalyze/USAGE.md`
(next to its code), and API knowledge in docstrings. Publishing a browsable
site should not mean moving those files — their locations are part of the
repository's logic — nor maintaining copies.

## Decision Drivers

* Single-sourcing: every page must have exactly one editable original, in the
  place where it is naturally maintained.
* The API surface (`DSPmini`, `protocol.py` helpers) is the product for
  library consumers and was already docstring-documented (`84e7f68`); it
  should render without per-module stub maintenance.
* Docs tooling must stay out of the runtime install.

## Considered Options

* MkDocs Material with include-markdown transclusion stubs + mkdocstrings +
  gen-files/literate-nav for a generated API reference
* Move all docs into `docs/` and publish that
* Sphinx with MyST
* README-only, no site

## Decision Outcome

Chosen option: **MkDocs Material with transclusion** (`4e2b514`). Files under
`docs/` are thin stubs that `include-markdown` fills from the real sources at
build time; `docs/gen_ref_pages.py` walks both packages and generates one API
page per module; a custom hook (`docs/hooks.py`) rewrites cross-source
relative links and drops the literate-nav SUMMARY from output. Docs
dependencies live behind the `docs` extra, pinned `mkdocs<2.0` ahead of the
announced plugin-removing 2.0 release. CHANGELOG joined the site the same way
(`e679606`). Deployment is `mkdocs gh-deploy` from the publish script
([ADR-0023](0023-write-release-automation-in-plain-bash-against-the-github-api.md)).

### Consequences

* Good, because `protocol.md` keeps living beside the captures that justify
  it, yet renders on the site — the single-source rule survived publication.
* Good, because API pages regenerate from docstrings; adding a module needs
  no docs edit.
* Good, because the runtime install is untouched — `uv sync` without extras
  pulls no docs tooling.
* Bad, because the hook layer (link rewriting, SUMMARY suppression) is bespoke
  build logic that must be understood before restructuring docs.
* Neutral, because transclusion means a page's *rendered* neighbourhood
  differs from its *source* neighbourhood; the hooks absorb most, not all, of
  the link mismatch risk.

### Confirmation

`make docs` builds warning-free (asserted in `e679606`); the stubs under
`docs/` contain only include directives; `site/` is gitignored.

## More Information

* `4e2b514` — the full design rationale; `84e7f68` — the docstring expansion
  that made the API reference worth generating; `e679606`, `cb8e1a6` —
  follow-ups; miniDSP-Linux-qt ADR-0029 — sibling decision.
