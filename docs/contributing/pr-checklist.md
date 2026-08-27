# Pre-PR checklist

Run through this list before opening a pull request. The goal is to keep the
review cycle short: an hour spent on the checklist saves a day of back-and-forth.

## 1. Branch and commits

- Branch name follows `type/short-description` (e.g. `feat/foo-bar`).
- Each commit uses [Conventional Commits](https://www.conventionalcommits.org/):
  `type(scope): subject`. **Scope** is optional and freeform; **type** is
  enforced (by `scripts/hooks/check_conventional_commit.py`) to one of:
  `feat`, `fix`, `docs`, `chore`, `ci`, `refactor`, `test`, `style`,
  `build`, `perf`, `revert`. Subject ≤72 chars, no trailing period.
- History is the shape you want merged (we use real merge commits, never
  squash). Rebase or `--amend` locally before opening the PR.

## 2. Local verification

```bash
make check       # lock-check + format-check (all formatters) + lint + typecheck (py3.11-3.13) + test
make docs-build  # MkDocs strict build (fails on broken internal links)
```

The pre-push hook runs both, so a push that would fail CI is blocked locally.
When editing `docs/` (or docstrings that feed the API reference), run
`make docs-build` early for faster feedback.

## 3. Tests

- New behaviour is covered by a test.
- Bugs come with a regression test that fails on the old code and passes
  on the new code.

## 4. Documentation

- Public-facing behaviour changes are reflected in the relevant doc under
  `docs/`.

## 5. Opening the PR

- PR title mirrors the Conventional Commit subject of the main change.
- Description covers: what changed, why, how it was tested, and any
  follow-ups being deliberately deferred.
- Linked issues / discussions are referenced.
- CI is green on the PR branch before requesting review.
