.PHONY: help version install setup clean test lint lint-fix format format-check \
        format-ruff format-ruff-check format-md format-md-check format-toml format-toml-check \
        format-yaml format-yaml-check format-json format-json-check \
        typecheck audit check docs-build docs-serve changelog bump-patch bump-minor bump-major \
        pre-commit lock-check

VERSION := $(shell grep '^version' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
VENV := .venv

# Tracked + untracked-but-not-ignored files per type. uv.lock is machine-generated — never formatted.
LSF := git ls-files --cached --others --exclude-standard
MD_FILES := $(shell $(LSF) '*.md')
TOML_FILES := $(shell $(LSF) '*.toml' ':!uv.lock')
YAML_FILES := $(shell $(LSF) '*.yml' '*.yaml')
JSON_FILES := $(shell $(LSF) '*.json')

help:
	@echo "Makefile targets:"
	@echo "  install                uv sync (dev + docs groups, locked)"
	@echo "  setup                  install + git hooks (pre-commit/pre-push/commit-msg)"
	@echo "  clean                  Remove venv and caches"
	@echo "  test                   Run pytest (non-integration)"
	@echo "  lint                   Run ruff check"
	@echo "  lint-fix               Run ruff check --fix (auto-fix safe violations)"
	@echo "  format                 Format everything: py (ruff) + md (mdformat) + toml (taplo) + yaml (yamlfix) + json"
	@echo "  format-check           Check all formatters without writing"
	@echo "  typecheck              Run pyright over src/, tests/, scripts/ for py3.11/3.12/3.13"
	@echo "  audit                  Run pip-audit over the full locked env (all groups)"
	@echo "  lock-check             Verify uv.lock is in sync with pyproject.toml"
	@echo "  check                  lock-check + format-check + lint + typecheck + test"
	@echo "  pre-commit             Run all pre-commit hooks"
	@echo "  docs-build             Build the docs site (MkDocs strict build)"
	@echo "  docs-serve             Serve the docs site locally with live reload"
	@echo "  changelog              Regenerate CHANGELOG.md from Conventional Commits"
	@echo "  bump-patch|bump-minor|bump-major   Version bump + changelog + local tag"
	@echo "  version                Print current version"

version:
	@echo $(VERSION)

install:
	uv sync --locked --group dev --group docs

setup: install
	uv run --group dev pre-commit install --install-hooks

pre-commit:
	uv run --group dev pre-commit run --all-files

clean:
	rm -rf $(VENV)
	rm -rf build/ dist/ htmlcov/ site/ *.egg-info src/*.egg-info
	rm -rf .pytest_cache .ruff_cache
	rm -f .coverage .coverage.* coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."

test:
	uv run --group dev pytest tests/ -v -m "not integration" \
	    --cov=your_package --cov-report=term-missing

lint:
	uv run --group dev ruff check src/ tests/ scripts/

lint-fix:
	uv run --group dev ruff check --fix src/ tests/ scripts/

format: format-ruff format-md format-toml format-yaml format-json

format-check: format-ruff-check format-md-check format-toml-check format-yaml-check format-json-check

format-ruff:
	uv run --group dev ruff format src/ tests/ scripts/

format-ruff-check:
	uv run --group dev ruff format --check src/ tests/ scripts/

format-md:
	uv run --group dev mdformat $(MD_FILES)

format-md-check:
	uv run --group dev mdformat --check $(MD_FILES)

format-toml:
	uv run --group dev taplo fmt $(TOML_FILES)

format-toml-check:
	uv run --group dev taplo fmt --check $(TOML_FILES)

format-yaml:
	uv run --group dev yamlfix $(YAML_FILES)

format-yaml-check:
	uv run --group dev yamlfix --check $(YAML_FILES)

# pretty-format-json exits 1 both when it rewrites files (fine) and on parse errors
# (not fine) — on nonzero, re-run in check mode so only real errors fail the target.
format-json:
	@uv run --group dev pretty-format-json --autofix --indent 2 --no-sort-keys $(JSON_FILES) \
	    || uv run --group dev pretty-format-json --indent 2 --no-sort-keys $(JSON_FILES)

format-json-check:
	uv run --group dev pretty-format-json --indent 2 --no-sort-keys $(JSON_FILES)

# Checks against every supported Python version: the lowest catches too-new
# syntax/APIs, the highest catches stdlib removed in newer versions.
PYRIGHT_VERSIONS := 3.11 3.12 3.13

typecheck:
	@for v in $(PYRIGHT_VERSIONS); do \
	  echo "== pyright --pythonversion $$v =="; \
	  uv run --group dev pyright --pythonversion $$v src/ tests/ scripts/ || exit 1; \
	done

# Audits the FULL locked environment (all dependency groups + transitives), not just
# runtime deps. --locked fails loudly if uv.lock is out of sync with pyproject.toml
# (a plain export would silently re-resolve). Hashes come from uv.lock;
# --disable-pip + --require-hashes skips the pip resolver and verifies integrity.
audit:
	uv export --locked --all-groups --no-emit-project | uv tool run pip-audit --strict --disable-pip --require-hashes -r /dev/stdin

lock-check:
	uv lock --check

# lock-check runs first: with a drifted lockfile the uv run calls below would
# silently re-resolve uv.lock — fail loudly before anything can mutate it.
check: lock-check format-check lint typecheck test

docs-build:
	uv run --group docs mkdocs build --strict

docs-serve:
	uv run --group docs mkdocs serve

changelog:
	uv run --group dev cz changelog

bump-patch bump-minor bump-major:
	@git diff --quiet && git diff --cached --quiet || { echo "ERROR: working tree not clean — commit or stash first."; exit 1; }
	@segment=$$(echo $@ | sed 's/^bump-//'); \
	uv version --bump $$segment; \
	new=$$(uv version --short); \
	uv run --group dev cz changelog --unreleased-version "v$$new"; \
	uv run --group dev mdformat CHANGELOG.md; \
	git add pyproject.toml uv.lock CHANGELOG.md; \
	git commit -m "chore: bump version to v$$new"; \
	git tag -a "v$$new" -m "v$$new"; \
	branch=$$(git rev-parse --abbrev-ref HEAD); \
	printf "\nLocal tag v%s created. Next steps:\n" "$$new"; \
	printf "  git push -u origin %s\n" "$$branch"; \
	printf "  # open PR, merge with a regular merge commit, then:\n"; \
	printf "  git switch main && git pull && git push origin v$$new\n"
