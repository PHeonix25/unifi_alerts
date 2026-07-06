# Changelog

## [Unreleased]

### Changed

- Category binary sensors now expose a `last_severity` attribute containing the severity string from the most recent alert (`"LOW"`, `"MEDIUM"`, `"HIGH"`, `"VERY_HIGH"` on v2 controllers; raw webhook severity on legacy controllers). The `any_alert` rollup sensor exposes the same attribute. Automations can condition on this to suppress or escalate alerts by severity without disabling the category. ([#135])
- Raised the declared minimum supported Home Assistant version from 2024.5 to 2025.1, matching the version the test suite actually runs against. CI now runs the full suite against both the declared minimum HA (pinned) and the latest HA. ([#284])

### Added

- Added the MIT license. The repository previously shipped without any license file, which left users and contributors without a legal grant to use or modify the code and would have blocked the HACS default catalogue submission. ([#290])
- The config-flow finish step now links to a new Alarm Manager onboarding guide covering setup, verification, and common failure modes. ([#297])
- UniFi OS consoles (UDM, UDM Pro, UDM SE, UDM Pro Max) are now discovered automatically via SSDP. When one is found on the local network it appears in Settings > Integrations > Discovered, with the controller URL pre-filled. Credentials still need to be entered manually. ([#172])
- Unclassified event keys seen during polling are now collected and exposed under `unrecognised_keys` in the integration diagnostics (Settings > Devices & Services > UniFi Alerts > Download diagnostics). This makes previously-invisible unmapped events visible without enabling DEBUG logging, so users can identify and report missing keys to the issue tracker. ([#134])
- A typo'd site name during setup now shows a dedicated error ("Site not found on the controller") on the categories step instead of creating a broken config entry stuck in "Not Ready". The default site (`default`) still proceeds without an extra network round-trip since reachability was already confirmed in the credentials step. The same validation runs in the options flow when changing to a non-default site. ([#171])
- Category labels in entity names (e.g. "Network: WAN offline/latency") are now defined in `translations/en.json` instead of being hard-coded English strings, so translators can provide locale-specific versions without rebuilding the integration. Each entity now carries a per-category translation key rather than a generic key with a hard-coded English placeholder. ([#133])
- Each category now has a diagnostic `sensor.*_webhook_health` entity (`never_received` / `healthy` / `stale`, with a `last_webhook_at` attribute), promoting the existing `webhook_health` signal from a buried binary-sensor attribute to a dashboardable, automatable entity with history. The attribute remains on the binary sensor for backward compatibility. ([#270])

### Fixed

- The v2 system-log fetch window is now clamped to `DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS` (24 hours). Previously, a rarely-cleared category could hold the oldest watermark to an arbitrarily old timestamp, causing every poll to paginate from that date forward and silently miss recent alarms once the 10-page cap was reached. The clamp ensures all categories are always within the paged window. A WARNING is now logged when the page cap is reached, indicating some events may have been missed. ([#136])
- A `ConfigEntryAuthFailed` raised during the initial data fetch (for example, credentials rotated between setup's `authenticate()` call and the first coordinator poll) is no longer misclassified as `ConfigEntryNotReady`. Previously a blanket exception handler around the first refresh re-wrapped every failure, including a genuine auth failure, as "not ready": silently suppressing Home Assistant's reauth-repair flow. ([#257])
- Two distinct webhook alerts with no `key` field arriving in the same category within the dedup window no longer suppress each other; only genuine duplicate keys are still deduplicated. ([#291])
- Removing a config entry now deletes its persisted watermark storage file and any open repair issues tied to it, instead of leaving them behind permanently. ([#294])
- Alert payloads with non-string `device_name` or `site` values no longer crash the webhook handler or the polling path; these fields are now always coerced to strings, matching how `message`/`key`/`severity` were already handled. ([#292])
- The config entry's `unique_id` now updates when the controller URL is changed via the options flow, so duplicate-entry prevention and SSDP discovery matching stay correct after re-pointing an entry to a different controller. ([#295])
- The options (reconfigure) flow's `cannot_connect`, `invalid_auth`, `invalid_ssl_cert`, `invalid_url_scheme`, and `at_least_one_category` errors, and the SSDP discovery flow's `cannot_connect` abort reason, now have translated text. Previously these were missing from `strings.json`'s `options.error` and `config.abort` sections, so a user hitting one of them while reconfiguring an entry or during a failed SSDP discovery would see the raw untranslated key instead of a readable message. ([#298])
- A setup failure that occurs after webhooks were registered (for example a platform-forwarding error) now unregisters those webhooks and closes the client before re-raising. Previously the failed webhooks stayed registered, so Home Assistant's automatic setup retry hit a duplicate-id error for every category, silently loaded with an empty webhook URL map, and left real-time alerts routed to the dead coordinator from the first attempt until HA was restarted. ([#265])

### Internal

- Added unicode round-trip tests for `UniFiAlert` serialisation: emoji, CJK, and RTL text survive `to_dict`/`from_dict` without mangling, and 300-character unicode messages are clamped to 255 characters. Added large-batch determinism tests: 500-alert `CategoryState` count is exact, watermark filtering passes precisely the expected subset, and all 500 messages survive serialisation round-trip. ([#140])
- Authentication concerns (`authenticate`, API-key verification, username/password login, request headers, and auth state) are extracted from `UniFiClient` into a dedicated `UniFiAuth` class in a new `unifi_auth.py` module, so auth can be unit-tested in isolation without the full client. `UniFiClient` composes a `UniFiAuth` instance and still owns the probe-backoff reset on every successful authentication. No behaviour change. ([#120])
- Replaced every blanket `except Exception` (`# noqa: BLE001`) handler across the integration with the specific exception types each call site can actually raise: `json.JSONDecodeError`/`UnicodeDecodeError` for 400-body parsing and `aiohttp.ClientError`/`OSError`/`TimeoutError` for the best-effort logout in `unifi_client.py`; `CannotConnectError` for the initial `authenticate()` call in `__init__.py`; the five `config_flow.py` "unknown error" fallbacks (setup, site validation, reauth, options credentials, options site validation) removed entirely, since the preceding specific catches already cover the full raise-surface of `authenticate()`/`fetch_alarms()`; `(InvalidAuthError, CannotConnectError)` for the system-log probe's internal re-auth in `coordinator.py`; and `ValueError` (the only failure mode of HA's `async_register`) for webhook registration in `webhook_handler.py`. A genuine bug now surfaces with its real traceback instead of being silently reduced to a generic error. ([#257])
- `UniFiAlertsOptionsFlow.async_step_credentials` in `config_flow.py` is now a thin orchestrator over standalone helpers: input parsing/normalisation, URL scheme validation, duplicate-entry detection, the staged-data dict builders, and the `UniFiClient` authenticate/fetch-alarms validation call are each extracted into their own function so they can be unit-tested in isolation instead of only through the full flow step. No behaviour change. ([#238])
- Strengthened five test assertions that could previously let a real bug ship with CI green: auto-clear delay arithmetic (`clear_timeout_minutes * 60`) had zero coverage; the probe-backoff deadline was only checked for presence, not duration; the auto-clear test never checked `last_cleared_at` or asserted a single notification; no test proved a webhook POST after entry unload is inert; and no test covered concurrent same-category webhook pushes or a manual clear racing a poll. Each new/strengthened assertion was verified against a deliberately introduced bug before being finalised. No behaviour change. ([#282])
- Reduced test-suite maintenance cost with no behaviour change: factored the repeated 5-patch `async_setup_entry` collaborator stack in `test_init.py` into a single `patch_setup_entry_collaborators()` helper; deduplicated three identical "coordinator with a cancellable task" helpers in `test_coordinator.py` into one shared helper; parametrised `TestRegisterAll`'s six near-identical bodies in `test_webhook_handler.py` into one; and split three oversized test modules (`test_coordinator.py`, `test_options.py`, `test_unifi_client.py`, each over 1300 lines) into behaviour-grouped files under 800 lines each. Test count and coverage unchanged. ([#283])

## [1.8.0] - 2026-06-19

### Added

- Per-category webhook health signal. Each category binary sensor now exposes a `webhook_health` attribute (`never_received`, `healthy`, or `stale`) and a `last_webhook_at` timestamp, so you can confirm the Alarm Manager wiring works without waiting for a real alert. `healthy` means a webhook arrived within the last 7 days; `stale` means the last one is older than that (expected for rarely-firing categories). Both fields also appear per category in the diagnostics download and survive a config-entry reload. ([#117])
- A failed watermark save now raises a repair issue in Settings > Repairs warning that cleared alerts may reappear after a restart and to check disk space. The issue clears itself on the next successful save. ([#163])
- Rotating the webhook secret in the options flow now creates a repair issue in Settings > Repairs reminding the user to update all category URLs in UniFi Alarm Manager. The issue clears automatically when the first authenticated webhook is received after the update. ([#167])
- SSL certificate verification failures in the config flow now show a dedicated, actionable error instead of the generic cannot-connect message. The `verify_ssl` field now carries an inline warning about man-in-the-middle risk. ([#166])

### Changed

- Event entities (`event.unifi_alerts_*`) no longer replay the most-recent persisted alert as a fresh `alert_received` event when the integration reloads (for example after an options-flow save). The per-entity counter is now seeded from the restored category state in `async_added_to_hass` instead of resetting to zero. ([#116])
- The last-message sensor now returns `None` (HA "unknown") instead of the hardcoded English string "No alerts yet" when no alert has been received, eliminating the only remaining hard-coded user-facing string in the platform files. ([#138])
- Entity display names for last-message, open-count, and event entities now use a colon separator instead of an em-dash (e.g. `{category}: Last Message`). ([#138])
- The category configuration warning now reads "Warning:" instead of the `⚠️` emoji glyph so meaning is preserved for screen readers and translators. ([#138])

### Fixed

- Upgrading from a pre-v1.4.0 install no longer silently breaks webhook delivery. The schema v2-to-v3 migration now surfaces a Repair issue in Settings > Repairs when webhook URLs change due to the `webhook_id_suffix` being backfilled, giving a clear call to action to re-paste the new URLs into Alarm Manager. The previous INFO log was downgraded to DEBUG. ([#241])
- Successful re-authentication now immediately clears the system-log probe backoff. Previously, if the probe had been forced onto the legacy path by consecutive transient failures (hit `_PROBE_FAIL_LIMIT`), re-auth would leave the backoff timer intact and the integration would stay on the legacy path for up to 1 hour even after the controller became reachable. The fix resets `_probe_backoff_until`, `_probe_fail_count`, and `_has_system_log` (to `None`, triggering a fresh probe on the next poll) inside `authenticate()` on every success path. ([#168])
- Authenticated webhook POSTs whose body is not valid JSON or not valid UTF-8 now return HTTP 400 and are discarded rather than synthesizing an "Unknown alert" entity state update. A token-bearing sender could previously spam meaningless "Unknown alert" events via malformed bodies. ([#173])
- `UniFiClearCategoryButton` and `UniFiClearAllButton` now override `_handle_coordinator_update()` to call `async_write_ha_state()`, so the `available` property is re-evaluated when coordinator state changes (e.g. after a category is disabled via the options flow without a full reload). Previously the button entities could remain stale between polls. ([#170])
- A second 401 response from the controller after a successful re-authentication now raises `ConfigEntryAuthFailed` (triggering HA's re-auth repair flow) instead of propagating as an unhandled `InvalidAuthError`. Previously the coordinator only caught `CannotConnectError` on the retried fetch, so a persistent authentication failure after credential rotation silently broke polling. ([#122])
- `make lint`, `make typecheck`, `make validate`, and the `.githooks/pre-push` hook no longer crash on Windows shells whose stdout codec defaults to `cp1252`. Previously, the `✅` success glyph printed by the scripts raised `UnicodeEncodeError` and exited the script non-zero even when the underlying tool (ruff, mypy, the validators) had succeeded. All five affected scripts (`run_lint.py`, `run_typecheck.py`, `validate_hacs.py`, `validate_docs.py`, `check_translations.py`) now reconfigure stdout and stderr to UTF-8 via a shared `scripts/_console.py` helper at startup. Windows contributors no longer need to export `PYTHONIOENCODING=utf-8` to use the standard development workflow. ([#148])
- The v2 system-log probe no longer re-fires on every poll when the endpoint returns persistent non-404 errors. After 5 consecutive transient failures the probe caches the legacy path for 1 hour, then retries. A single blip still causes a re-probe on the next poll. ([#137])
- Watermark/alert-count persistence triggered by a webhook push now coalesces a burst of pushes into a single debounced write via `Store.async_delay_save`, removing a lost-update race between overlapping fire-and-forget saves. Background-task failures (including a persist raised inside an auto-clear) are now logged via a shared done-callback instead of being silently swallowed. ([#118])
- Webhook body contract is now documented and tested: unparseable bodies (invalid JSON/UTF-8) return HTTP 400 and do not mutate state; valid empty bodies (`{}`) and bodies with no recognised fields are accepted and produce an "Unknown alert" event. ([#124])

### Security

- `UniFiAlert` no longer retains the raw controller payload in its `raw` field after construction. Previously `from_webhook_payload`, `from_api_alarm`, and `from_system_log_event` all stored the full unredacted payload (client MACs, IPs, hostnames) in `last_alert.raw` for the lifetime of the `CategoryState`. Now `raw` defaults to `{}` after construction. `from_dict` is unchanged for backward storage compatibility. ([#164])
- `_render_message_raw` now uses a single-pass `re.sub` instead of sequential `str.replace`. The old approach allowed a parameter value that contained a `{TOKEN}` string to be re-substituted on a later iteration, and was order-dependent for overlapping key names (e.g. `{IP}` vs `{IP_DST}`). Neither could be triggered from outside a valid authenticated session, but the fix closes the ambiguity for future callers. ([#123])
- `from_webhook_payload`, `from_api_alarm`, and `from_system_log_event` now truncate `key` to 64 characters, `device_name` to 255 characters, and `severity` to 32 characters. Previously only `message` was bounded, so a token-bearing caller could push unbounded strings into HA state and logs via the other fields. ([#128])
- All authenticated outbound calls to the UniFi controller now pass `allow_redirects=False`. Any 3xx response raises `CannotConnectError` rather than silently resubmitting credentials to the redirect target. ([#127])
- `UniFiAlert.to_dict()` no longer persists the `raw` UniFi payload to `.storage`. That payload carried unredacted client MACs, IP addresses, and hostnames, and could contain non-JSON-safe values that would crash `Store.async_save`. Persistence now emits an explicit scalar field list (`category`, `message`, `received_at`, `key`, `device_name`, `site`, `severity`); `from_dict()` still defaults `raw` to `{}` on read so existing stored entries continue to load. ([#147])

### Documentation

- README now explains multi-controller and multi-site setup: run one integration instance per controller URL or per UniFi site, and clarifies the site name field (default `"default"`, changed only when you renamed the site or monitor a non-default site). ([#139])

### Internal

- Added test coverage reporting via Codecov: `pytest-cov` added to dev requirements, 95% floor enforced in CI and locally (`--cov-fail-under=95`), XML report uploaded to Codecov on every push, live badge added to README and info.md. `make coverage` generates an HTML report locally; `.coverage`, `coverage.xml`, and `htmlcov/` added to `.gitignore`.
- Added end-to-end integration tests for webhook secret rotation: confirms the old token is rejected (401) after reload and the new token is accepted (200), covering the full rotation cycle from entry-data update through webhook re-registration. ([#121])
- `ci.yml` and `version-check.yml` now include a `concurrency` block so redundant runs for the same branch/PR are cancelled when a new commit is pushed. `release.yml` is intentionally excluded. ([#175])
- Unit test files now use a consistent class-based layout: tests are grouped into `Test*` classes by flow step or functional area (`TestUserStep`, `TestCategoriesStep`, `TestDiagnosticsRedaction`, etc.) matching the `python_classes = Test*` convention already set in `pytest.ini`. `test_setup.py`, `test_diagnostics.py`, and `test_reauth.py` were converted from flat functions; `docs/TESTING.md` now documents the convention. ([#233])
- Alert classification is now handled by a single `classify_event_key()` function in `const.py`, replacing two separate prefix-match loops that lived in `unifi_client.py` and `models.py`. The `_unknown_system_log_keys` module-global set is removed from `models.py`; deduplication of unknown-key warnings is now scoped to the coordinator instance via a `seen_keys` parameter, so tests no longer share global state between runs. ([#119])

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

[Unreleased]: https://github.com/PHeonix25/unifi_alerts/compare/v1.8.0...HEAD
[1.8.0]: https://github.com/PHeonix25/unifi_alerts/releases/tag/v1.8.0
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
[#116]: https://github.com/PHeonix25/unifi_alerts/issues/116
[#117]: https://github.com/PHeonix25/unifi_alerts/issues/117
[#118]: https://github.com/PHeonix25/unifi_alerts/issues/118
[#147]: https://github.com/PHeonix25/unifi_alerts/pull/147
[#148]: https://github.com/PHeonix25/unifi_alerts/issues/148
[#119]: https://github.com/PHeonix25/unifi_alerts/issues/119
[#120]: https://github.com/PHeonix25/unifi_alerts/issues/120
[#121]: https://github.com/PHeonix25/unifi_alerts/issues/121
[#122]: https://github.com/PHeonix25/unifi_alerts/issues/122
[#123]: https://github.com/PHeonix25/unifi_alerts/issues/123
[#127]: https://github.com/PHeonix25/unifi_alerts/issues/127
[#128]: https://github.com/PHeonix25/unifi_alerts/issues/128
[#133]: https://github.com/PHeonix25/unifi_alerts/issues/133
[#134]: https://github.com/PHeonix25/unifi_alerts/issues/134
[#135]: https://github.com/PHeonix25/unifi_alerts/issues/135
[#136]: https://github.com/PHeonix25/unifi_alerts/issues/136
[#138]: https://github.com/PHeonix25/unifi_alerts/issues/138
[#139]: https://github.com/PHeonix25/unifi_alerts/issues/139
[#140]: https://github.com/PHeonix25/unifi_alerts/issues/140
[#163]: https://github.com/PHeonix25/unifi_alerts/issues/163
[#164]: https://github.com/PHeonix25/unifi_alerts/issues/164
[#166]: https://github.com/PHeonix25/unifi_alerts/issues/166
[#167]: https://github.com/PHeonix25/unifi_alerts/issues/167
[#168]: https://github.com/PHeonix25/unifi_alerts/issues/168
[#170]: https://github.com/PHeonix25/unifi_alerts/issues/170
[#171]: https://github.com/PHeonix25/unifi_alerts/issues/171
[#172]: https://github.com/PHeonix25/unifi_alerts/issues/172
[#173]: https://github.com/PHeonix25/unifi_alerts/issues/173
[#175]: https://github.com/PHeonix25/unifi_alerts/issues/175
[#233]: https://github.com/PHeonix25/unifi_alerts/issues/233
[#238]: https://github.com/PHeonix25/unifi_alerts/issues/238
[#241]: https://github.com/PHeonix25/unifi_alerts/issues/241
[#257]: https://github.com/PHeonix25/unifi_alerts/pull/257
[#290]: https://github.com/PHeonix25/unifi_alerts/pull/290
[#291]: https://github.com/PHeonix25/unifi_alerts/pull/291
[#292]: https://github.com/PHeonix25/unifi_alerts/pull/292
[#294]: https://github.com/PHeonix25/unifi_alerts/pull/294
[#295]: https://github.com/PHeonix25/unifi_alerts/pull/295
[#297]: https://github.com/PHeonix25/unifi_alerts/pull/297
[#298]: https://github.com/PHeonix25/unifi_alerts/pull/298
[#284]: https://github.com/PHeonix25/unifi_alerts/issues/284
[#265]: https://github.com/PHeonix25/unifi_alerts/issues/265
[#270]: https://github.com/PHeonix25/unifi_alerts/issues/270
[#282]: https://github.com/PHeonix25/unifi_alerts/issues/282
[#283]: https://github.com/PHeonix25/unifi_alerts/issues/283
[#PR]: https://github.com/PHeonix25/unifi_alerts/pull/PR
