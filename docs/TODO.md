# TODO

Outstanding work only. Items are removed when they ship; completion lives in `docs/HISTORY.md`, and the per-release plan lives in `docs/ROADMAP.md`.

## 🟢 Nice-to-have

- **HACS default catalogue submission**: open the PR to <https://github.com/hacs/default> once all v1.x items below are closed.
- **Tier 2 docs linter (markdownlint)**: layer `markdownlint-cli2` on top of `scripts/validate_docs.py` to catch structural issues (heading-level skips, mixed list markers, bare URLs, trailing whitespace) that a regex linter cannot. Adds a Node dependency; commit a `.markdownlint.json` config tuned for this repo. Run it from CI's `lint` job and the pre-push hook alongside the existing prose check.

## Reliability / correctness

- **`SYSTEM_LOG_KEY_TO_CATEGORY` is incomplete** (`const.py`): the v2 system-log key map was seeded from field-confirmed events on Network 10.3.58 (UCG-Ultra) and the documented API schema. Additional keys will surface in the wild; add them as users report unclassified v2 events. Coarse-grained fallback via `SYSTEM_LOG_CATEGORY_FALLBACK` (broad enum) keeps events in roughly the right category until key-level entries are added.

## Type safety / tech debt

- **`mypy strict = false`**: migrate `UniFiClient.config: dict[str, Any]` to a `TypedDict` or frozen dataclass, then bump `pyproject.toml` to `strict = true`.

## Testing

- **Optional: integration test for full rotation cycle**: options-flow > entry-update > reload > re-register, end-to-end. Each step is unit-tested already.

## Architecture

- **Entity naming via `_attr_translation_key`**: all four platform files hard-code `_attr_name = f"{CATEGORY_LABELS[cat]} ..."`. Migrate to `has_entity_name = True` + `_attr_translation_key` so strings live in `strings.json`. Unlocks localisation.
- **Split `tests/unit/test_config_flow.py` into a package**: ~1405 lines with four logically independent classes; rebase chains across classes produce interleaved conflicts. Convert to `tests/unit/config_flow/{__init__,conftest,test_setup,test_options,test_reauth}.py`.

## Known issues

- **`_device_info()` duplication**: duplicated identically across `binary_sensor.py`, `sensor.py`, `event.py`, `button.py`. Intentional for platform isolation; extract to a shared `entity_base.py` only if it becomes a maintenance burden.
