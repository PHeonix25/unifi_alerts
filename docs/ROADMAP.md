# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-07-24):** v2.0.0 (HACS default catalogue) shipped stable on 2026-07-24; the umbrella submission issue (#143) is closed and a PR is open against `hacs/default`. A same-day v2.0.1 patch release followed, fixing the min_severity selector rendering as an untranslated radio-button list instead of a dropdown (#375). The next cycle (v2.1.0) is already seeded with review follow-ups from the severity-filtering feature (#331): UI copy, a diagnostic trail for filtered alerts, and several `severity.py` cleanups. Item-level work is tracked in GitHub Issues, grouped by milestone: <https://github.com/PHeonix25/unifi_alerts/milestones>.

> **Branching model:** see `CLAUDE.md § Branching and releasing`.

---

## v2.1.0 - Severity follow-through and test coverage

Finish the severity-filtering feature started in #331 and close the test gaps on the paths users depend on most. Adds the first way to verify a webhook setup without waiting for a real alert.

Main threads: the #331 review follow-ups (UI copy, filtered-alert diagnostics, `severity.py` cleanups), coverage for entity actions, webhook edge cases and coordinator/service error handling, a send-test-alert button, and the config flow accessibility blockers.

## v2.2.0 - Structural simplification

Reduce surface area, internal and user-facing. Splits the coordinator's persistence and filtering responsibilities into their own modules, and cuts the entity count and first-run configuration load that overwhelm new users.

Main threads: coordinator extraction, fewer diagnostic entities, a two-tier config flow, webhook and diagnostics hardening, and discovery/failover coverage.

## v2.3.0 - Polish and de-cluttering

Low-risk tidying once the structural work has settled. No new capability.

Main threads: code and test simplification, removal of redundant tests, opt-in message sensors, and UX copy polish.

---

## Deferred / low priority

- Extract `_device_info()` duplication into a shared `entity_base.py` mixin (only if maintenance burden grows; currently intentional for platform isolation).
- Configurable site per category (power-user feature).
