# Lint & Type Check

Ruff and pyright are both configured in `pyproject.toml`. Ruff runs with a broad rule set (and `ruff format` handles formatting); pyright runs in `typeCheckingMode = "strict"` with `reportUnnecessaryTypeIgnoreComment = "error"` — dead suppressions are caught automatically.

Non-Python files are formatted by pip-managed tools: **mdformat** (`*.md`, config in `.mdformat.toml`), **taplo** (`*.toml`, config in `.taplo.toml`; `uv.lock` excluded), **yamlfix** (`*.yml`/`*.yaml`, config in `pyproject.toml` `[tool.yamlfix]`), and **pretty-format-json** (`*.json`). All run via `make format` / `make format-check` — same source of truth for pre-commit hooks and CI.

**Fix the root cause, do not silence warnings.**

## Auto-fix first

For ruff violations, run `ruff check --fix` before editing by hand. If the fixer reports unsafe suggestions, read what they do and decide per case whether to apply `--unsafe-fixes`. Manual edits are for cases the auto-fixer cannot handle structurally — not a default.

## Suppression bans

Never use any of the following to bypass a lint or type error without a strong, documented reason:

- `# noqa` / `# noqa: <code>` (ruff)
- `# type: ignore` / `# type: ignore[...]` (generic)
- `# pyright: ignore[reportX]` (pyright — preferred form when a pyright suppression is truly unavoidable, because it is rule-specific and pyright will flag it if it becomes unnecessary)
- `# pragma: no cover` (coverage — same discipline: only for code that legitimately cannot be executed in tests, not to hide untested paths)

## What counts as a strong, documented reason

One of:

- Known ruff or pyright bug with an upstream issue link.
- Third-party API whose typing or runtime behavior cannot be worked around (explain which API and why).
- Architectural trade-off already discussed and approved by the user.

## Suppression format — when one is truly justified

- Always use the **specific rule code** (`# noqa: E501`, `# pyright: ignore[reportUnknownMemberType]`), never a blanket form.
- Add an inline comment explaining **why** on the same line or the line immediately above.
- Prefer refactoring the code over suppressing the warning; suppression is the last resort.

## Config changes require escalation

Never modify `pyproject.toml` ruff or pyright rules unilaterally to make warnings disappear. This includes:

- `[tool.ruff.lint] select`
- `[tool.ruff.lint] ignore`
- `[tool.ruff.lint.per-file-ignores]`
- Any `report*` severity under `[tool.pyright]`

Raise the concern with the user first and only edit after explicit approval. Do not sprinkle suppressions across the codebase as a substitute for fixing the underlying issue.

## Verification gate after every edit

Before moving on to the next edit or claiming a task complete, run `ruff check` and `pyright` (or `make check`) against the changed files. Do not batch this to the end of the session — a broken baseline compounds quickly. Any `<new-diagnostics>` reminder that arrives after a write is a blocker, not a note.

## Git hooks

`make setup` requires only `uv`. It installs three `pre-commit` git hook stages:

- `pre-commit` — `make lint-fix`, `make format` (ruff + mdformat + taplo + yamlfix + pretty-format-json), `make lock-check` (latter only when `pyproject.toml` or `uv.lock` changes).
- `pre-push` — `make check` (lock-check + format-check + lint + typecheck + test) and `make docs-build` — mirrors CI. `format-check` covers every formatter in check mode.
- `commit-msg` — Conventional Commits format (enforces the `type(scope): subject` rule from `CLAUDE.md`), implemented locally in `scripts/hooks/check_conventional_commit.py`.

Hooks are ergonomic, not authoritative: CI still runs `make check` as the source of truth. If a hook is failing locally but CI is green, refresh the hook env: `uv run pre-commit clean && uv run pre-commit install --install-hooks`. Never bypass a failing hook with `--no-verify` — fix the root cause.
