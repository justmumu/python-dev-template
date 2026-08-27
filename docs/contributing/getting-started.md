# Getting started

If you're contributing to this project for the first time, here's the minimum to get up and running.

## Prerequisites

- **uv** — Python package + project manager. Install: <https://docs.astral.sh/uv/>

## Clone and set up

```bash
git clone https://github.com/{{REPO_OWNER}}/python-dev-template.git
cd python-dev-template
make setup
```

`make setup` does:

- `uv sync --locked --group dev --group docs` — installs Python deps into `.venv/`.
- `pre-commit install` — wires the pre-commit, pre-push, and commit-msg git hooks.

## The dev gate

Run before any PR:

```bash
make check       # lock-check + format-check (all formatters) + lint + typecheck (py3.11-3.13) + test
make docs-build  # MkDocs strict build (fails on broken internal links)
```

Both are enforced on `git push` via the pre-push hook, so a broken push is impossible.

## Editor setup (VS Code, optional)

Open the repo folder and install the workspace-recommended extensions
(Extensions panel → type `@recommended`). Do this **after** `make setup` —
the format-on-save bridges call the tools inside `.venv/`.

With those installed, saving any file formats it with the exact same pinned
tools `make format` uses (ruff, taplo, mdformat, yamlfix, JSON) — editor
output, `make format`, and CI are byte-identical.

Other editors: `.editorconfig` covers the basics (indent, line endings, final
newline); the pre-commit hook runs `make format` for you on commit.

## Make a change

1. Open a feature branch: `git switch -c type/short-description` (e.g. `feat/foo-bar`).
2. Implement the change with TDD: failing test → minimal fix → verify → commit.
3. Walk the [Pre-PR checklist](pr-checklist.md) before opening the PR.
4. Use Conventional Commits for every commit subject (`type(scope): subject`, ≤72 chars).

For lint and type-check rules — including the suppression protocol — see [Lint & typing](lint-typing.md).
