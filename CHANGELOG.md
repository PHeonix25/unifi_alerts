# Changelog

## [Unreleased]

### Security

- `UniFiAlert.to_dict()` no longer persists the `raw` UniFi payload to `.storage`. That payload carried unredacted client MACs, IP addresses, and hostnames, and could contain non-JSON-safe values that would crash `Store.async_save`. Persistence now emits an explicit scalar field list (`category`, `message`, `received_at`, `key`, `device_name`, `site`, `severity`); `from_dict()` still defaults `raw` to `{}` on read so existing stored entries continue to load. Closes #115.

### Internal

- Added test coverage reporting via Codecov: `pytest-cov` added to dev requirements, 95% floor enforced in CI and locally (`--cov-fail-under=95`), XML report uploaded to Codecov on every push, live badge added to README and info.md. `make coverage` generates an HTML report locally; `.coverage`, `coverage.xml`, and `htmlcov/` added to `.gitignore`.

## [1.7.0] - 2026-05-29

### Security

- Webhook handler now rejects requests with HTTP 500 when no bearer secret is configured, rather than accepting them. Config entries missing `webhook_secret` are backfilled during migration to schema version 3. ([#94])
- Added explicit `permissions: contents: read` to `ci.yml`, `version-check.yml`, and `copilot-setup-steps.yml`. Closes a CodeQL "Workflow does not contain permissions" finding on `copilot-setup-steps.yml` and pre-emptively scopes the other two read-only workflows to the same minimum. `release.yml` and `pr-labeler.yml` already had explicit blocks. ([#111])

### Documentation

- Reconciled documentation against current code: corrected test directory layout in REPO_LAYOUT (unit/integration subpackages with three conftest files), fixed button platform table row in HOMEASSISTANT (both classes now inherit CoordinatorEntity), updated HA minimum version in info.md (2024.5 not 2026.1.0), corrected HISTORY.md update guidance in DEVELOPING (bump-PR only, not per-PR), updated conftest diagram in TESTING (three conftest files), and removed already-shipped automation-edge-case item from ROADMAP and TODO.
- Added Troubleshooting guide (docs/TROUBLESHOOTING.md) covering four common setup scenarios.
- Added tested-controllers matrix, privacy/data-retention section, and uninstall instructions to README.
- Added local-network-only warning to info.md first paragraph.
- Updated setup-flow finish step to stress copying webhook URLs before clicking Submit.
- Restructured README into a standard flow (Features > Requirements > Installation > Setup > Entities > Privacy > Uninstall > Support > Contributing), merged the two duplicate tested-consoles tables into one, and moved Lovelace/automation examples to `docs/EXAMPLES.md`. Slimmed info.md by removing duplicated local-network warning and a redundant link block. README dropped from 331 to 186 lines without losing user-facing content.
- Rewrote `AGENTS.md` as a self-contained agent context file with the repo map, the six-step category-registration walkthrough, and the common-pitfalls list. Added a maintenance matrix to `.github/copilot-instructions.md` covering the four common change cascades (new category, webhook handler, coordinator shape, `UniFiClientConfig` / `UniFiAlert`). Added `.github/PULL_REQUEST_TEMPLATE.md` and an "AI Ready" badge to README.
- Added six Copilot agent definitions under `.github/agents/` (SE Lead, QE Lead, Security Lead, Responsible AI, Product Manager, Technical Debt Remediation) with named personas and a unified Identity / Mission / Core Principles / Workflow / Output Format / Anti-Patterns structure.

### Internal

- Split `tests/unit/test_config_flow.py` (1565 lines) into `tests/unit/config_flow/` package with separate files per flow type to reduce rebase conflicts.
- Confirmed `SensorStateClass.MEASUREMENT` on open-count and rollup-count sensors; no `SensorDeviceClass` is set (none of the HA built-ins fit an alert counter).
- Improved code comments on webhook dedup, polling-vs-webhook alert_count invariant, acknowledgement watermark, and system-log probe. Clarified webhook body decode-failure log message.
- Introduced `UniFiClientConfig` TypedDict in `models.py` to replace `dict[str, Any]` config dicts passed to `UniFiClient`, `UniFiAlertsCoordinator`, and `WebhookManager`. Pure refactor; no behaviour change. Prerequisite for flipping `mypy strict = true`.
- Enabled `mypy --strict` across the integration (`pyproject.toml`). All call sites use the `UniFiClientConfig` TypedDict from ARCH-1; residual fixes were limited to parameterising generic `dict`/`list`/`Store`/`Task` annotations and routing the `DeviceInfo` import through `homeassistant.helpers.device_registry` (its canonical module) so mypy accepts the export.
- Moved `make lint` and `make typecheck` from inline shell invocations to `scripts/run_lint.py` and `scripts/run_typecheck.py` so the same logic runs identically on Linux, macOS, and Windows without per-platform shims.
- Added `.github/workflows/copilot-setup-steps.yml` so GitHub Copilot coding-agent sessions self-provision Python 3.12, a venv, and `requirements-dev.txt` on first run.
- Widened `scripts/validate_docs.py` to scan every `*.md` in the repo recursively (excluding `.git`, `.venv`, `node_modules`, `.claude`, `.mypy_cache`, `.ruff_cache`). New markdown anywhere in the tree now inherits the same prose rules automatically.
- Added 232 lines of targeted branch-path unit tests across `test_options.py`, `test_reauth.py`, `test_coordinator.py`, and `test_models.py`. Pure coverage uplift; no production-code changes.
- Migrated all entity display names to `_attr_translation_key` + `_attr_translation_placeholders`; English strings now live in `strings.json` and `translations/en.json`. Existing automations are unaffected because `unique_id` values are unchanged.

## [1.6.0] - 2026-05-11

### Changed

- `make lint` now covers `tests/` in addition to `custom_components/`. Zero pre-existing `I001`/`F401` issues were present at the time the scope was widened; the target was simply not wired up.
- Polling now uses the v2 `system-log/all` endpoint when the controller exposes it (detected via a one-shot probe of `/system-log/count`). The v2 endpoint accepts `timestampFrom` and pagination, so recent alarms on busy controllers (more than ~33 alarms/day) are no longer truncated out of the polled response. Controllers without the endpoint continue to use the legacy `/list/alarm` path; no user action required.

### Added

- Added an "Updating the integration" section to README.md between Installation and Setup, explaining that a full Home Assistant restart is required after every HACS update; the config-entry Reload action does not pick up new code or manifest changes.

### Fixed

- Polled alarms with epoch-millisecond `timestamp`/`datetime` fields (numeric or numeric-string) are now parsed correctly. Previously `datetime.fromisoformat(str(ts))` rejected numeric strings, silently falling back to "now" and corrupting `received_at` for every polled alert on controllers that emit ms timestamps. Prerequisite for the v2 system-log polling switch.
- 400-response bodies that fail JSON parsing during alarm-endpoint probing are now logged at DEBUG with the exception class. Previously a bare `except Exception: pass` masked malformed UniFi error bodies, hiding the `api.err.InvalidObject` fallback path.
- Per-category Clear buttons now report unavailable when their category is disabled in options. Previously they appeared clickable but no-oped on press. The all-clear button is also now unavailable when no categories are enabled. Both button classes now inherit `CoordinatorEntity` so they respond to coordinator updates consistently with the other platforms. (`button.py`)
- README and info.md entity-ID examples now match what HA generates from the integration's entity names; stale short-form IDs (e.g. `binary_sensor.unifi_alerts_network_device`) replaced with the correct slugified forms (e.g. `binary_sensor.unifi_alerts_network_device_offline_online`). Credential setup copy updated to remove references to "older controllers" and self-hosted Network Application installs now that UniFi OS is required.
- `alert_count` and `last_alert` now persist across config-entry reloads. Previously every options change discarded both counters; they are now saved alongside the existing watermark in the integration's `Store` and restored on startup.

## [1.5.0] - 2026-05-07

### Fixed

- Options-flow credential changes are now staged and persisted atomically only when the user submits the finish step. Previously, `async_step_credentials` called `async_update_entry` eagerly, so closing the dialog at the categories step left a new password (or rotated webhook secret) persisted against the user's intent. The `verify_ssl` toggle now also persists when flipped on its own; previously it was filtered out of the change-detection check and silently ignored.
- `make check` now passes on Windows. A new top-level `tests/conftest.py` applies two Windows-only workarounds: it forces `SelectorEventLoop` for `aiodns` (both via `set_event_loop_policy(WindowsSelectorEventLoopPolicy())` and by rebinding `WindowsProactorEventLoopPolicy._loop_factory` so HA's per-test `HassEventLoopPolicy` produces Selector loops via inheritance), and it neutralises `pytest_socket.disable_socket` so asyncio's `socket.socketpair()` self-pipe survives. HA core's earlier `socket_allow_hosts(["127.0.0.1"])` filter still applies, so external network egress remains blocked. No-op on Linux/macOS.
- Polling no longer re-asserts `is_alerting` for alarms older than the acknowledgement watermark. Previously the binary sensor flipped back to Problem with a stale message after a Clear, while Open Count stayed at 0.
- `_auto_clear` now persists the advanced watermark to storage. An HA restart immediately after a timer-triggered clear no longer resets `open_count` to the lifetime total.
- Webhook pushes now optimistically increment `open_count` so the count sensor moves with the binary sensor instead of lagging by up to one poll interval. Polling reconciles to the authoritative value on the next refresh.

### Changed

- Config flow now uses HA's `async_get_clientsession` for credential validation, honouring proxy, connection-pool, and per-session SSL settings. ([#68])
- `aiohttp` dropped from `manifest.json` requirements; HA core provides it. ([#68])
- `docs/HOMEASSISTANT.md` rewritten to mandate `async_get_clientsession` and forbid bare `aiohttp.ClientSession()`. ([#68])
- `__init__.py` exception messages and paired error logs surface only the exception class name, never `str(err)`. Prevents credential fragments from leaking into HA logs and the repair UI. ([#67])
- `UniFiClient.close()` logout failures now log at WARNING with the exception class name. Previously suppressed silently. ([#67])

### Added

- `SECURITY.md` documents the webhook-secret rotation threat model: rotation replaces the bearer token but reuses the URL path. ([#67])

## [1.4.0] - 2026-05-04

### Changed

- **Breaking:** UniFi OS consoles required; classic self-hosted Network Application is no longer supported. ([#59])
- **Breaking:** Config entry version bumped 1 to 2. The legacy `is_unifi_os` key is stripped automatically on first load. ([#59])
- Webhook payload DEBUG logging narrowed to `{category, alert_key, severity, device_name}`. ([#50])
- Inbound webhooks debounced per `(category, alert_key)` over a 5-second window. ([#50])
- `release.yml` workflow migrated from `softprops/action-gh-release` to `gh release create --generate-notes`; eliminates the only third-party action in the release pipeline. ([#51])

### Added

- Per-entry webhook ID suffix (`CONF_WEBHOOK_ID_SUFFIX`) prevents collision when two config entries are active. ([#50])
- Constant-time webhook token comparison via `hmac.compare_digest`. ([#50])
- Webhook secret rotation via the options-flow credentials step. ([#50])
- `?token=` redacted to `?token=***` in setup logs. ([#50])
- `WebhookManager.register_all()` rolls back on partial failure. ([#50])
- Webhook decode failures log at WARNING with class name and 80-byte body preview. ([#50])
- `CHANGELOG.md`, `SECURITY.md`, `CODEOWNERS`, GitHub bug-report and feature-request issue templates. ([#51])
- Dependabot config for the `github-actions` ecosystem. ([#51])
- `.github/release.yml` categories file for grouped auto-generated release notes. ([#51])

## [1.3.0] - 2026-04-29

### Fixed

- Options flow no longer loops; restructured to mirror initial setup (credentials, categories, finish). ([#36])
- Service / device card now appears in HA's Devices & Services immediately after setup. ([#36])
- Message sensor defaults to `"No alerts yet"` instead of blank. ([#36])
- `EntityCategory.DIAGNOSTIC` applied to message sensors; `EntityCategory.CONFIG` applied to clear buttons. ([#36])
- `EventDeviceClass.BUTTON` removed from event entities (semantically incorrect). ([#36])
- API-key auth no longer misdetects `_is_unifi_os = False` on UniFi OS controllers. ([#31])
- HTTP status codes surfaced in `CannotConnectError` messages. ([#31])

### Changed

- Alarm endpoint probe chain extended to `[/list/alarm, /alarm, /stat/alarm]` for UniFi Network 9.x+. ([#41])
- Invalid `limit=200` query parameter removed from `/alarm` calls. ([#32])

### Fixed (CI)

- Pre-release `grep` regex fixed: added `--` terminator so `vX.Y.Z-preN` tags stop being parsed as CLI flags and incorrectly published as stable. ([#34])
- `softprops/action-gh-release` bumped to v3 (Node 24, ahead of Node 20 EOL). ([#34])

## [1.2.0] - 2026-04-22

Internal critical-review pass. No user-visible changes; the audit findings were carried forward into 1.3.0 and 1.4.0.

## [1.1.0] - 2026-04-15

### Added

- Lovelace dashboard YAML example in README. ([#15])
- Automation example in README with verified `event_type` / `event_data` schema. ([#15])
- Services `unifi_alerts.clear_category` and `unifi_alerts.clear_all`. ([#17])
- Config-entry repair flow: HA repair notification on post-setup auth failure. ([#19])
- Options flow can update credentials and controller URL without re-adding the integration. ([#20])

### Changed

- Controller URL validated for `http(s)` scheme to prevent SSRF.
- Webhook body capped at 8 KB (`WEBHOOK_MAX_BODY_BYTES`). ([#13])
- Authentication exception messages log only the class name, not `str(err)`. ([#13])

### Fixed

- Polling re-auth no longer claims success when re-auth succeeds but the second poll fails. ([#14])

### Changed (CI)

- All GitHub Actions `uses:` references pinned to commit SHAs. ([#18])
- Two-branch model adopted: `main` for stable, `dev` for `X.Y.Z-preN`. `version-check.yml` enforces the format per branch. ([#12])

## [1.0.0] - 2026-04-10

### Added

- First stable release of the UniFi Alerts custom integration.
- Per-category binary sensors, message sensors, open-count sensors, event entities, and clear buttons.
- Rollup binary sensor, count sensor, and message sensor across enabled categories.
- Three-step config flow: credentials, categories, webhook URL display. Username/password and API-key auth.
- REST polling backstop on a configurable interval; webhook push path for real-time updates.
- Per-category bearer-token authentication on inbound webhooks.

### Changed

- SSL verification enabled by default (`DEFAULT_VERIFY_SSL = True`); UI toggle for self-signed certs.
- Webhooks marked `local_only=True`.
- Sensitive credential fields use `TextSelectorType.PASSWORD`.

### Fixed

- UCG-Ultra OS detection: two-stage fallback probe added.
- Config-flow API-key field guidance reworded to be firmware-version agnostic.

[Unreleased]: https://github.com/PHeonix25/unifi_alerts/compare/v1.7.0...HEAD
[1.7.0]: https://github.com/PHeonix25/unifi_alerts/releases/tag/v1.7.0
[1.6.0]: https://github.com/PHeonix25/unifi_alerts/releases/tag/v1.6.0
[1.5.0]: https://github.com/PHeonix25/unifi_alerts/releases/tag/v1.5.0
[1.4.0]: https://github.com/PHeonix25/unifi_alerts/releases/tag/v1.4.0
[1.3.0]: https://github.com/PHeonix25/unifi_alerts/releases/tag/v1.3.0
[1.2.0]: https://github.com/PHeonix25/unifi_alerts/releases/tag/v1.2.0
[1.1.0]: https://github.com/PHeonix25/unifi_alerts/releases/tag/v1.1.0
[1.0.0]: https://github.com/PHeonix25/unifi_alerts/releases/tag/v1.0.0

[#12]: https://github.com/PHeonix25/unifi_alerts/pull/12
[#13]: https://github.com/PHeonix25/unifi_alerts/pull/13
[#14]: https://github.com/PHeonix25/unifi_alerts/pull/14
[#15]: https://github.com/PHeonix25/unifi_alerts/pull/15
[#17]: https://github.com/PHeonix25/unifi_alerts/pull/17
[#18]: https://github.com/PHeonix25/unifi_alerts/pull/18
[#19]: https://github.com/PHeonix25/unifi_alerts/pull/19
[#20]: https://github.com/PHeonix25/unifi_alerts/pull/20
[#31]: https://github.com/PHeonix25/unifi_alerts/pull/31
[#32]: https://github.com/PHeonix25/unifi_alerts/pull/32
[#34]: https://github.com/PHeonix25/unifi_alerts/pull/34
[#36]: https://github.com/PHeonix25/unifi_alerts/pull/36
[#41]: https://github.com/PHeonix25/unifi_alerts/pull/41
[#50]: https://github.com/PHeonix25/unifi_alerts/pull/50
[#51]: https://github.com/PHeonix25/unifi_alerts/pull/51
[#59]: https://github.com/PHeonix25/unifi_alerts/pull/59
[#67]: https://github.com/PHeonix25/unifi_alerts/pull/67
[#68]: https://github.com/PHeonix25/unifi_alerts/pull/68
[#PR]: https://github.com/PHeonix25/unifi_alerts/pull/PR
