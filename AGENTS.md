# GitHub Copilot Instructions

> **Full project context, constraints, conventions, and working style are in [`CLAUDE.md`](../CLAUDE.md). Read it first.**

## Quick reference

| Topic | Where to look |
| ----- | ------------- |
| Architecture & data flow | `docs/ARCHITECTURE.md` |
| HA-specific patterns | `docs/HOMEASSISTANT.md` |
| UniFi API & payloads | `docs/UNIFI.md` |
| Outstanding work | `docs/TODO.md` |
| Test guidance | `docs/TESTING.md` |

## Tech stack

- **Python 3.12+** - modern type hints only (`list[str]`, `X | None`)
- **Home Assistant** custom integration (`custom_components/unifi_alerts/`)
- **aiohttp** for all async HTTP; **pytest** + `MagicMock`/`AsyncMock` for tests
- **ruff** (lint + format) and **mypy** (strict type-checking)
- Distributed via **HACS**

## Build & test commands

```bash
make check        # default: lint + typecheck + validate + test (run before every commit)
make lint         # ruff check + format check
make typecheck    # mypy
make validate     # HACS preflight + translation drift check
make test         # pytest
```

All commands use `.venv` in the repo root - never the system Python.

## Key files

| File | Purpose |
| ---- | ------- |
| `custom_components/unifi_alerts/const.py` | All constants, category defs, UniFi key>category map |
| `custom_components/unifi_alerts/coordinator.py` | DataUpdateCoordinator - owns all category state |
| `custom_components/unifi_alerts/config_flow.py` | Three-step UI setup + options flow |
| `custom_components/unifi_alerts/strings.json` | Must stay identical to `translations/en.json` |
| `tests/conftest.py` | Shared fixtures and helpers |

## Hard rules for suggestions

- **No blocking I/O** - every function touching the network or disk must be `async`.
- **No `Optional[X]`** - use `X | None`.
- **No entity state caching** - entities read state from the coordinator only.
- **`manifest.json` keys must be alphabetical** (after `domain`, `name`) - hassfest enforces order.
- **Every GitHub Actions `uses:` must be a full 40-character SHA** - no tag or branch refs.
- **Webhook requests must be validated** against `CONF_WEBHOOK_SECRET` via `?token=` - never skip this check.
