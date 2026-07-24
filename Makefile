.PHONY: help setup setup-lint test test-min-ha lint typecheck validate doc-check check

# OS-aware paths so the Makefile works on Windows (cmd.exe / PowerShell) as
# well as Linux/macOS. On Windows, Python's venv puts binaries in Scripts/
# with .exe extensions; on Unix they live under bin/ with no suffix.
ifeq ($(OS),Windows_NT)
  VENV := .venv/Scripts
  PY314 := py -3.14
  EXE := .exe
else
  VENV := .venv/bin
  PY314 := python3.14
  EXE :=
endif

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
	@echo "  make test       - full pytest suite with coverage (fail below 95%), against latest HA"
	@echo "  make test-min-ha - full pytest suite against the declared minimum HA (hacs.json floor)"
	@echo "  make coverage   - open HTML coverage report in browser after running tests"

setup:
	$(PY314) -m venv .venv
	$(VENV)/pip$(EXE) install -r requirements-dev.txt

setup-lint:
	$(PY314) -m venv .venv
	$(VENV)/pip$(EXE) install -r requirements-lint.txt

# The whole-suite coverage gate lives here (and in the CI test job), not in
# pytest addopts, so a targeted single-file pytest run still passes.
test:
	$(VENV)/pytest$(EXE) tests/ -v --cov-fail-under=95

# Mirrors the "minimum HA" leg of the `test` job in .github/workflows/ci.yml:
# overrides homeassistant + pytest-homeassistant-custom-component in the
# existing .venv down to the declared floor (hacs.json "homeassistant"),
# then runs the same suite against it. Requires `make setup` first. When the
# floor moves, update this pin alongside hacs.json, the ci.yml minimum-HA
# leg, and the README requirements section in the same PR.
test-min-ha:
	$(VENV)/pip$(EXE) install --quiet "homeassistant==2026.3.1" "pytest-homeassistant-custom-component==0.13.317"
	$(VENV)/pytest$(EXE) tests/ -v --cov-fail-under=95

coverage:
	$(VENV)/pytest$(EXE) tests/ -v --cov-report=html
	$(VENV)/python$(EXE) -m webbrowser htmlcov/index.html

lint:
	$(VENV)/python$(EXE) scripts/run_lint.py

typecheck:
	$(VENV)/python$(EXE) scripts/run_typecheck.py

# `validate` and `doc-check` use the system python via $(PY314) wrapper - both
# scripts are pure stdlib so they don't need the venv at all. Falls back to
# `python3` on Unix and `python` on Windows when 3.14 isn't on PATH as
# `python3.14` / `py -3.14`.
validate:
	$(PY314) scripts/validate_hacs.py
	$(PY314) scripts/validate_docs.py
	$(PY314) scripts/check_agentrc_refs.py

doc-check:
	$(PY314) scripts/validate_docs.py
	$(PY314) scripts/check_translations.py
	$(PY314) scripts/check_agentrc_refs.py

check: lint typecheck validate test
	@echo All checks passed.

.DEFAULT_GOAL := help
