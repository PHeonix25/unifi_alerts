# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-05-15):** v1.7.0-pre1 cut from `dev`. Stable v1.7.0 promotion remains; `ARCH-2` (translation keys) is the only outstanding v1.7 code item before the stable release PR. Path to v2.0.0: v1.7.0 (documentation + architecture), v2.0.0 (HACS default).

> **Branching model:** see `CLAUDE.md § Branching strategy and versioning`.

---

## v1.7.0: Documentation + architecture

Closes the remaining documentation gaps and the largest architecture items.

### Architecture

- [ ] **`has_entity_name = True` + `_attr_translation_key`**: move display strings out of platform files into `strings.json`. Unlocks localisation.

### QA

- [ ] **Optional: integration test for full rotation cycle**: options-flow > entry-update > reload > re-register, end-to-end.

---

## v2.0.0: HACS default catalogue

Prerequisites for submitting to <https://github.com/hacs/default>.

- [ ] All v1.x items above resolved.
- [ ] Submit PR to `hacs/default`.

---

## Deferred / low priority

- Extract `_device_info()` duplication into a shared `entity_base.py` mixin (only if maintenance burden grows).
- Configurable site per category (power-user feature).
