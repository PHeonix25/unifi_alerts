.PHONY: setup test lint typecheck validate doc-check check

VENV := .venv/bin

setup:
	python3.12 -m venv .venv
	$(VENV)/pip install -r requirements-dev.txt

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

.DEFAULT_GOAL := check
