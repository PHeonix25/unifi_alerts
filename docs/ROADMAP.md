# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-09-18):** v2.1.0 shipped and tagged; the v2.2.0 cycle is open at `2.2.0-pre1`. v2.1.0 closed the "severity follow-through and test coverage" theme: `severity_level` as an entity attribute (#356), a diagnostic trail for silently-filtered alerts (#357), entity state and attribute test coverage (#385), the rollup sensors' availability inconsistency (#417), the unmapped `VPN` and `SOFTWARE_UPDATES` v2 category enums that silently dropped events (#411), and earlier in the cycle the UniFi Network 10.6+ setup failure (#406), the #331 review follow-ups and the `_device_info()` extraction (#383). Descoped: the "Test Webhook" button (#384), whose literal spec doesn't fit HA's config-flow architecture. Item-level work is tracked in GitHub Issues, grouped by milestone: <https://github.com/PHeonix25/unifi_alerts/milestones>.

> **Branching model:** see `CLAUDE.md § Branching and releasing`.

---

## v2.2.0 - Structural simplification

Reduce surface area, internal and user-facing. Splits the coordinator's persistence and filtering responsibilities into their own modules, and cuts the entity count and first-run configuration load that overwhelm new users.

Main threads: coordinator extraction, fewer diagnostic entities, a two-tier config flow, webhook and diagnostics hardening, discovery/failover coverage, and a non-No_Filter default `min_severity` for chatty categories (#355, wants a product decision before implementation).

## v2.3.0 - Polish and de-cluttering

Low-risk tidying once the structural work has settled. No new capability.

Main threads: code and test simplification, removal of redundant tests, opt-in message sensors, and UX copy polish.

---

## Deferred / low priority

- Configurable site per category (power-user feature).
