# Getting started

If you're contributing to this project for the first time, here's the minimum
to get up and running.

## Prerequisites

Install [uv](https://docs.astral.sh/uv/), Git and Make on macOS, Linux or WSL.
uv installs the selected Python interpreter and project tools; you do not need
to install Node.js, npm or a separate documentation toolchain. Pyright's Python
package manages its own runtime.

## Clone and set up

```bash
git clone https://github.com/justmumu/python-dev-template.git
cd python-dev-template
make setup
```

`make setup` completes the initial setup:

- `make install` installs the locked development and documentation dependencies
  into `.venv/`. A freshly generated project initializes its missing `uv.lock`
  through uv first.
- The project formatters normalize generated Markdown, TOML, YAML and JSON.
- Git hooks are installed for pre-commit, pre-push and commit-msg.

Use `make install` when you only need to refresh dependencies, as CI does.
Commit `uv.lock` and `.copier-answers.yml` in generated projects.

## Finish a new project's setup

If you just created a Python project from this template:

- Replace the argparse demo with your application's behavior.
- Customize the README, docs landing page, logo and colors.
- Add the `python` repository topic and enable **Discussions** under Settings →
  Features; the issue-template contact link points to Discussions.
- If you publish the docs, set `site_url` in `mkdocs.yml` to their public URL and
  expand `nav` as you add pages.
- Configure branch protection, regular merge commits and automatic branch deletion.
- Keep `main` as the default branch; CI push triggers and the release workflow use it.
- Keep Actions enabled. GitHub's automated setup commit does not trigger another
  CI run; the setup workflow validates the project before creating that commit.
  Normal CI runs on pushes to `main` and on pull requests.

Keep `.copier-answers.yml` committed so you can apply future template updates.
Complete the development gate and agent setup below before starting development.

## The development gate

Run before any PR:

```bash
make check       # lock + format + lint + strict typing + tests/coverage
make docs-build  # MkDocs strict build, including internal links and anchors
```

Both commands also run on `git push` through the pre-push hook. CI verifies the
same checks independently.

The local interpreter defaults to Python 3.13 through `.python-version`.
`make check` runs tests once in the selected environment and Pyright separately
for Python 3.11, 3.12 and 3.13. GitHub CI installs and tests the project in each
of those three Python versions; documentation builds once in the 3.13 job.

For focused feedback, use `make test-one TEST=tests/test_file.py::test_name`.
This does not replace the complete gate or its 80% branch coverage requirement.
In the template generator repository, identified by `copier.yml`, also run
`make test-integration` to exercise real generated projects.

## Documentation

`make docs-serve` starts the local MkDocs preview. `make docs-build` builds the site
into `site/` in strict mode. All pages use normal Markdown under `docs/`, and
navigation lives in `mkdocs.yml`. Generated Python projects also render their
Python API reference from docstrings through mkdocstrings.

## Use a coding agent

Claude Code and Codex share the rules in root `AGENTS.md`. Follow the
[agent setup guide](agents.md) to activate project permissions and the protected
metadata gate before development.

## Make a change

1. Open a feature branch: `git switch -c type/short-description`
   (e.g. `feat/foo-bar`), or `codex/short-description` for Codex work.
2. Implement the change with a focused failing test, a minimal fix, and
   verification before committing.
3. Walk the [Pre-PR checklist](pr-checklist.md) before opening the PR.
4. Use Conventional Commits for every commit subject
   (`type(scope): subject`, ≤72 chars).

For lint and type-check rules, including the suppression protocol, see
[Lint & typing](lint-typing.md).
