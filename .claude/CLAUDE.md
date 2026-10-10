# Claude Code integration

Shared development rules are loaded by root `CLAUDE.md` through `@AGENTS.md`.
Do not duplicate them here. See `docs/contributing/agents.md`
for setup and the protected-files guard. The guard reverts agent writes to
protected configuration files: use the `make` targets it documents (for example
`make uv-add`) or ask the user, and never retry a reverted write.

Use LSP when the host exposes it. Treat diagnostic error
reminders as blockers. If LSP is unavailable, use the shared command-line
checks and report the missing capability without blocking routine work.

Only the Compound Engineering plugin is enabled in
`.claude/settings.json`; its availability does not change the shared policy.
