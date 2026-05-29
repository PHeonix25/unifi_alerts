.PHONY: help setup setup-lint test lint typecheck validate doc-check check

# OS-aware paths so the Makefile works on Windows (cmd.exe / PowerShell) as
# well as Linux/macOS. On Windows, Python's venv puts binaries in Scripts/
# with .exe extensions; on Unix they live under bin/ with no suffix.
ifeq ($(OS),Windows_NT)
  VENV := .venv/Scripts
  PY312 := py -3.12
  EXE := .exe
else
  VENV := .venv/bin
  PY312 := python3.12
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
	@echo "  make test       - full pytest suite with coverage (fail below 95%)"

setup:
	$(PY312) -m venv .venv
	$(VENV)/pip$(EXE) install -r requirements-dev.txt

setup-lint:
	$(PY312) -m venv .venv
	$(VENV)/pip$(EXE) install -r requirements-lint.txt

test:
	$(VENV)/pytest$(EXE) tests/ -v

lint:
	$(VENV)/python$(EXE) scripts/run_lint.py

typecheck:
	$(VENV)/python$(EXE) scripts/run_typecheck.py

# `validate` and `doc-check` use the system python via $(PY312) wrapper - both
# scripts are pure stdlib so they don't need the venv at all. Falls back to
# `python3` on Unix and `python` on Windows when 3.12 isn't on PATH as
# `python3.12` / `py -3.12`.
validate:
	$(PY312) scripts/validate_hacs.py
	$(PY312) scripts/validate_docs.py

doc-check:
	$(PY312) scripts/validate_docs.py
	$(PY312) scripts/check_translations.py

check: lint typecheck validate test
	@echo All checks passed.

.DEFAULT_GOAL := help
