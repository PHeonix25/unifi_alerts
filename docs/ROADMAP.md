# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-06-19):** v1.8.0 stable shipped. Path to v2.0.0: v1.9.0 (Localisation and Scale), then v2.0.0 (HACS default catalogue). Item-level work is tracked in GitHub Issues, grouped by milestone: <https://github.com/PHeonix25/unifi_alerts/milestones>.

> **Branching model:** see `CLAUDE.md § Branching strategy and versioning`.

---

## v1.9.0: Localisation and Scale

- Localisation: translatable category labels and the remaining inline strings.
- Scale and efficiency: clamp the watermark fetch window; add probe backoff.
- Capability: severity filtering for noisy categories; a self-healing key map.
- Process: GitHub Issues is now the work tracker (see `docs/TODO.md` for the taxonomy).

Item-level detail: the `v1.9.0` [milestone](https://github.com/PHeonix25/unifi_alerts/milestones).

## v2.0.0: HACS default catalogue

Prerequisites for submitting to <https://github.com/hacs/default>.

- [ ] All `v2.0-gate` issues closed (raw-payload persistence, retention and data-handling statement, Alarm Manager onboarding docs, and localisation maturity).
- [ ] Submit PR to `hacs/default`.

---

## Deferred / low priority

- Extract `_device_info()` duplication into a shared `entity_base.py` mixin (only if maintenance burden grows; currently intentional for platform isolation).
- Configurable site per category (power-user feature).
