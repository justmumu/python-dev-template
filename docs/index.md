# python-dev-template

{{PROJECT_DESCRIPTION}}

This site is built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) and
[mkdocstrings](https://mkdocstrings.github.io/) — API pages are generated straight from the
package's Google-style docstrings.

## Quick links

- [Getting started](contributing/getting-started.md) — clone, toolchain, dev gate.
- [Pre-PR checklist](contributing/pr-checklist.md) — walk it before every PR.
- [Lint & typing](contributing/lint-typing.md) — ruff/pyright rules and the suppression protocol.
- [API reference](api.md) — generated from docstrings.

## Local docs loop

```bash
make docs-serve   # live reload at http://127.0.0.1:8000
make docs-build   # strict static build (fails on broken internal links)
```
