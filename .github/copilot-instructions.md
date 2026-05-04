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