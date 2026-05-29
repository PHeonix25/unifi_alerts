# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-05-29):** v1.7.0 released. Path to v2.0.0: v1.8.0 (incremental polish; backlog lives in `docs/TODO.md`), v2.0.0 (HACS default).

> **Branching model:** see `CLAUDE.md § Branching strategy and versioning`.

---

## v2.0.0: HACS default catalogue

Prerequisites for submitting to <https://github.com/hacs/default>.

- [ ] All v1.x items in `docs/TODO.md` resolved.
- [ ] Submit PR to `hacs/default`.

---

## Deferred / low priority

- Extract `_device_info()` duplication into a shared `entity_base.py` mixin (only if maintenance burden grows).
- Configurable site per category (power-user feature).
- Optional integration test for the full rotation cycle (options-flow > entry-update > reload > re-register, end-to-end). Each step is unit-tested already; the integration test would catch wiring regressions.
