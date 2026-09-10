<!--
Thanks for opening a PR! Walk through the contributor checklist before
requesting review: docs/contributing/pr-checklist.md
-->

## Summary

<!-- What changes and why. One or two sentences is plenty. -->

## Testing

<!--
How did you verify this works? E.g.:
- `make check` passes locally
- New/updated unit tests cover the change
- Ran `make test-integration` when changing a repository
  that contains `copier.yml` (the template generator)
-->

## Checklist

- [ ] Branch follows `type/short-description` or `codex/short-description`.
- [ ] Commits use Conventional Commits (`type(scope): subject`).
- [ ] `make check` is green locally.
- [ ] `make docs-build` is green locally.
- [ ] Relevant docs updated (`docs/`, `README.md`, or `AGENTS.md` as appropriate).
- [ ] PR will be merged with a regular merge commit (not squash).

## Notes for the reviewer

<!-- Anything non-obvious: architectural tradeoffs, deliberately deferred work, follow-up issues. -->
