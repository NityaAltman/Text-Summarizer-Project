.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help setup test lint fmt typecheck check doctor clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the venv and install the package in editable mode
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@echo "\nDone. Activate with: source $(VENV)/bin/activate"

test:  ## Run the test suite
	$(PY) -m pytest

lint:  ## Check style
	$(PY) -m ruff check src tests

fmt:  ## Fix style and import order in place
	$(PY) -m ruff check --fix src tests
	$(PY) -m ruff format src tests

typecheck:  ## Run mypy
	$(PY) -m mypy

check: lint typecheck test  ## Everything CI runs

doctor:  ## Verify Ollama is reachable and the model is pulled
	$(PY) -m podsum doctor

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
