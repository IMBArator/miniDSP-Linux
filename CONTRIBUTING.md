# Contributing to miniDSP-Linux

This guide is about how a change gets into miniDSP-Linux: branches, commits,
what to check before you commit, and the conventions the code follows.
Everything else lives elsewhere and isn't repeated here: how to install and use
the project is in the [README](README.md), how to set it up and work on it from
a checkout is in the [developer guide](docs/development.md), and how it is
built inside, and why, is in [docs/architecture.md](docs/architecture.md).

## Branches

Finished work lives on `main`, and every release is tagged there. For anything
bigger than a small fix, such as a feature or a larger refactoring, start a
branch from `main` called `feature/<name>` and merge it back when it's done.

`gh-pages` is different: it holds the published docs site and is written by
`make publish`, so nobody edits it by hand.

Before you change anything, check which branch you're on.

## Commits

Keep each commit to one topic. The code, its tests and the docs that describe
it go together; unrelated changes go into separate commits. That keeps the
history readable and makes a single change easy to revert.

Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): subject`, in lower case and without a full stop, for example
`fix(device): retry the init handshake`. The scope names the module, the
command or the kind of document (`readme`, `decisions`).

| Type | Use it for |
|---|---|
| `feat` | new behaviour |
| `fix` | a bug fix |
| `refactor`, `perf` | changes that don't alter behaviour |
| `docs` | documentation |
| `test` | tests only |
| `build`, `chore` | tooling, dependencies, housekeeping; `chore(release)` is the release commit |
| `data` | USB captures with their `.meta.toml` metadata files |

Add a body when the reason for a change isn't obvious from the diff.

Stage files by name rather than with `git add .`, so nothing generated slips
in: build output (`dist/`, `site/`), caches and virtual environments never
belong in a commit. Keep local paths, home directories and personal tool
settings out of documents, code, comments and commit messages, too; not
everybody who reads the project can see them.

## Before you commit

Run `make test` and `make check`; both have to pass. Always go through the make
targets, in your shell as well as in docs and commit messages, rather than
calling pytest, ruff or ty yourself: the Makefile is the one place that decides
the flags and paths, so everybody runs the same thing. How to set it all up is
in the [developer guide](docs/development.md).

Some things belong in the same commit as your change:

- **Tests.** When behaviour changes, the tests change with it. A regression
  test says which bug it guards against.
- **Docs.** Update the README when commands or setup change for users, the
  developer guide when the development setup changes, and
  [docs/architecture.md](docs/architecture.md) when the design, a module's job
  or an invariant changes. Please don't state the number of tests anywhere; it
  is out of date with the next commit.
- **A decision record**, when the change makes or reverses a decision (see
  [Architecture decisions](#architecture-decisions)).

The changelog is written from the commit subjects by git-cliff when a release
is made: `feat` becomes "Added", `fix` "Fixed", `refactor` and `perf`
"Changed", `docs` "Documentation", and the other types are left out. So choose
the type by what a reader of the changelog should learn, and write the subject
for them. Whatever is edited by hand in `CHANGELOG.md` survives later releases.

## Code

The project uses Python 3.11 (set in `pyproject.toml`), uv for the environment
and Hatchling for the build; `uv.lock` is committed. Two packages sit side by
side: `minidsp/`, the library with its command line tool, and `dspanalyze/`,
the analysis toolchain. The tests live in `tests/`.

- Every module that contains code starts with
  `from __future__ import annotations` (ruff checks this), and docstrings use
  the Google style, because the API reference on the docs site is generated
  from them.
- Modules log through `log = logging.getLogger(__name__)` and never configure
  logging themselves; which code may do that is one of the
  [invariants](docs/architecture.md#invariants).
- Command line tools use `argparse` subcommands, each with
  `set_defaults(func=...)` and a `help=` text.
- Fix ruff and ty findings instead of silencing them: no `# noqa`, no
  `# ty: ignore`, and no settings that switch a check off. When ty complains
  that a value might be `None`, check it with an `assert`; when it doesn't
  accept a test fake, make the fake a subclass of the real class or `cast` it
  where it is passed in.
- Tests are plain `test_*` functions in modules that have a docstring and are
  divided by `# --- section ---` comments. Small fakes and `monkeypatch` are
  preferred over fixtures. A test that needs something from the system (a
  program, a device) checks for it and skips when it's missing.
- New protocol knowledge in `minidsp/protocol.py` gets a comment with the raw
  hex bytes and what they control, including byte offsets and value ranges.
  Capture analysis and notes go in `analysis/`, application code in
  `minidsp/`. Which files a new command, assertion, transport or output format
  touches is described under
  [How things plug in](docs/architecture.md#how-things-plug-in).

## Protocol work, the device and releases

The [invariants](docs/architecture.md#invariants) in the architecture document
are the rules no change may break, for example that nothing ever overwrites
the factory preset F00. Please read them before you change the code they
protect: a change that breaks one is wrong even when every test passes.

Protocol knowledge comes only from captures of the manufacturer's editor:

- Capture one isolated action at a time, and commit each capture together with
  its `.meta.toml` metadata file as a `data:` commit. That way the evidence for
  every protocol claim is in the repository. The commands are in the developer
  guide's
  [protocol analysis workflow](docs/development.md#protocol-analysis-workflow).
- When a finding is confirmed, it lands in one go: in
  `dspanalyze/protocol_config.toml`, in `minidsp/protocol.py` with its tests,
  in [protocol.md](analysis/protocol.md) and in the
  [feature list](analysis/feature-list.md).
- Protocol docs and protocol code only change with verified results and after
  the maintainer has agreed.

Releases and publishing are done by the maintainer:

1. `make version VERSION=X.Y.Z` sets the new version (in `pyproject.toml`,
   `uv.lock` and both packages), adds the changelog section, and commits and
   tags the release. The script refuses to run on a dirty working tree, for an
   existing tag or for a version that already has a changelog section. It asks
   before tagging from a branch other than `main` or a version below the
   latest, and it pushes only after an explicit yes, never when it doesn't run
   in a terminal.
2. Push the commit and the tag, if the script didn't.
3. `make build` puts the wheel and the sdist into `dist/`.
4. `make publish` (with a `GITHUB_TOKEN` that has `repo` scope) creates the
   GitHub Release from the changelog section, attaches the wheel and the sdist,
   and deploys the docs to GitHub Pages. Versions with `-rc`, `-beta` or
   `-alpha` become prereleases.

After a release, the Qt GUI can move its pin to the new wheel.

## Architecture decisions

Decisions with lasting consequences are recorded in
[docs/decisions/](docs/decisions/index.md), one Markdown file per decision in
the [MADR](https://adr.github.io/madr/) format. They answer "why is it like
this?" without digging through the commit history, and they keep settled
questions from being reopened by accident. Before you propose a change in an
area, read its records.

Write a record when a change chooses between real alternatives that someone
might later question (a library, a file format, a protocol, a security
mechanism), when it constrains future work, or when it reverses an earlier
decision. If you're unsure, ask yourself whether undoing it later would be
costly or confusing without knowing why it was made. Bug fixes, refactorings
and small features don't need a record, and neither does anything that only
follows the conventions in this guide; records are for the project's own
choices and for every deviation from these conventions.

To write one, copy [the template](docs/decisions/adr-template.md) to the next
free number (`NNNN-title-with-dashes.md`) and fill it in. Keep it to one
decision and about a page: the problem, the options you really had, the choice
and its consequences. Date it with the day the decision was made; if you write
it later, say so and name the commit that made it. The current design, how-tos
and protocol details don't belong in a record; link to where they live. Then
add the record to the [index](docs/decisions/index.md), and update
[docs/architecture.md](docs/architecture.md) if it changes the picture there.

An accepted record is never rewritten. When a decision changes, write a new
record, mark the old one `superseded by ADR-NNNN` and link both ways. Small
additions that don't change the decision, such as a follow-up commit or a
known limitation, go into the old record's "More Information".
