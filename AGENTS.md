# AGENTS.md - unifi_alerts

> This file is the single home for the shared facts every agent needs: repo purpose, tech stack, build/test commands, and the repo map. Do not copy these blocks into [`CLAUDE.md`](CLAUDE.md) or [`.github/copilot-instructions.md`](.github/copilot-instructions.md); link here instead. `scripts/validate_docs.py` fails the build if the anchored blocks below are duplicated into another file.
> Claude-specific working style and the full non-negotiable constraint list live in [`CLAUDE.md`](CLAUDE.md). Release and branching detail lives in [`docs/RELEASING.md`](docs/RELEASING.md). Extended docs (architecture, HA patterns, UniFi API, testing) live in [`docs/`](docs/).

---

## What this repo is

A Home Assistant custom integration (`domain: unifi_alerts`) that aggregates UniFi Network controller alerts into HA sensors, binary sensors, event entities, and buttons. Distributed via HACS.

This integration covers **UniFi Network** only (System Logs / SIEM events from the Network Application on UniFi OS). It does **not** support UniFi Protect (cameras, motion detection, NVR).

Two data paths run in parallel:
- **Webhook push** - UniFi Alarm Manager POSTs to per-category webhook URLs registered by HA. Real-time path.
- **REST polling** - integration polls the UniFi controller's alarm API on a configurable interval. Backstop for open-count data and missed webhooks.

---

## Quick reference

| Topic | Where to look |
| ----- | ------------- |
| Architecture & data flow | `docs/ARCHITECTURE.md` |
| HA-specific patterns | `docs/HOMEASSISTANT.md` |
| UniFi API & payloads | `docs/UNIFI.md` |
| Outstanding work | GitHub Issues (taxonomy in `docs/TODO.md`) |
| Test guidance | `docs/TESTING.md` |
| Per-file responsibilities | `docs/REPO_LAYOUT.md` |

---

## Tech stack

<!-- shared:stack -->
| Layer | Tool |
| ----- | ---- |
| Type checking | `mypy` in strict mode |
| Tests | `pytest` + `MagicMock`/`AsyncMock`; never real HTTP in tests |
<!-- /shared:stack -->

---

## Build & test commands

<!-- shared:commands -->
```bash
make check        # default: lint + typecheck + validate + test (run before every commit)
make lint         # ruff check + format check
make typecheck    # mypy
make validate     # HACS preflight + docs prose checks
make doc-check    # docs prose checks + translation drift check
make test         # pytest
```
<!-- /shared:commands -->

All commands use `.venv` in the repo root - never the system Python. Run `make setup` once after cloning to create it.

---

## Repository map

Use [`docs/REPO_LAYOUT.md`](docs/REPO_LAYOUT.md) for the authoritative per-file map and load-bearing notes. Do not duplicate the file tree in agent-context files.

`agentrc.eval.json` holds planning-evaluation cases for agent harnesses: each case pairs a realistic task prompt with the expectations a good implementation plan must meet (files touched, constraints respected, tests updated) and a `checklist` array of binary, independently-gradeable criteria derived from those expectations - every case must ship a `checklist`, not prose alone. `scripts/check_agentrc_refs.py` (wired into `make doc-check`/`make validate` and CI) mechanically checks that file paths named in the case text still exist; it does not check the checklist's presence or shape, or judge semantic accuracy - review that by hand. `scripts/run_agentrc_eval.py` (manual/`workflow_dispatch`, see `docs/research/agentic-eval-harness.md`) runs the cases against one model (default Anthropic Claude Haiku - needs `ANTHROPIC_API_KEY`) and grades each checklist item pass/fail; `scripts/run_agentrc_eval_cross_model.py` runs the same cases against every model listed in `scripts/agentrc_eval_models.json` (manual only for now) and reports where models disagree. `.github/workflows/agentrc-quality-score.yml` runs the single-model check automatically on PRs touching `agentrc.eval.json`/`CLAUDE.md`/`AGENTS.md`/`custom_components/unifi_alerts/**` and posts an advisory PR comment - it never blocks a merge, and is a silent no-op if `ANTHROPIC_API_KEY` isn't configured. If you rename a symbol or move a test file referenced in a case's text, or the case's premise stops matching the codebase, update the case (and its checklist) in the same PR.

---

## Personas and when to invoke

Use `.github/agents/*.agent.md` as the source for persona behaviour and outputs. Route by task type:

- **Security Lead**: webhook token auth, diagnostics redaction, SSL verification defaults, and trust-boundary checks in webhook/client paths.
- **Software Engineering Lead**: coordinator-owned state, async lifecycle correctness, and design trade-offs in integration modules.
- **Quality Lead**: regression tests for config flow, webhook dispatch, coordinator polling, and entity state behaviour.
- **Responsible AI**: accessibility and inclusive UX in config flow copy, diagnostics readability, and privacy-by-design checks.
- **Product Manager**: issue shaping in this repo's taxonomy (`size:`, `priority:`, milestone) with measurable user outcomes.
- **Technical Debt Remediation Plan**: ranked debt plans tied to existing issues and verifiable follow-up work.

Keep persona examples tied to this integration's actual surface, not generic web-app examples.

---

## Adding a new alert category

This is the most common extension task. Every step is required - missing any one breaks the integration silently or at runtime.

1. **`const.py`** - add `CATEGORY_<NAME>: str = "<name>"` constant; add it to `ALL_CATEGORIES`; add entries to `CATEGORY_ICONS`, `CATEGORY_ICONS_OK`; add all relevant `EVT_*` keys to `UNIFI_KEY_TO_CATEGORY`.
2. **`strings.json`** - add `"cat_<name>"` key under each config step that lists categories (`categories.data`, `options.data`). Add webhook URL label under `finish.data` and `options.data`. Add the per-category entity display-name keys (binary sensor, last message, open count, event, clear button) under `entity` - these supply the localised entity names that used to come from `CATEGORY_LABELS`.
3. **`translations/en.json`** - mirror every change made to `strings.json` exactly. Run `scripts/check_translations.py` to validate.
4. **`binary_sensor.py`**, **`sensor.py`**, **`event.py`**, **`button.py`** - no code changes needed for most categories (platforms iterate `ALL_CATEGORIES` dynamically), but review each if adding a category with unusual display logic.
5. **`tests/`** - add the new category key to fixtures in `tests/unit/conftest.py` and `tests/integration/conftest.py`. Check `tests/unit/coordinator/` and `test_entities.py` for category-enumerated tests that need updating.
6. Run `make doc-check` for translation parity, then `make check` for the full suite. Fix any failures before committing.

---

## Hard rules

- **No blocking I/O** - every function touching the network or disk must be `async`.
- **`X | None`** not `Optional[X]`; `list[str]` not `List[str]`.
- **Entities never cache state** - read from coordinator only.
- **`manifest.json` keys** must be `domain`, `name`, then all remaining keys alphabetically - hassfest enforces order.
- **Webhook token auth is mandatory** - every inbound webhook request must be validated against `CONF_WEBHOOK_SECRET` via the `Authorization: Bearer` header (preferred) or the legacy `?token=` query parameter (deprecated, accepted during a migration window - issue #176). Never remove either check while both are supported.
- **GitHub Actions `uses:` must be full 40-char SHA** - no tags, no branch refs.
- **No third-party release actions** - use `gh release create --generate-notes` only.
- **`strings.json` and `translations/en.json` must be identical** - CI enforces this.

---

## Decision log

- **Nested `AGENTS.md` files**: deferred. This repository is a single-package integration with a stable module map; one root `AGENTS.md` plus `docs/REPO_LAYOUT.md` keeps routing clear without extra maintenance overhead.

---

## Common pitfalls

- **Partial category registration** - the most common mistake. Adding a category to `const.py` but forgetting `strings.json`/`translations/en.json` breaks the config flow UI silently. Always run `make doc-check` after touching categories.
- **Blocking I/O in coordinator** - `UniFiAlertsCoordinator._async_update_data` must stay async-clean. Importing and calling `requests` or any sync HTTP here will block the HA event loop.
- **Caching state in entities** - entities must read state from `self.coordinator.data` on every `@property` call. Storing a local copy causes stale UI after coordinator updates.
- **`manifest.json` key order** - hassfest rejects any manifest where keys after `domain`/`name` are not alphabetical. Always check with `make validate` after editing this file.
- **Squash-merging `dev > main`** - use "Create a merge commit" only. Squash leaves the release commit out of `dev`'s ancestry and causes merge conflicts on the next cycle.
- **Short or tag-ref GitHub Actions SHAs** - Dependabot proposes SHA bumps weekly; always resolve the new SHA fully before merging.
