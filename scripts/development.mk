.PHONY: help version install setup clean test test-one test-permissions lint lint-fix format format-check format-ruff format-ruff-check format-md format-md-check format-toml format-toml-check format-yaml format-yaml-check format-json format-json-check typecheck audit check docs-build docs-serve bump-patch bump-minor bump-major changelog pre-commit lock-check format-project-text

VENV := .venv
# Preserve literal test IDs instead of evaluating Make expressions supplied in TEST.
override TEST := $(value TEST)
export TEST

help::
	@echo "Makefile targets:"
	@echo "  install                Install locked dev/docs dependencies; initialize a missing lock"
	@echo "  setup                  Install dependencies and all Git hook stages"
	@echo "  clean                  Remove venv, build outputs and caches"
	@echo "  test                   Run tests once in the active Python environment"
	@echo "  test-one TEST=tests/…   Run one test file or node for focused feedback"
	@echo "  test-permissions       Verify policy and real sandbox (CODEX_TEST_BINARY required)"
	@echo "  lint | lint-fix        Run Ruff checks or safe fixes"
	@echo "  format | format-check  Format all supported files or check without rewriting"
	@echo "  format-{ruff,md,toml,yaml,json}[-check]   Individual formatters"
	@echo "  typecheck              Strict Pyright for Python 3.11, 3.12 and 3.13"
	@echo "  audit                  Audit locked runtime, dev and docs dependencies"
	@echo "  lock-check             Verify uv.lock agrees with pyproject.toml"
	@echo "  check                  lock-check, formatting, lint, typing and tests"
	@echo "  pre-commit             Run all pre-commit hooks"
	@echo "  docs-build             Build MkDocs with strict link and anchor checks"
	@echo "  docs-serve             Serve MkDocs locally with live reload"
	@echo "  changelog              Generate the changelog with Commitizen"
	@echo "  bump-patch|bump-minor|bump-major   Version, changelog, commit and local annotated tag"
	@echo "  version                Print current version"

version:
	@uv version --short

install:
	@if [ ! -f uv.lock ]; then uv lock; fi
	uv sync --locked --group dev --group docs

setup: install
	uv run --group dev pre-commit install --install-hooks
	$(MAKE) format

# Rendered user descriptions and answers may need quoting/wrapping normalization.
format-project-text: format-md format-toml format-yaml format-json

pre-commit:
	uv run --group dev pre-commit run --all-files

clean:
	rm -rf $(VENV) dist/ build/ htmlcov/ site/ .pytest_cache .ruff_cache
	rm -f .coverage .coverage.* coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."

test:
	uv run --group dev --group docs pytest tests/ -v -m "not integration" \
	    --cov=$(COVERAGE_SOURCE) --cov-report=term-missing

test-one:
	@case "$${TEST%%::*}" in */../*|*/..) ;; tests/?*) exit 0 ;; esac; \
	    echo "Usage: make test-one TEST=tests/test_file.py[::test_name]" >&2; exit 2
	uv run --group dev --group docs pytest "$$TEST" -v

test-permissions:
	@test -n "$$CODEX_TEST_BINARY" || { \
	    echo "Set CODEX_TEST_BINARY to an installed Codex CLI executable." >&2; exit 2; }
	uv run --group dev pytest tests/test_agent_permissions.py -v

lint:
	uv run --group dev ruff check $(PYTHON_PATHS)

lint-fix:
	uv run --group dev ruff check --fix $(PYTHON_PATHS)

format: format-ruff format-project-text

format-check: format-ruff-check format-md-check format-toml-check format-yaml-check format-json-check

format-ruff:
	uv run --group dev ruff format $(PYTHON_PATHS)

format-ruff-check:
	uv run --group dev ruff format --check $(PYTHON_PATHS)

format-md format-toml format-yaml format-json:
	uv run --group dev python scripts/format_files.py $(patsubst format-%,%,$@)

format-md-check format-toml-check format-yaml-check format-json-check:
	uv run --group dev python scripts/format_files.py $(patsubst %-check,%,$(patsubst format-%,%,$@)) --check

typecheck:
	@for version in 3.11 3.12 3.13; do \
	    uv run --group dev pyright --pythonversion $$version $(PYTHON_PATHS) || exit $$?; \
	done

audit:
	@mkdir -p .cache
	uv export --locked --all-groups --no-emit-project --output-file .cache/audit-requirements.txt
	uv tool run pip-audit --strict --disable-pip --require-hashes -r .cache/audit-requirements.txt

lock-check:
	uv lock --check

check: lock-check
	$(MAKE) format-check lint typecheck test

docs-build:
	uv run --group docs mkdocs build --strict

docs-serve:
	uv run --group docs mkdocs serve

changelog:
	uv run --group dev python scripts/release.py changelog

bump-patch bump-minor bump-major:
	uv run --group dev python scripts/release.py bump $(patsubst bump-%,%,$@)
