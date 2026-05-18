# GitHub Copilot Instructions

> Full project context, hard constraints, conventions, and working style live in [`CLAUDE.md`](../CLAUDE.md). Read it first.
> Quick-reference links to architecture, HA patterns, UniFi API, testing, and TODO docs are in [`AGENTS.md`](../AGENTS.md).

---

## What this repo is

A Home Assistant custom integration (`domain: unifi_alerts`) that aggregates UniFi Network controller alerts into HA sensors, binary sensors, event entities, and buttons. Distributed via HACS.

## Tech stack

| Layer | Tool |
|-------|------|
| Language | Python 3.12+ |
| Async HTTP | `aiohttp` |
| Lint + format | `ruff` |
| Type checking | `mypy` (strict) |
| Tests | `pytest` + `MagicMock`/`AsyncMock` |
| HA integration | `custom_components/unifi_alerts/` |

## Build & test

```bash
make check      # lint + typecheck + validate + test (run before every commit)
make lint       # ruff check + format check
make typecheck  # mypy
make validate   # HACS preflight + translation drift check
make test       # pytest
```

All commands use `.venv` in the repo root — never the system Python.

## Key source files

| File | Role |
|------|------|
| `custom_components/unifi_alerts/const.py` | All constants, category defs, UniFi key→category map |
| `custom_components/unifi_alerts/coordinator.py` | DataUpdateCoordinator — owns all category state |
| `custom_components/unifi_alerts/webhook_handler.py` | Registers HA webhooks, validates `?token=` bearer auth |
| `custom_components/unifi_alerts/config_flow.py` | Three-step UI setup + options flow |
| `custom_components/unifi_alerts/strings.json` | Must stay identical to `translations/en.json` |

## Non-negotiable rules (summary)

- **No blocking I/O** — every network/disk call must be `async`.
- **`X | None`** not `Optional[X]`; `list[str]` not `List[str]`.
- **Entities never cache state** — read from coordinator only.
- **`manifest.json` keys** must be `domain`, `name`, then alphabetical — hassfest enforces order.
- **Webhook token auth is mandatory** — reject requests without a valid `?token=` query param (HTTP 401).
- **GitHub Actions `uses:` must be full 40-char SHA** — no tags, no branch refs.
- **No third-party release actions** — use `gh release create --generate-notes` only.
- **`strings.json` and `translations/en.json` must be identical** — CI enforces this.

See [`CLAUDE.md`](../CLAUDE.md) for the complete list with rationale.

## Branching & versioning

- Work on `dev`; `main` is stable-only.
- `main` version format: `X.Y.Z`; `dev` format: `X.Y.Z-preN` (or stable when preparing a release).
- Feature branches: `claude/*` or `feature/*`, always branched from `dev`.
- Claude cannot push tags — provide the user with the exact `git tag` + `git push origin <tag>` command after a version-bump PR merges.

See [`CLAUDE.md`](../CLAUDE.md) for the full release workflow.

## Maintenance matrix

What must be updated when specific parts of the codebase change.

### Adding a new alert category

| File | Change required |
| ---- | --------------- |
| `custom_components/unifi_alerts/const.py` | Add `CATEGORY_<NAME>` constant; add to `ALL_CATEGORIES`, `CATEGORY_LABELS`, `CATEGORY_ICONS`, `CATEGORY_ICONS_OK`; add all `EVT_*` keys to `UNIFI_KEY_TO_CATEGORY` |
| `custom_components/unifi_alerts/strings.json` | Add `"cat_<name>"` label to `config.step.categories.data`, `config.step.finish.data`, `options.step.options.data`; add webhook URL label |
| `custom_components/unifi_alerts/translations/en.json` | Mirror every change to `strings.json` exactly |
| `tests/unit/conftest.py` | Add category to fixture category lists |
| `tests/integration/conftest.py` | Add category to fixture category lists |

Run `make validate` after: catches translation drift and HACS preflight failures immediately.

### Modifying webhook request handling

| File | Change required |
| ---- | --------------- |
| `custom_components/unifi_alerts/webhook_handler.py` | Primary change site - all webhook registration, token validation, dedup logic |
| `tests/unit/test_webhook_handler.py` | Unit tests for handler logic |
| `tests/integration/test_webhook.py` | Integration tests for full webhook flow |

Never remove the `?token=` validation check - it is a security hard requirement.

### Changing coordinator data shape

| File | Change required |
| ---- | --------------- |
| `custom_components/unifi_alerts/coordinator.py` | Primary change site |
| `custom_components/unifi_alerts/binary_sensor.py` | Reads `coordinator.data` - check all `@property` accessors |
| `custom_components/unifi_alerts/sensor.py` | Reads `coordinator.data` - check all `@property` accessors |
| `custom_components/unifi_alerts/event.py` | Reads `coordinator.data` - check all `@property` accessors |
| `custom_components/unifi_alerts/button.py` | Reads `coordinator.data` - check all `@property` accessors |
| `tests/unit/test_coordinator.py` | Coordinator unit tests |
| `tests/integration/test_lifecycle.py` | Full lifecycle integration tests |

### Modifying `UniFiClientConfig` or `UniFiAlert`

| File | Change required |
| ---- | --------------- |
| `custom_components/unifi_alerts/models.py` | Primary change site |
| `custom_components/unifi_alerts/unifi_client.py` | Uses `UniFiClientConfig` and returns `UniFiAlert` instances |
| `custom_components/unifi_alerts/coordinator.py` | Constructs `UniFiClientConfig`; processes `UniFiAlert` objects |
| `custom_components/unifi_alerts/webhook_handler.py` | Constructs `UniFiClientConfig` at registration time |
| `custom_components/unifi_alerts/__init__.py` | Casts `entry.data` to `UniFiClientConfig` at setup |
| `tests/unit/test_models.py` | Model unit tests |

### Editing `manifest.json`

Keys must remain: `domain`, `name`, then all remaining keys alphabetically. hassfest will reject any other order. Run `make validate` after every edit.