# Lint & type check

We use **ruff** (broad ruleset, plus `ruff format`) and **pyright** in
`typeCheckingMode = "strict"` for Python — `make typecheck` runs it against every
supported version (3.11/3.12/3.13); both are configured in `pyproject.toml`.
Non-Python files are formatted by **mdformat** (md), **taplo** (toml), **yamlfix**
(yml/yaml) and **pretty-format-json** (json) — all pure pip dependencies, run via
`make format` / `make format-check`.

**Fix the root cause, do not silence warnings.** Try `ruff check --fix` before editing by hand.

## Suppressions

Suppressions (`# noqa`, `# type: ignore`, `# pyright: ignore[...]`, `# pragma: no cover`) are a last resort. If one is genuinely necessary:

- Always use the **specific rule code** (e.g. `# noqa: E501`, `# pyright: ignore[reportUnknownMemberType]`) — never the blanket form.
- Add an inline comment explaining **why**, on the same line or the line directly above.
- Prefer refactoring the code over suppressing.

Never modify the lint/type config in `pyproject.toml` to make a warning disappear without raising the issue first.

## Git hooks

`make setup` installs three `pre-commit` git hook stages:

- `pre-commit` — `make lint-fix`, `make format` (all formatters), `make lock-check` (latter only when `pyproject.toml` or `uv.lock` changes).
- `pre-push` — `make check` (`lock-check` + `format-check` + `lint` + `typecheck` + `test`) and `make docs-build`; mirrors CI.
- `commit-msg` — Conventional Commits format.

Never bypass a failing hook with `--no-verify`. Hooks are ergonomic; CI runs `make check` as the source of truth.
