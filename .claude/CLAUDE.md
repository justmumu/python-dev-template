## Development Rules

### Python Virtual Environment

Managed by **uv**. Deps in `pyproject.toml` (`[project.dependencies]` + `[dependency-groups] dev`/`docs`). Lockfile `uv.lock` must be committed.

Run Python via `.venv/bin/<cmd>`, `source .venv/bin/activate`, or `uv run <cmd>`. If `.venv` missing → `make setup`. Never use system Python.

Add deps: `uv add <pkg>` (runtime), `uv add --group dev <pkg>` (dev), `uv add --group docs <pkg>` (docs). Never hand-edit lockfile.

______________________________________________________________________

### Lint & Type Check

Ruff (lint + format) + pyright strict for Python; mdformat (md), taplo (toml), yamlfix (yml/yaml), pretty-format-json (json) — all pip-managed, wired into `make format` / `make format-check`. **Fix the root cause, do not silence warnings.** Try `ruff check --fix` before manual edits. After every edit, run `ruff check` and `pyright` on changed files before moving on — a broken baseline compounds fast.

Suppressions (`# noqa`, `# type: ignore`, `# pyright: ignore[...]`, `# pragma: no cover`) require a strong, documented reason. Never modify `pyproject.toml` lint/type config unilaterally.

`make setup` installs pre-commit hooks: lint-fix + format (all formatters) + lock-check on pre-commit, `make check` on pre-push (full gate), Conventional Commits on commit-msg. Never bypass with `--no-verify` — fix the cause.

Full rules — banned forms, acceptable reasons, suppression format, escalation protocol, verification gate: [`.claude/rules/lint-typing.md`](rules/lint-typing.md).

______________________________________________________________________

### Code Intelligence

Symbol name → LSP. Text pattern (comment, string, config) → Grep. Reading a whole file to learn its shape is almost always wrong — use `documentSymbol`. Before any rename or signature change, run `findReferences` first. Treat `<new-diagnostics>` reminders as blockers, not notes.

Full reflex → LSP substitution table and rationale: [`.claude/rules/code-intelligence.md`](rules/code-intelligence.md).

______________________________________________________________________

### Git Workflow

Every change ships through a feature branch + PR. **Never commit or push directly to `main`** — this applies to trivial changes too (typos, one-line doc fixes, version bumps).

- **Branches:** `type/short-description` (`feat/browser-retry`, `fix/docker-start-race`, `docs/release-process`, `chore/bump-v0.2.0`).
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) — `type(scope): subject`. Scope optional when change is cross-cutting.
- **Merge:** Regular merge commits, **never squash**. Preserves individual commit SHAs so locally-created tags on the branch stay valid after merge.
- **Pre-PR gate:** Walk [`docs/contributing/pr-checklist.md`](../docs/contributing/pr-checklist.md). `make check` + `make docs-build` minimum.

______________________________________________________________________

### Release discipline

Version bumps follow the same branch + PR rule. `make bump-{patch,minor,major}` edits `pyproject.toml`, regenerates `CHANGELOG.md` from Conventional Commits (commitizen), commits, and creates a local tag — it does **not** push.

Flow (full detail: [`.claude/rules/release-process.md`](rules/release-process.md)):

1. From clean `main`: `git switch -c chore/bump-v<new>`
2. `make bump-<segment>` — creates bump commit (version + changelog) + local annotated tag (refuses on dirty tree)
3. Push **branch only**: `git push -u origin chore/bump-v<new>`. **Do not push the tag yet.**
4. Open PR, review, merge (regular merge — preserves the bump commit SHA).
5. After merge: `git switch main && git pull && git push origin v<new>` — the tag push triggers the `Release` workflow, which creates the GitHub Release from `CHANGELOG.md` automatically.

The macro prints these next steps after tagging, so the flow is self-reminding.

______________________________________________________________________

### Superpowers Artifact Locations

Superpowers skills write artifacts under `.superpowers/` at repo root (gitignored, private working area). These paths override the default `docs/superpowers/` locations used by the brainstorming, writing-plans, and related skills:

- Design specs → `.superpowers/docs/specs/YYYY-MM-DD-<topic>-design.md`
- Implementation plans → `.superpowers/docs/plans/YYYY-MM-DD-<topic>-plan.md`

Never write superpowers artifacts into the tracked `docs/` tree — that directory is reserved for the public MkDocs site.
