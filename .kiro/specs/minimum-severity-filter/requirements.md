# Requirements Document

## Introduction

This feature closes the remaining half of GitHub Issue #135. PR #210 (shipped in v1.9.0) already exposed severity as an entity attribute (`severity`, `last_severity`); that work is done and out of scope here.

The remaining scope is an integration-level minimum-severity option that makes noisy categories (e.g. `network_device`, `network_client`) usable while enabled instead of muted entirely: an alert below a category's configured minimum severity must be a true no-op - not accepted, not counted, and not advancing any state - on both the webhook push path and the legacy/v2 polling paths. Because v2 system-log severities (`LOW`/`MEDIUM`/`HIGH`/`VERY_HIGH`) and legacy alarm severities (inconsistent free-form strings, sometimes empty) currently have no common scale, this feature also introduces a normalization step that produces a consistent, ordered severity for every alert regardless of ingestion path, so the minimum-severity comparison is meaningful everywhere and so automations can key off severity reliably. This feature also introduces an explicit "No Filter" (OFF) setting value so a category can be configured to bypass the minimum-severity gate entirely, distinct from setting the threshold to the lowest severity level.

## Glossary

- **System**: The UniFi Alerts integration's alert-processing components (`UniFiAlertsCoordinator`, `UniFiAlert`, `CategoryState`) that construct, gate, and apply alerts.
- **Severity_Level**: A normalized, ordered severity value assigned to every alert. The valid values are `LOW`, `MEDIUM`, `HIGH`, and `VERY_HIGH`, ordered `LOW < MEDIUM < HIGH < VERY_HIGH`. Every alert's normalized severity resolves to exactly one Severity_Level. `No_Filter` (see below) is not a Severity_Level and is never assigned as an alert's own normalized severity.
- **Severity_Normalizer**: The part of the System that maps a raw severity string (from a webhook payload, a legacy alarm record, or a v2 system-log event) to exactly one Severity_Level.
- **Minimum_Severity_Setting**: A per-category configuration value selected from the ordered set `No_Filter < LOW < MEDIUM < HIGH < VERY_HIGH`. When set to a Severity_Level (`LOW`, `MEDIUM`, `HIGH`, or `VERY_HIGH`), an alert in that category is not accepted if its normalized Severity_Level is below that value. When set to `No_Filter`, every alert in that category is accepted regardless of its normalized Severity_Level, with no severity comparison performed. `No_Filter` is a distinct configuration state of Minimum_Severity_Setting - it is not a Severity_Level and is never assigned as an alert's own normalized severity.
- **No_Filter**: The special Minimum_Severity_Setting sentinel value, displayed to users as "No Filter" and referred to in this document as OFF, that accepts every alert in a category regardless of its normalized Severity_Level, with no severity comparison performed. For the purposes of the Minimum_Severity_Setting selector's ordering, `No_Filter` sits below `LOW`, giving the ordering `No_Filter < LOW < MEDIUM < HIGH < VERY_HIGH`. This ordering applies only to the Minimum_Severity_Setting selector: it does not make `No_Filter` a Severity_Level, and `No_Filter` is never itself assigned as an alert's own normalized severity - only as a category's Minimum_Severity_Setting. An alert's own normalized severity remains restricted to exactly one of `LOW`, `MEDIUM`, `HIGH`, or `VERY_HIGH` (see Requirement 1, Requirement 2).
- **Enabled Category**: An alert category (one of the 7 defined in `ALL_CATEGORIES`) whose `CategoryState.enabled` is `True`.
- **Config_Flow**: The initial setup flow shown when the integration is first added.
- **Options_Flow**: The reconfiguration flow shown via Settings -> Devices & Services -> UniFi Alerts -> Configure.

## Requirements

### Requirement 1: Severity Normalization Across Ingestion Paths

**User Story:** As an automation author, I want every alert to carry a consistent, normalized severity level regardless of whether it arrived via webhook push, legacy alarm polling, or v2 system-log polling, so that I can build automations that key off severity reliably.

#### Acceptance Criteria

1. WHEN the System constructs a `UniFiAlert` from a webhook payload, a legacy alarm record, or a v2 system-log event, THE Severity_Normalizer SHALL assign exactly one of `LOW`, `MEDIUM`, `HIGH`, or `VERY_HIGH` as that alert's Severity_Level.
2. WHEN the raw severity string on a v2 system-log event case-insensitively equals `"LOW"`, `"MEDIUM"`, `"HIGH"`, or `"VERY_HIGH"`, THE Severity_Normalizer SHALL assign the identical Severity_Level.
3. THE System SHALL continue to expose the original, unmodified raw severity string via the existing `severity` and `last_severity` attributes, independent of the normalized Severity_Level.

### Requirement 2: Legacy Severity Synonym Mapping and Unmapped Fallback

**User Story:** As an integration maintainer, I want legacy alarm severity strings mapped onto the normalized scale using a documented synonym table, so filtering behaves consistently even though legacy controllers use inconsistent vocabulary.

#### Acceptance Criteria

1. WHEN a raw severity string case-insensitively matches a documented synonym for a Severity_Level (for example `"critical"`/`"urgent"` for `VERY_HIGH`; `"error"`/`"high"` for `HIGH`; `"warning"`/`"medium"` for `MEDIUM`; `"info"`/`"low"`/`"notice"` for `LOW`), THE Severity_Normalizer SHALL assign the corresponding Severity_Level.
2. IF a raw severity string is empty, OR does not case-insensitively match any Severity_Level name or documented synonym, THEN THE Severity_Normalizer SHALL assign Severity_Level `LOW`.
3. THE Severity_Normalizer SHALL match Severity_Level names and synonyms case-insensitively and ignoring leading/trailing whitespace.

### Requirement 3: Per-Category Minimum-Severity Setup Configuration

**User Story:** As a user setting up the integration, I want to set a minimum severity per alert category during initial setup, so that noisy categories can be enabled without accepting every low-value alert.

#### Acceptance Criteria

1. WHEN the Config_Flow displays the categories step, THE Config_Flow SHALL present a Minimum_Severity_Setting selector offering `No_Filter`, `LOW`, `MEDIUM`, `HIGH`, and `VERY_HIGH` as selectable options, defaulted to `No_Filter`, for each of the 7 alert categories.
2. WHEN the user submits the categories step with a Minimum_Severity_Setting selected for a category, THE Config_Flow SHALL store that selected value as the category's Minimum_Severity_Setting on the created config entry.
3. WHERE the user does not change a category's Minimum_Severity_Setting selector, THE Config_Flow SHALL store `No_Filter` as that category's Minimum_Severity_Setting.

### Requirement 4: Per-Category Minimum-Severity Reconfiguration

**User Story:** As a user reconfiguring an existing entry, I want to change the minimum severity per category, so that I can tune noise levels without recreating the integration.

#### Acceptance Criteria

1. WHEN the Options_Flow displays the categories step, THE Options_Flow SHALL present the same Minimum_Severity_Setting selector as the Config_Flow, offering `No_Filter`, `LOW`, `MEDIUM`, `HIGH`, and `VERY_HIGH` as selectable options, pre-filled with each category's currently stored Minimum_Severity_Setting.
2. WHEN the user submits the Options_Flow categories step with updated Minimum_Severity_Setting values, THE Options_Flow SHALL persist the updated per-category Minimum_Severity_Setting values to the config entry.
3. THE Options_Flow SHALL accept and persist a submitted Minimum_Severity_Setting value without requiring it to match the value most recently pre-filled for that category.

### Requirement 5: Backward-Compatible Default for Existing Config Entries

**User Story:** As an existing user upgrading the integration, I want my current alert behavior to stay identical until I explicitly opt in to filtering, so that the upgrade does not silently drop alerts I currently receive.

`No_Filter` is used as this default, rather than `LOW`, because `No_Filter` bypasses the Minimum_Severity_Setting gate entirely and makes the "filtering is disabled" state explicit, while a `LOW` default would depend on the Severity_Normalizer's synonym-mapping and fallback behavior (Requirement 2) continuing to resolve every raw severity string to at least `LOW` - an assumption that holds today but that `No_Filter` does not need to rely on as the severity scale evolves.

#### Acceptance Criteria

1. WHILE a config entry has no stored Minimum_Severity_Setting for a category, THE System SHALL treat that category's Minimum_Severity_Setting as `No_Filter`, overriding any other effective value that would otherwise be computed for that category.
2. WHEN a config entry created before this feature existed is loaded, THE System SHALL apply `No_Filter` as the Minimum_Severity_Setting for every category, so that no alert accepted before this feature existed becomes filtered.

### Requirement 6: Webhook Push Severity Gate

**User Story:** As a user with a noisy category enabled, I want alerts below my configured minimum severity to be a true no-op on the webhook path, so that my counts and state are not disturbed by low-value alerts.

#### Acceptance Criteria

1. WHEN `push_alert` receives an alert for an Enabled Category whose Minimum_Severity_Setting is a Severity_Level and whose normalized Severity_Level is below that category's Minimum_Severity_Setting, THE System SHALL leave that category's `is_alerting`, `alert_count`, `open_count`, and `last_alert` unchanged from their values immediately before the alert arrived.
2. WHEN `push_alert` receives an alert for an Enabled Category whose Minimum_Severity_Setting is a Severity_Level and whose normalized Severity_Level is below that category's Minimum_Severity_Setting, THE System SHALL leave that category's event entity state unchanged, so no new event fires.
3. WHEN `push_alert` receives an alert for an Enabled Category whose Minimum_Severity_Setting is a Severity_Level and whose normalized Severity_Level meets or exceeds that category's Minimum_Severity_Setting, THE System SHALL apply the alert using the same acceptance behavior that existed before this feature (setting `is_alerting`, incrementing `alert_count`, updating `open_count` and `last_alert`, and firing the event entity).
4. IF `push_alert` receives an alert for a category that is not an Enabled Category, THEN THE System SHALL ignore the alert without evaluating the Minimum_Severity_Setting gate, unchanged from behavior before this feature existed.
5. WHEN `push_alert` receives an alert for an Enabled Category whose Minimum_Severity_Setting is `No_Filter`, THE System SHALL apply the alert using the same acceptance behavior described in Acceptance Criterion 3 without comparing the alert's normalized Severity_Level to any threshold, so the alert is always accepted and never treated as a no-op.

### Requirement 7: Polling Path Severity Gate

**User Story:** As a user relying on polling as a backstop, I want polled alarms below my configured minimum severity excluded from open counts and state changes, so that polling and webhooks behave consistently.

#### Acceptance Criteria

1. WHEN the System counts open alarms for a category whose Minimum_Severity_Setting is a Severity_Level during a poll cycle, THE System SHALL exclude alarms whose normalized Severity_Level is below that category's Minimum_Severity_Setting from `open_count`.
2. WHEN the System determines whether to set `is_alerting` and `last_alert` from polled alarms for an Enabled Category whose Minimum_Severity_Setting is a Severity_Level, THE System SHALL consider only alarms whose normalized Severity_Level meets or exceeds that category's Minimum_Severity_Setting.
3. WHEN the System tracks the newest-seen alarm timestamp used to anchor the Clear watermark for a category whose Minimum_Severity_Setting is a Severity_Level, THE System SHALL consider only alarms whose normalized Severity_Level meets or exceeds that category's Minimum_Severity_Setting.
4. WHERE a category's polled alarms are being filtered by a Minimum_Severity_Setting for the purpose of computing `open_count`, THE System SHALL apply that filtering whether or not the category is an Enabled Category.
5. WHILE a category is not an Enabled Category, THE System SHALL NOT evaluate the Minimum_Severity_Setting gate to determine that category's `is_alerting` or `last_alert`, since a disabled category's alerting state is not updated regardless of severity.
6. WHEN a category's Minimum_Severity_Setting is `No_Filter`, THE System SHALL count every alarm for that category toward `open_count` without comparing any alarm's normalized Severity_Level to any threshold, so every alarm is always counted and never excluded.
7. WHEN an Enabled Category's Minimum_Severity_Setting is `No_Filter`, THE System SHALL consider every alarm for that category when determining `is_alerting`, `last_alert`, and the newest-seen alarm timestamp used to anchor the Clear watermark, without comparing any alarm's normalized Severity_Level to any threshold, so every alarm is always considered and never excluded.

### Requirement 8: Webhook Health Signal Independence

**User Story:** As a user verifying webhook wiring, I want the webhook health signal to reflect connectivity regardless of severity filtering, so that a below-threshold alert still proves the webhook path is wired correctly.

#### Acceptance Criteria

1. WHEN `push_alert` receives an alert for an Enabled Category whose normalized Severity_Level is below that category's Minimum_Severity_Setting, THE System SHALL still update `last_webhook_at` for that category.

### Requirement 9: Webhook Authentication Integrity

**User Story:** As a security-conscious maintainer, I want severity filtering to never bypass or weaken the existing webhook token check, so that the new feature cannot be used to circumvent authentication.

#### Acceptance Criteria

1. THE System SHALL evaluate the Minimum_Severity_Setting gate only after the existing webhook token/secret validation has succeeded.
2. IF the webhook token/secret validation fails, THEN THE System SHALL reject the request before evaluating severity, exactly as it did before this feature existed.

### Requirement 10: Documentation and Localization Consistency

**User Story:** As a maintainer, I want the new configuration fields documented and translated consistently, so that the integration passes existing validation tooling and users understand the new option.

#### Acceptance Criteria

1. WHEN a new configuration field is added to `strings.json` for the Minimum_Severity_Setting selector, THE System SHALL add an identical key and value to `translations/en.json`.
2. THE System SHALL document the normalized Severity_Level ordering, the `No_Filter` (OFF) Minimum_Severity_Setting value and its position outside that ordering, the legacy synonym mapping, and the unmapped-severity fallback behavior in `docs/UNIFI.md`.
3. WHEN this feature ships, THE System SHALL include a corresponding bullet under the `[Unreleased]` section of `CHANGELOG.md`.
4. THE System SHALL NOT be considered complete for release until the `docs/UNIFI.md` update, the `CHANGELOG.md` `[Unreleased]` bullet, and byte-identical `strings.json`/`translations/en.json` parity are all present.
