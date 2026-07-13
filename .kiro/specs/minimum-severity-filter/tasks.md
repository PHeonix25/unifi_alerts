# Implementation Plan: Minimum Severity Filter

## Overview

Convert the minimum-severity-filter design into incremental coding steps. Work proceeds bottom-up: the pure `severity.py` normalization/gating module and the `const.py` config key first (nothing else can be built without them), then the `models.py` computed property and config surface, then the two consumers (`coordinator.py` push/poll paths and `config_flow.py` Config_Flow/Options_Flow selectors), then documentation/changelog/translation parity, then end-to-end integration tests, then a final full-suite checkpoint.

## Tasks

- [x] 1. Add `hypothesis` as a pinned dev dependency
  - Add `hypothesis==6.153.1` to `requirements-dev.txt`
  - _Requirements: Testing Strategy (design.md)_

- [x] 2. Implement `severity.py` normalization and gating module
  - [x] 2.1 Create `custom_components/unifi_alerts/severity.py` with constants
    - Define `SEVERITY_LOW`, `SEVERITY_MEDIUM`, `SEVERITY_HIGH`, `SEVERITY_VERY_HIGH`, `SEVERITY_ORDER`
    - Define `MIN_SEVERITY_NO_FILTER = "no_filter"` and `MIN_SEVERITY_ORDER`
    - Define the `_SEVERITY_SYNONYMS` mapping (critical/urgent→VERY_HIGH, error/high→HIGH, warning/medium→MEDIUM, info/low/notice→LOW)
    - _Requirements: 1.1, 2.1_

  - [x] 2.2 Implement `normalize_severity(raw: str) -> str`
    - Case-insensitive, whitespace-trimmed match against canonical Severity_Level names, then against `_SEVERITY_SYNONYMS`
    - Fall back to `SEVERITY_LOW` for empty or unmatched input
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3_

  - [x] 2.3 Write property test: Normalizer totality (mandatory)
    - **Property 1: Normalizer totality**
    - **Validates: Requirements 1.1**
    - In `tests/unit/test_severity.py`, using `hypothesis` with arbitrary strings (including empty/Unicode), assert `normalize_severity` always returns one of the four Severity_Levels and never `MIN_SEVERITY_NO_FILTER`

  - [x] 2.4 Write property test: Canonical and synonym matching is case- and whitespace-insensitive (mandatory)
    - **Property 2: Canonical and synonym matching is case- and whitespace-insensitive**
    - **Validates: Requirements 1.2, 2.1, 2.3**
    - In `tests/unit/test_severity.py`, generate arbitrary casing/whitespace-padding variants of each canonical name and synonym, assert correct mapped Severity_Level

  - [x] 2.5 Write property test: Unmatched or empty input falls back to LOW (mandatory)
    - **Property 3: Unmatched or empty input falls back to LOW**
    - **Validates: Requirements 2.2**
    - In `tests/unit/test_severity.py`, generate arbitrary strings filtered to exclude canonical names/synonyms (after lowercase+strip), assert result is `SEVERITY_LOW`

  - [x] 2.6 Implement `meets_minimum(severity_level: str, minimum: str) -> bool`
    - Always `True` when `minimum == MIN_SEVERITY_NO_FILTER`
    - Otherwise compare `SEVERITY_ORDER` indices
    - _Requirements: 6.3, 6.5, 7.6_

  - [x] 2.7 Implement `get_effective_min_severity(config, category) -> str`
    - Resolve `config[CONF_MIN_SEVERITY]` dict lookup with `No_Filter` default for absent map or absent category key
    - Validate the resolved value against `MIN_SEVERITY_ORDER`, coercing any unrecognised stored value back to `MIN_SEVERITY_NO_FILTER` (per Error Handling in design.md)
    - _Requirements: 5.1, 5.2_

  - [x] 2.8 Write property test: Effective-setting resolution defaults missing data to No_Filter (mandatory)
    - **Property 7: Effective-setting resolution defaults missing data to No_Filter**
    - **Validates: Requirements 5.1, 5.2**
    - In `tests/unit/test_severity.py`, generate configs with the `min_severity` map absent, present-but-missing-key, and present-with-key, assert correct resolution in each case

  - [x] 2.9 Implement `filter_by_min_severity(alerts, minimum) -> list[UniFiAlert]`
    - Pure filter with no `enabled` dependency; returns `alerts` unchanged when `minimum == MIN_SEVERITY_NO_FILTER`
    - _Requirements: 7.1, 7.4, 7.6_

- [x] 3. Add `CONF_MIN_SEVERITY` config key to `const.py`
  - Add `CONF_MIN_SEVERITY: Final = "min_severity"`
  - _Requirements: 3.2, 4.2, 5.1_

- [x] 4. Checkpoint - Run the test suite (mandatory gate, not optional)
  - Run the full test suite and confirm every test passes before proceeding. This is a mandatory gate, including all property tests written so far — do not proceed to subsequent tasks until all tests pass. If a test fails, fix the implementation or the test before moving on.

- [x] 5. Add `severity_level` property and config typing to `models.py`
  - [x] 5.1 Add `UniFiAlert.severity_level` computed property
    - Returns `normalize_severity(self.severity)`; not a dataclass field, not touched by `to_dict`/`from_dict`
    - _Requirements: 1.1, 1.3_

  - [x] 5.2 Add `min_severity: dict[str, str]` key to `UniFiClientConfig` TypedDict
    - _Requirements: 3.2, 4.2_

  - [x] 5.3 Write property test: Raw severity is preserved independent of normalization (mandatory)
    - **Property 4: Raw severity is preserved independent of normalization**
    - **Validates: Requirements 1.3**
    - In `tests/unit/test_severity.py` (constructing `UniFiAlert` instances directly), assert `alert.severity` equals the original raw string (subject to existing 32-char truncation) regardless of `severity_level`

- [x] 6. Wire severity gating into `coordinator.py` push path
  - [x] 6.1 Read `_min_severity` config in `UniFiAlertsCoordinator.__init__`
    - `self._min_severity: dict[str, str] = config.get(CONF_MIN_SEVERITY, {})`
    - _Requirements: 3.2, 5.1_

  - [x] 6.2 Insert severity gate into `push_alert`
    - Gate placed after the existing `enabled` check and before dedup/`apply_alert`
    - On below-threshold: update only `last_webhook_at`, call `_schedule_persist()` and `async_set_updated_data`, then return (no dedup window touched)
    - On at/above-threshold or `No_Filter`: proceed with existing unchanged acceptance logic
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 8.1, 9.1, 9.2_

  - [x] 6.3 Write property test: Below-threshold push on an enabled category is a true no-op (mandatory)
    - **Property 8: Below-threshold push on an enabled category is a true no-op**
    - **Validates: Requirements 6.1, 6.2**
    - In `tests/unit/coordinator/test_push_dedup.py`, generate arbitrary prior `CategoryState`, a minimum from `{LOW, MEDIUM, HIGH, VERY_HIGH}`, and a strictly-below alert; assert `is_alerting`/`alert_count`/`open_count`/`last_alert` unchanged

  - [x] 6.4 Write property test: Disabled category never evaluates the gate (mandatory)
    - **Property 9: Disabled category never evaluates the gate**
    - **Validates: Requirements 6.4**
    - In `tests/unit/coordinator/test_push_dedup.py`, generate arbitrary disabled `CategoryState`, arbitrary minimum, arbitrary-severity alert; assert entire state unchanged after `push_alert`

  - [x] 6.5 Write property test: At-or-above-threshold or No_Filter push is accepted exactly as before (mandatory)
    - **Property 10: At-or-above-threshold or No_Filter push is accepted exactly as before this feature**
    - **Validates: Requirements 6.3, 6.5**
    - In `tests/unit/coordinator/test_push_dedup.py`, generate arbitrary prior state and either an at/above-threshold alert or a `No_Filter` setting with arbitrary severity; assert `is_alerting=True`, `alert_count` incremented, `last_alert` updated, `open_count` incremented when newer than watermark

  - [x] 6.6 Write property test: `last_webhook_at` still advances on a gated push (mandatory)
    - **Property 11: `last_webhook_at` still advances on a gated push**
    - **Validates: Requirements 8.1**
    - In `tests/unit/coordinator/test_push_dedup.py`, generate an enabled category, a minimum from `{LOW, MEDIUM, HIGH, VERY_HIGH}`, and a below-threshold alert; assert `last_webhook_at` updates to `received_at` while other fields stay unchanged

- [x] 7. Wire severity gating into `coordinator.py` poll path
  - [x] 7.1 Insert severity filter step into `_async_update_data`
    - Apply `filter_by_min_severity` before the existing watermark filter; call `_track_newest_seen` with the severity-filtered list
    - Keep the existing `if not state.enabled: continue` guard unchanged and preceding the new filter step
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 7.2 Write property test: Severity-filtered polling drives open_count, alerting selection, and watermark consistently (mandatory)
    - **Property 12: Severity-filtered polling drives open_count, alerting selection, and the newest-seen watermark consistently**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.6, 7.7**
    - In `tests/unit/coordinator/test_polling.py`, generate an enabled category, arbitrary polled alarms with varying severities, and a minimum from `{No_Filter, LOW, MEDIUM, HIGH, VERY_HIGH}`; assert `open_count`, `is_alerting`/`last_alert` selection, and the newest-seen watermark all derive from the same severity-eligible, watermark-eligible subset

  - [x] 7.3 Write property test: Disabled category is untouched by a poll cycle regardless of severity content (mandatory)
    - **Property 13: Disabled category is untouched by a poll cycle regardless of severity content**
    - **Validates: Requirements 7.5**
    - In `tests/unit/coordinator/test_polling.py`, generate a disabled category with arbitrary prior `is_alerting`/`last_alert`/`open_count`, arbitrary polled alarms, and arbitrary minimum; assert all three fields unchanged after a poll cycle

- [x] 8. Checkpoint - Run the test suite (mandatory gate, not optional)
  - Run the full test suite and confirm every test passes before proceeding. This is a mandatory gate, including all property tests written so far — do not proceed to subsequent tasks until all tests pass. If a test fails, fix the implementation or the test before moving on.

- [ ] 9. Add Minimum_Severity_Setting selector to `config_flow.py` Config_Flow
  - [x] 9.1 Define `_MIN_SEVERITY_OPTIONS` and `_min_severity_selector`
    - `SelectOptionDict` entries for `No_Filter`/`LOW`/`MEDIUM`/`HIGH`/`VERY_HIGH` with display labels; shared `SelectSelector` instance
    - _Requirements: 3.1_

  - [x] 9.2 Add `min_severity_{category}` field to `async_step_categories` schema
    - One field per category in `ALL_CATEGORIES`, defaulted to `MIN_SEVERITY_NO_FILTER`, alongside existing `cat_{category}` boolean field
    - _Requirements: 3.1_

  - [x] 9.3 Collect and store submitted values on Config_Flow submission
    - Build `min_severity = {cat: user_input.get(f"min_severity_{cat}", MIN_SEVERITY_NO_FILTER) for cat in ALL_CATEGORIES}`
    - Store into `self._entry_data[CONF_MIN_SEVERITY]`
    - _Requirements: 3.2, 3.3_

  - [ ] 9.4 Write property test: Config_Flow categories-step submission round-trips, defaulting omitted categories to No_Filter (mandatory)
    - **Property 5: Config_Flow categories-step submission round-trips per category, defaulting omitted categories to No_Filter**
    - **Validates: Requirements 3.2, 3.3**
    - In `tests/unit/config_flow/test_min_severity.py`, generate arbitrary mappings from a subset of the 7 categories to one of the 5 settings; assert the created entry's stored per-category setting matches submitted values and defaults omitted categories to `No_Filter`

  - [ ] 9.5 Write unit test: Config_Flow categories-step rendering (mandatory)
    - In `tests/unit/config_flow/test_setup.py`, assert each of the 7 categories exposes a `min_severity_{cat}` selector offering the 5 expected options, defaulted to `No_Filter`
    - _Requirements: 3.1_

- [ ] 10. Add Minimum_Severity_Setting selector to `config_flow.py` Options_Flow
  - [x] 10.1 Add `min_severity_{category}` field to `UniFiAlertsOptionsFlow.async_step_categories` schema
    - Pre-fill default via `current_min_severity.get(cat, MIN_SEVERITY_NO_FILTER)`, following the existing options→data→default fallback chain
    - _Requirements: 4.1_

  - [x] 10.2 Collect and stage submitted values on Options_Flow submission
    - Build the same `min_severity` mapping shape as Config_Flow; store into `self._pending_options[CONF_MIN_SEVERITY]`
    - _Requirements: 4.2, 4.3_

  - [ ] 10.3 Write property test: Options_Flow categories-step submission round-trips independent of pre-fill (mandatory)
    - **Property 6: Options_Flow categories-step submission round-trips independent of pre-fill**
    - **Validates: Requirements 4.2, 4.3**
    - In `tests/unit/config_flow/test_min_severity.py`, generate arbitrary previously-stored mappings and arbitrary newly-submitted mappings (which may differ arbitrarily, including omitted categories); assert persisted values match the submission, defaulting omitted categories to `No_Filter`, regardless of pre-fill

  - [ ] 10.4 Write unit test: Options_Flow categories-step pre-fill (mandatory)
    - In `tests/unit/config_flow/test_min_severity.py`, assert pre-fill resolves correctly both from a legacy entry (no stored `min_severity`) and from an entry with an explicit stored value
    - _Requirements: 4.1_

- [ ] 11. Checkpoint - Run the test suite (mandatory gate, not optional)
  - Run the full test suite and confirm every test passes before proceeding. This is a mandatory gate, including all property tests and unit tests written so far — do not proceed to subsequent tasks until all tests pass. If a test fails, fix the implementation or the test before moving on.

- [x] 12. Verify webhook auth-before-gate ordering
  - [x] 12.1 Write unit test: severity gate is unreachable before token auth succeeds (mandatory)
    - Extend `tests/unit/test_webhook_handler.py`: an invalid-token request carrying an otherwise-accepted alert never invokes `push_alert` and still returns HTTP 401
    - _Requirements: 9.1, 9.2_

- [ ] 13. Add localization keys to `strings.json` and `translations/en.json`
  - Add the 14 `min_severity_{category}` keys under both `config.step.categories.data` and `options.step.categories.data` in `strings.json`
  - Mirror every key byte-identically into `translations/en.json`
  - _Requirements: 10.1_

- [ ] 14. Document severity normalization in `docs/UNIFI.md`
  - Add a "Severity normalization" section covering the four-level ordering, the `No_Filter` sentinel and its position outside that ordering, the full synonym table, and the empty/unmatched fallback to `LOW`
  - _Requirements: 10.2_

- [ ] 15. Add `CHANGELOG.md` entry
  - Add one `### Added` bullet under `[Unreleased]` describing the per-category minimum-severity option, referencing issue #135
  - _Requirements: 10.3, 10.4_

- [ ] 16. Add integration test coverage (mandatory)
  - [ ] 16.1 Write integration test: webhook push below then at/above threshold (mandatory)
    - Extend `tests/integration/test_webhook.py`: full config-entry setup with a non-default `min_severity` for one category, a webhook push below threshold followed by one at/above threshold, confirming entity state only changes on the second push
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 8.1_

  - [ ] 16.2 Write integration test: config-entry lifecycle with non-default min_severity (mandatory)
    - Extend `tests/integration/test_lifecycle.py`: full config-entry setup/reload with a non-default `min_severity` for one category, confirming the stored setting survives entry lifecycle operations and gates alerts accordingly
    - _Requirements: 5.1, 5.2, 3.2, 4.2_

- [ ] 17. Final checkpoint - Run full validation suite (mandatory gate, not optional)
  - Run `make check` (lint + typecheck + validate + test) and confirm every check passes, including every property test, unit test, and integration test added in this plan. This is a mandatory gate — fix any failures and re-run until all checks pass. The feature is not complete until this fully passes.
  - _Requirements: 10.1, 10.4_

## Notes

- Every task in this plan is mandatory, including every property-based test, unit/example test, and integration test task. None of them are optional and none may be skipped: each test listed here directly validates one of the design's correctness properties or acceptance criteria, and skipping any of them leaves that property or criterion unverified.
- Checkpoint tasks (4, 8, 11, 17) are hard gates, not optional check-ins: all tests (and, for Task 17, the full `make check` suite) must pass before moving on to the next task.
- `severity.py` and the `CONF_MIN_SEVERITY` constant (Tasks 2-3) must land before any consumer changes (Tasks 5-10), since `models.py`, `coordinator.py`, and `config_flow.py` all import from `severity.py`/`const.py`.
- `models.py` (Task 5) must land before `coordinator.py` (Tasks 6-7), since the push/poll gates call `alert.severity_level`.
- `coordinator.py` and `config_flow.py` changes (Tasks 6-10) are independent of each other and their relative order may vary, but both sets of tasks are required — neither is optional regardless of sequencing. They are sequenced coordinator-first here since the poll/push gates are the core behavior and the config UI is how users set the values consumed by that behavior.
- Documentation/changelog/localization tasks (13-15) have no code dependencies on each other and their relative order may vary, but all three are required — none may be skipped. They are sequenced after the behavior they document is implemented.
- Integration tests (Task 16) depend on both the coordinator gating (Tasks 6-7) and the config flow selectors (Tasks 9-10) since they exercise full entry setup plus webhook push. Both integration test sub-tasks (16.1, 16.2) are mandatory.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2.1", "3"] },
    { "id": 1, "tasks": ["2.2", "2.6", "2.9"] },
    { "id": 2, "tasks": ["2.3", "2.4", "2.5", "2.7"] },
    { "id": 3, "tasks": ["2.8", "5.1", "5.2"] },
    { "id": 4, "tasks": ["5.3", "6.1", "9.1"] },
    { "id": 5, "tasks": ["6.2", "7.1", "9.2", "10.1"] },
    { "id": 6, "tasks": ["6.3", "6.4", "6.5", "6.6", "7.2", "7.3", "9.3", "10.2", "12.1"] },
    { "id": 7, "tasks": ["9.4", "9.5", "10.3", "10.4"] },
    { "id": 8, "tasks": ["13", "14", "15"] },
    { "id": 9, "tasks": ["16.1", "16.2"] }
  ]
}
```
