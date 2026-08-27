# python-dev-template

> **Team template for new Python projects.** Click "Use this template" on GitHub and
> a cleanup workflow will configure the new repo automatically.
>
> ⚠️ The initial setup commit takes ~1 minute to land. **Wait for it to appear
> on `main` before cloning**, or you'll need to rebase onto the setup commit.

## What this template provides

- uv-managed Python project (lockfile committed), supporting Python 3.11 / 3.12 / 3.13
- Ruff (broad lint ruleset + formatter) and pyright strict for Python — single source
  of truth shared by VSCode, pre-commit hooks, and CI
- Formatters for everything else, all pip-managed: mdformat (md), taplo (toml),
  yamlfix (yml/yaml), pretty-format-json (json)
- pre-commit hooks, Conventional Commits enforcement
- Changelog automation: `make bump-*` regenerates `CHANGELOG.md` from Conventional
  Commits (commitizen) alongside the version bump + tag
- Pre-configured GitHub Actions: CI (`make check` on a 3.11/3.12/3.13 matrix,
  `make docs-build` once), a Release workflow (pushing a version tag creates the
  GitHub Release from the matching `CHANGELOG.md` section), weekly `pip-audit`
  dependency audit, Dependabot on github-actions and uv
- MIT LICENSE shipped (downstream substitutes copyright holder)
- MkDocs Material docs site with mkdocstrings API reference
  generated from docstrings, plus the contributor guides
- VSCode workspace settings + recommended extensions (ruff, even-better-toml,
  custom-local-formatters, editorconfig, python, pylance, github-actions) — saving
  any file formats it with the same pinned tools `make format` uses, byte-identical
- `.claude/` config: CLAUDE.md, Claude plugins (superpowers, pyright-lsp,
  caveman), and a pre-tool-use hook guarding pyproject.toml / uv.lock
- Reference package skeleton: argparse CLI entrypoint (`__main__.py`), env-driven config
  (`config.py`), exception hierarchy (`errors.py`), `py.typed`, pytest suite with coverage gate

## Using this template

1. Click **Use this template → Create a new repository** on the GitHub page.
2. Name the new repo using the team convention: lowercase, hyphenated
   (e.g. `billing-service`). The package name is auto-derived by replacing hyphens
   with underscores (`billing_service`). **Don't name it `python-dev-template`** —
   the cleanup workflow refuses to run on a repo with the template's own name.
3. Wait for the **"chore: initial template setup"** commit to appear on `main`.
   Check the Actions tab if it's taking long.
4. Clone the new repo, open `POST_SETUP.md`, work through the manual TODOs
   (description, LICENSE if public, repo settings, etc.), then delete that file.
5. Code.

## What the cleanup workflow does

On the first push after "Use this template":

- Replaces `python-dev-template` → your new project name (every tracked file)
- Replaces `your_package` → your derived package name (dir, imports, docstrings)
- Replaces `{{REPO_OWNER}}` and `{{AUTHOR}}` markers
- Renames `src/your_package/` to `src/<your_package>/`
- Fills in the project description everywhere from the repo description you typed
  at create time (left as a `POST_SETUP.md` TODO if you left it empty)
- Pins `version` back to `0.0.0` and deletes the template's own `CHANGELOG.md` —
  your first `make bump-minor` ships `v0.1.0` with a fresh changelog
- Generates `uv.lock`
- Writes `POST_SETUP.md` with remaining manual TODOs
- Deletes the cleanup script, the cleanup workflow, the template-ci workflow,
  the sentinel file, and the template-specific tests — all in the same
  "chore: initial template setup" commit

## Working on this template

Prereqs: `uv` only.

Local dev loop:

```
make setup       # uv sync (dev + docs) + pre-commit install
make check       # lock-check + format-check (all formatters) + lint + typecheck (py3.11-3.13) + test
make docs-build  # mkdocs strict build (fails on broken internal links)
uv run --group dev pytest tests/test_template_init_integration.py -v -m integration   # full e2e (~1 min)
```

The `integration` marker keeps the slow end-to-end test out of `make check`;
CI runs it explicitly.
