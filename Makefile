.DEFAULT_GOAL := help
PYTHON_PATHS := tests/ scripts/
COVERAGE_SOURCE := scripts.bootstrap

include scripts/development.mk

.PHONY: test-integration

help::
	@echo "  test-integration       Validate both generated-project setup routes"

test-integration:
	uv run --locked --group dev --group docs pytest -v -m integration
