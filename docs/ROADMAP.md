# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-07-24):** v2.0.0 (HACS default catalogue) shipped stable on 2026-07-24; the umbrella submission issue (#143) is closed and a PR is open against `hacs/default`. A same-day v2.0.1 patch release followed, fixing the min_severity selector rendering as an untranslated radio-button list instead of a dropdown (#375). The next cycle (v2.1.0) is already seeded with review follow-ups from the severity-filtering feature (#331): UI copy, a diagnostic trail for filtered alerts, and several `severity.py` cleanups. Item-level work is tracked in GitHub Issues, grouped by milestone: <https://github.com/PHeonix25/unifi_alerts/milestones>.

> **Branching model:** see `CLAUDE.md § Branching and releasing`.

---

## Deferred / low priority

- Extract `_device_info()` duplication into a shared `entity_base.py` mixin (only if maintenance burden grows; currently intentional for platform isolation).
- Configurable site per category (power-user feature).
