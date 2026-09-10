# Lint & Type Check

Ruff and pyright are both configured in `pyproject.toml`. Ruff runs with a broad rule set; pyright runs in `typeCheckingMode = "strict"` with `reportUnnecessaryTypeIgnoreComment = "error"` — dead suppressions are caught automatically.

Non-Python formatting is installed through uv alongside the development tools:

| Files    | Formatter                             | Make target        |
| -------- | ------------------------------------- | ------------------ |
| Python   | Ruff                                  | `make format`      |
| Markdown | mdformat with GFM/frontmatter support | `make format-md`   |
| TOML     | taplo                                 | `make format-toml` |
| YAML     | yamlfix                               | `make format-yaml` |
| JSON     | pretty-format-json                    | `make format-json` |

`make format` runs all formatters; `make format-check` checks without rewriting
files. The formatters cover tracked and untracked non-ignored files, excluding
`uv.lock`, private work areas and the Jinja source tree. Generated projects run
the same checks on their rendered files. Make, Git hooks and CI use the same
tools and configuration. The editor follows the same formatting conventions;
for JSON it uses Python's `json.tool`, while Make uses `pretty-format-json`.
Both preserve key order and Unicode, with two-space indentation. JSON formatting
applies to standard JSON; JSON with comments is not supported.

**Fix the root cause, do not silence warnings.**

## Auto-fix first

For ruff violations, run `make lint-fix` before editing by hand. The target uses Ruff's safe fixes. Review remaining suggestions and fix the underlying code; do not introduce ad hoc flags that weaken the checks.

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

After each coherent change, run `make lint` and `make typecheck`; use `make check` for the complete gate before claiming completion. When the host provides diagnostic reminders, treat errors as blockers.

Use `make test-one TEST=tests/test_file.py::test_name` for focused test feedback.
This accepts one test file/node under `tests/`, not arbitrary pytest flags. It
does not replace `make check`, which still runs the full fast suite and coverage
threshold. In the template generator repository (which contains `copier.yml`),
`make test-integration` runs the generation integration suite separately.

taplo may format Python metadata through `make format`; uv may manage the
lockfile. These trusted tool outputs are allowed. Direct AI metadata rewrites
and unilateral changes to lint/type/coverage policy still require approval.

## Git hooks

`make setup` installs all dependencies through uv and three Git hook stages:

- `pre-commit` — `make lint-fix` for Python changes, `make format` for text
  changes including Markdown/YAML, and `make lock-check` when `pyproject.toml`
  or `uv.lock` changes.
- `pre-push` — `make check` and `make docs-build`. Formatting checks cover every
  supported language; the strict MkDocs build checks internal links and anchors.
- `commit-msg` — Conventional Commits format (the `type(scope): subject` rule
  from `AGENTS.md`), implemented in `scripts/hooks/check_conventional_commit.py`.

CI independently runs the checks on Python 3.11, 3.12 and 3.13, with the docs
build in the 3.13 job. Locally, `make typecheck` checks all three target versions;
`make test` runs once in the selected interpreter with 80% branch coverage.

Local hooks provide earlier feedback and must also pass. Run `make setup` to
install/reinstall them and `make pre-commit` to exercise them on all files. If a
hook fails, diagnose its reported error. Never bypass it with `--no-verify`.
