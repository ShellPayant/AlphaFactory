# =====================================================================
# AlphaFactory — common dev tasks (uv-managed)
# =====================================================================

.PHONY: help install install-dev sync test test-fast test-cov lint format typecheck check clean

help:
	@echo "AlphaFactory dev commands:"
	@echo "  install       Install runtime dependencies (uv sync)"
	@echo "  install-dev   Install runtime + dev dependencies"
	@echo "  sync          Sync to lockfile"
	@echo "  test          Run full test suite"
	@echo "  test-fast     Skip slow & integration tests"
	@echo "  test-cov      Run tests with coverage report"
	@echo "  lint          Run ruff linter"
	@echo "  format        Run ruff formatter"
	@echo "  typecheck     Run mypy strict type check"
	@echo "  check         lint + typecheck + test-fast (pre-commit gate)"
	@echo "  clean         Remove caches and build artefacts"

install:
	uv sync

install-dev:
	uv sync --extra dev

sync:
	uv sync --extra dev --frozen

test:
	uv run pytest

test-fast:
	uv run pytest -m "not slow and not integration and not live"

test-cov:
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy src

check: lint typecheck test-fast

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
