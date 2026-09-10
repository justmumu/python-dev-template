# Template architecture

The root repository develops and tests the generator. `template/` contains the
Python application it emits. Copier provides validation, rendering, recorded answers and
updates; `scripts/bootstrap.py` adapts it to GitHub's first-run workflow.

```text
copier.yml                  Questions, defaults and validators
reserved-package-names.json  Python and development namespace exclusions
template/                   Generated Python application
scripts/bootstrap.py        Stage, validate and install GitHub's first-run output
scripts/development.mk      Shared Make recipes for both repositories
scripts/hooks/              Shared Claude/Codex metadata guard and Git hooks
tests/                      Rendering, bootstrap, update and policy contracts
docs/                       Public generator documentation
```

The root `pyproject.toml` depends on Copier and has no application package entrypoint.
The emitted `pyproject.toml` uses uv_build and a project-specific console script, with no required
runtime dependencies. Ruff's entire lint and formatting policy is identical in both projects;
strict type checking and the 80% branch coverage threshold are preserved. Only
the source paths and generator-specific test configuration differ.

## Shared sources

Jinja includes reuse the root permission hooks, host settings, Git hook
configuration, Make recipes, formatting and release helpers, and common contributor
guides. Each Makefile declares its source and coverage targets, then includes
`scripts/development.mk`; only the generator adds `test-integration`. The generated
getting-started guide reuses the root guide with the project's repository details.
A shared file is maintained once. Project-specific files, including Python metadata, README,
runtime code and MkDocs configuration, live under `template/`.

Included sources are parsed by Jinja. Avoid literal Jinja delimiters in shared
files or explicitly escape them. The generator does not scan and replace strings
throughout an existing repository or rewrite TOML after rendering.

The reserved-name catalog covers the union of Python 3.11–3.13 standard modules,
Python keywords, project helper packages, and emitted development/docs dependency
imports and distribution names. Keep it current when changing supported Python
versions or tooling; the CI matrix checks each interpreter’s standard modules.
The validator reads this data with normal Jinja includes, without custom
extensions or executable Copier tasks.

## Verification

`make check` runs the generator's formatting, lint, type and fast test gates.
Fast tests cover single-word and hyphenated project names, escaping, rejected input, exact quality
policy parity, recorded provenance, safe first-run installation and real Copier
updates with and without conflicts.

```bash
make test-integration
```

The integration suite exercises local generation and GitHub bootstrap. Each
generated project runs its own `make check`, documentation build and package
build. The suite installs its wheel outside the source tree and verifies console and
module entrypoints, help text, logging configuration and argument errors.
Template source files are excluded from ordinary root formatter runs because
their Jinja syntax is not the emitted file syntax; generated output runs the
full gates. The integration suite validates actual Python 3.11, 3.12 and 3.13
environments. Local type checking always covers all three targets, while local
tests run once in the selected interpreter.

Bootstrap requires a clean target with `.github/.template-pending`, refuses the
original template repository, preserves `.git` and ignored local files, and
rejects file collisions and symlinks. It installs only the rendered manifest plus
the uv-generated lock, leaving temporary environments and build products behind.
I/O failures during installation restore the tracked files from a temporary
backup. If restoration itself fails, it retains the backup and reports its path
for manual recovery. Index flags that can hide local changes are also rejected.
This is a first-run adapter, not an updater for established projects.

GitHub setup renders from the copied repository at its current commit without
contacting the upstream template. Copier records the relative source `.` and
that genuine local revision. The initial template remains in project history;
later updates fetch upstream commits into `refs/remotes/template/main` and use
Copier's normal three-way merge. This avoids an extra setup secret, duplicate
source snapshots, or manually rewritten answers. Regression tests cover unrelated
GitHub initial history, fresh clones, consecutive updates and merge conflicts.

Publish the first Copier-compatible release only after this migration is merged
and verified. Documentation specifies an explicit source ref until a compatible release is
available, instead of relying on Copier's latest-tag default.

## Documentation and releases

Both projects use uv-installed MkDocs Material, Markdown pages under `docs/`,
and strict link validation. Generated projects additionally use mkdocstrings to
render their configuration, error and CLI APIs from Python docstrings.
The root generator documents creation, updates and architecture instead.

New projects start at `0.0.0`, independently of the generator's own version.
Copier records the initial version so later template updates preserve released
application versions. Projects made by the previous initializer require a
reviewed migration before they can use Copier updates.

Commitizen generates changelogs from Conventional Commits. The release helper
uses uv for version changes and creates an annotated local tag only after the
release commit succeeds. Generated applications exclude inherited template
history from their changelogs. See the [release process](../contributing/release-process.md)
for the PR, merge, tag push and automatic GitHub Release sequence.
