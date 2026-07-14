# GitHub Copilot Instructions

> Claude-specific working style and the full non-negotiable constraint list live in [`CLAUDE.md`](../CLAUDE.md). Read it first.
> Release and branching detail lives in [`docs/RELEASING.md`](../docs/RELEASING.md).

---

## Shared facts (defined once in AGENTS.md)

Repo purpose, the tech stack, the build/test command block, the repository structure, and the key source-file map all live in [`AGENTS.md`](../AGENTS.md). Read that first; it is the single source for those facts, so they are not repeated here. `scripts/validate_docs.py` fails the build if the shared blocks are copied back into this file.

## Non-negotiable rules (summary)

Canonical source: [`AGENTS.md` > Hard rules](../AGENTS.md#hard-rules).
Claude-specific additions and rationale: [`CLAUDE.md`](../CLAUDE.md#non-negotiable-constraints).

## Branching & versioning

- Work on `dev`; `main` is stable-only.
- `main` version format: `X.Y.Z`; `dev` format: `X.Y.Z-preN` (or stable when preparing a release).
- Feature branches: `claude/*` or `feature/*`, always branched from `dev`.
- Claude cannot push tags; provide the user with the exact `git tag` + `git push origin <tag>` command after a version-bump PR merges.

See [`docs/RELEASING.md`](../docs/RELEASING.md) for the full release workflow.

## Ways of working: outstanding work and findings

- **Work is tracked in GitHub Issues**, not in `docs/TODO.md` (now a taxonomy pointer). Pick work by milestone (`v1.8.0`, `v1.9.0`, `v2.0.0`), then `priority:`, then `size:`. Close items by referencing them in the PR (`Closes #NN`).
- **When you spot something worth tracking** (a bug, a hardening gap, tech debt, a doc gap): confirm with the maintainer before opening an issue. Do not file issues unprompted or in bulk. On approval, use the **Task** issue template (or Bug / Feature where they fit) and apply one category label, one `size: S|M|L`, one `priority: high|medium|low`, and the target milestone. See `docs/TODO.md` for the taxonomy and `scripts/seed_issues.py` for bulk seeding.

## Maintenance matrix

What must be updated when specific parts of the codebase change.

### Adding a new alert category

| File | Change required |
| ---- | --------------- |
| `custom_components/unifi_alerts/const.py` | Add `CATEGORY_<NAME>` constant; add to `ALL_CATEGORIES`, `CATEGORY_ICONS`, `CATEGORY_ICONS_OK`; add all `EVT_*` keys to `UNIFI_KEY_TO_CATEGORY` |
| `custom_components/unifi_alerts/strings.json` | Add `"cat_<name>"` label to `config.step.categories.data`, `config.step.finish.data`, `options.step.options.data`; add webhook URL label |
| `custom_components/unifi_alerts/translations/en.json` | Mirror every change to `strings.json` exactly |
| `tests/unit/conftest.py` | Add category to fixture category lists |
| `tests/integration/conftest.py` | Add category to fixture category lists |

Run `make doc-check` for translation parity and `make validate` for HACS/docs preflight.

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
| `tests/unit/coordinator/` | Coordinator unit tests |
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