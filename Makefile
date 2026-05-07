.PHONY: help setup setup-lint test lint typecheck validate doc-check check

VENV := .venv/bin

help:
	@echo "Common targets:"
	@echo "  make help       - show this message (default)"
	@echo "  make setup      - create .venv with full dev stack (Home Assistant + tests)"
	@echo "  make setup-lint - create .venv with ruff + mypy only (fast, lint-only work)"
	@echo "  make check      - lint + typecheck + validate + test (run before push)"
	@echo "  make doc-check  - prose linter + translation drift only, no venv needed"
	@echo ""
	@echo "Individual:"
	@echo "  make lint       - ruff check + format check"
	@echo "  make typecheck  - mypy"
	@echo "  make validate   - HACS manifest preflight + docs prose linter"
	@echo "  make test       - full pytest suite"

setup:
	python3.12 -m venv .venv
	$(VENV)/pip install -r requirements-dev.txt

setup-lint:
	python3.12 -m venv .venv
	$(VENV)/pip install -r requirements-lint.txt

test:
	$(VENV)/pytest tests/ -v

lint:
	$(VENV)/ruff check custom_components/
	$(VENV)/ruff format --check custom_components/

typecheck:
	$(VENV)/mypy custom_components/unifi_alerts --ignore-missing-imports

validate:
	python3 scripts/validate_hacs.py
	python3 scripts/validate_docs.py

doc-check:
	python3 scripts/validate_docs.py
	@diff custom_components/unifi_alerts/strings.json \
	      custom_components/unifi_alerts/translations/en.json > /dev/null \
	      || (echo "strings.json and translations/en.json have drifted" && exit 1)

check: lint typecheck validate test

.DEFAULT_GOAL := help
