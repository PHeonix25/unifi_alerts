# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-08-21):** v2.1.0-pre1 tagged, the first checkpoint of the v2.1.0 cycle. Closed: most of the #331 review follow-ups (UI copy, `severity.py` cleanups, config/options flow accessibility fixes), the `_device_info()` extraction (#383), a webhook secret-leak regression test (#379), and the remaining entity/webhook/coordinator test-coverage gaps (#380, #381, #382). Descoped: the "Test Webhook" button (#384), whose literal spec doesn't fit HA's config-flow architecture. Item-level work is tracked in GitHub Issues, grouped by milestone: <https://github.com/PHeonix25/unifi_alerts/milestones>.

> **Branching model:** see `CLAUDE.md § Branching and releasing`.

---

## v2.1.0 - Severity follow-through and test coverage

First checkpoint (v2.1.0-pre1) closed most of the #331 review follow-ups (`severity.py` cleanups, the min_severity UI copy, config/options flow accessibility fixes), the extracted `_device_info()` helper (#383), a latent `from_dict` severity-truncation fix (#359), a webhook secret-leak regression test (#379), and the remaining entity/webhook/coordinator test-coverage gaps (#380, #381, #382). The "Test Webhook" button (#384) was descoped: a live button embedded in the options flow finish step doesn't fit how HA config flows work, and the 30-second auto-clear timing needs more design thought than a first pass gave it.

Remaining threads: surfacing `severity_level` as an entity attribute (#356), a diagnostic trail for silently-filtered alerts (#357), a non-No_Filter default `min_severity` for chatty categories (#355, wants a product decision before implementation), and entity state/attribute test coverage (#385).

## v2.2.0 - Structural simplification

Reduce surface area, internal and user-facing. Splits the coordinator's persistence and filtering responsibilities into their own modules, and cuts the entity count and first-run configuration load that overwhelm new users.

Main threads: coordinator extraction, fewer diagnostic entities, a two-tier config flow, webhook and diagnostics hardening, and discovery/failover coverage.

## v2.3.0 - Polish and de-cluttering

Low-risk tidying once the structural work has settled. No new capability.

Main threads: code and test simplification, removal of redundant tests, opt-in message sensors, and UX copy polish.

---

## Deferred / low priority

- Configurable site per category (power-user feature).
