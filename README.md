# python-dev-template

Create Python applications with shared development rules for **Claude Code and
Codex**, strict quality gates, and a template you can update through Copier.

## Create a project

**On GitHub:** select [Use this template](https://github.com/new?template_name=python-dev-template&template_owner=justmumu),
choose a lowercase Python project name such as `server` or `billing-service`, and wait for **Initial project setup**
in Actions. It fills in your repository's name, owner and description, then
verifies the generated project before committing it.

Setup uses the files GitHub already copied. No extra token or Actions secret is
required, including when the template repository is private.

**Locally:** install uv, then:

```bash
uvx --from 'copier>=9.18.2,<10' copier copy --vcs-ref=main \
  https://github.com/justmumu/python-dev-template.git weather-service
cd weather-service
git init -b main
make setup
make check
```

Copier asks for your project details. Commit the generated `uv.lock` and
`.copier-answers.yml`. Use the explicit ref until the first Copier-compatible release is published.

See the [creation guide](docs/guides/create-project.md) for both
routes and the [update guide](docs/guides/template-updates.md)
for bringing future template changes into your project.

## What the project includes

- An argparse CLI, typed environment configuration and application error classes.
- Python 3.11–3.13, uv and an installable console entrypoint.
- Ruff's full lint policy, strict Pyright and 80% branch coverage.
- Shared `AGENTS.md`, Claude Code settings, and Codex permissions and hooks.
- Automatic routine edits, with approval for direct Python metadata changes.
- Conventional Commit hooks, a three-version Python CI matrix, Dependabot and
  dependency auditing.
- Commitizen changelogs, annotated tags and automatic GitHub Releases.
- New projects start at `0.0.0`; Copier updates preserve application versions.
- MkDocs Material documentation with Python API references and a getting-started guide.

All development and documentation tools install through uv; no separate
Node.js or npm setup is required. `make setup` installs dependencies and hooks;
`make install` refreshes dependencies without installing hooks.

Run `make setup`, then follow the
[Claude Code and Codex setup guide](docs/contributing/agents.md)
to activate the instructions and permissions in your chosen host.

## Maintain this template

The root is the Copier generator; `template/` is the emitted Python project. Shared
hooks and policies have one source. Read the
[architecture guide](docs/guides/template-architecture.md) before
changing generation or bootstrap behavior.

```bash
make setup
make check
make docs-build
make test-integration
```

Rendering, update/conflict and bootstrap tests run in the fast gate. Integration
tests run the generated projects' own checks, docs/package builds and isolated wheel installations with console and module
entrypoints. Changes ship through feature branches and PRs; see [AGENTS.md](AGENTS.md).
