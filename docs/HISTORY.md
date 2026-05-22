# History

Dated record of completed work. Newest first. Format per entry: category, short description, PR or commit reference, short why.

## 2026-05-18

- **release**: v1.7.0-pre2 tagged. Ships ARCH-2 (the last v1.7 code item) plus the off-plan tooling and docs PRs that landed during the pre1 review window. Pre2 is the validation checkpoint for the maintainer's pre1 -> pre2 upgrade test plan on a real HA + UniFi controller; pass criteria are byte-identical entity_id, unique_id, and friendly_name snapshots across the two pre-releases.
- **feat**: migrate entity names to `_attr_translation_key` + `_attr_translation_placeholders` (ARCH-2) ([#107]). Display strings move from hard-coded `_attr_name = f"{CATEGORY_LABELS[cat]} ..."` formatting to `strings.json` and byte-identical `translations/en.json` under the HA-standard `entity.{platform}.{key}.name` schema; English-rendered names are preserved byte-for-byte, `_attr_unique_id` is untouched. Unlocks localisation without code changes.
- **docs**: backfill CHANGELOG entries for off-plan PRs and resolve the `[#PR]` placeholder on the SEC-1 bullet to `[#94]` ([#107]). The four off-plan PRs (#103-#106) merged without their own `[Unreleased]` bullets; backfilled now so the v1.7.0 stable promotion PR has a complete starting point.
- **ci**: move `make lint` and `make typecheck` from inline shell invocations to `scripts/run_lint.py` and `scripts/run_typecheck.py` ([#103]). Same logic now runs identically on Linux, macOS, and Windows without per-platform shims; replaces the `ifeq ($(OS),Windows_NT)` cross-platform branching previously needed in the Makefile.
- **docs**: rewrite `AGENTS.md` as a self-contained agent context file ([#104]). Adds repo structure map, six-step category-registration walkthrough, and common-pitfalls list so agents that cannot follow cross-file links (web-based tools, third-party AI) get the conventions inline. Also adds a maintenance matrix to `.github/copilot-instructions.md` covering the four common change cascades, a `.github/PULL_REQUEST_TEMPLATE.md`, a `copilot-setup-steps.yml` workflow for one-command Copilot session provisioning, and an "AI Ready" badge to README.
- **docs**: add six Copilot agent definitions under `.github/agents/` (SE Lead, QE Lead, Security Lead, Responsible AI, Product Manager, Technical Debt Remediation) ([#105]). Unified Identity / Mission / Core Principles / Workflow / Output Format / Anti-Patterns structure across all six, named personas for self-identification in reviews. Also widens `scripts/validate_docs.py` to scan every `*.md` recursively rather than a fixed glob list so new markdown anywhere in the tree inherits the prose rules automatically.
- **tests**: 232 lines of targeted branch-path unit tests across `test_options.py`, `test_reauth.py`, `test_coordinator.py`, and `test_models.py` ([#106]). Pure coverage uplift; no production-code changes.

## 2026-05-15

- **release**: v1.7.0-pre1 tagged. Ships the v1.7.0 documentation + architecture scope: fail-closed webhook auth with schema v3 migration that backfills missing secrets on legacy entries (SEC-1), `UniFiClientConfig` TypedDict that closed the largest `dict[str, Any]` surface and unblocked `mypy --strict` (ARCH-1), `strict = true` flipped with zero `# type: ignore` debt (CI-1), `tests/unit/config_flow/` package split (ARCH-3), `SensorStateClass.MEASUREMENT` confirmed on count sensors (ARCH-4), end-to-end documentation accuracy pass (DOC-A), new troubleshooting / privacy / tested-controllers / uninstall sections (DOC-B), WHY comments on dedup / watermark / system-log probe (QUAL-1), and a README + info.md restructure that dropped README from 331 to 186 lines.
- **security**: fail-closed webhook auth and schema v3 migration that backfills `webhook_secret` / `webhook_id_suffix` on legacy entries ([#94]). Webhook handler now returns HTTP 500 when no bearer secret is configured (previously accepting); migration generates a fresh secret and suffix only when missing or empty, leaving correctly-configured entries untouched.
- **docs**: reconcile documentation against current code (DOC-A) ([#95]). 35 verified drift points across REPO_LAYOUT test paths, HOMEASSISTANT button row, info.md HA baseline (2024.5 not 2026.1.0), DEVELOPING HISTORY guidance, TESTING conftest tree.
- **tests**: split `tests/unit/test_config_flow.py` (1565 lines) into `tests/unit/config_flow/` package (ARCH-3) ([#96]). Four files (`test_setup`, `test_options`, `test_reauth`, plus shared `conftest`); same test count, smaller rebase blast radius.
- **feat**: confirm `SensorStateClass.MEASUREMENT` on open-count and rollup-count sensors (ARCH-4) ([#97]). No `SensorDeviceClass` is set (none of HA's built-ins fit an alert counter); comment added so a future reader does not re-open the question.
- **docs**: v1.7 user docs (DOC-B) and WHY comments (QUAL-1) ([#98]). Troubleshooting / privacy / tested-controllers / uninstall sections in README; `info.md` local-network warning; setup-flow finish step copy stresses copying webhook URLs before Submit. Code-side WHY comments cover the webhook 5s dedup window, polling-vs-webhook `alert_count` invariant, acknowledgement watermark, and system-log probe.
- **docs**: restructure README and info.md, dedupe content, move examples to `docs/EXAMPLES.md` ([#99]). Standard flow (Features > Requirements > Installation > Setup > Entities > Privacy > Uninstall > Support > Contributing); merged the two duplicate "tested consoles" tables; README dropped from 331 to 186 lines with no content cut.
- **chore**: introduce `UniFiClientConfig` TypedDict for the client / coordinator / webhook config dict (ARCH-1) ([#100]). Replaces `dict[str, Any]` parameters and storage; `cast()` at the HA `ConfigEntry` boundary; `Final` annotations on the 13 `CONF_*` keys so mypy resolves them as literal types. Prerequisite for CI-1.
- **ci**: enable `mypy --strict` across the integration (CI-1) ([#101]). Fixed every issue with real type annotations and one import-path move (`DeviceInfo` from `helpers.device_registry` instead of the unmarked re-export on `helpers.entity`); zero `# type: ignore` lines added.

## 2026-05-11

- **release**: v1.6.0 tagged. Ships the v1.6.0 reliability scope: v2 `system-log/all` polling switch with capability probe and legacy fallback (closes the ~3000-record cap on `/list/alarm` that left `open_count` stuck at 0 on busy controllers), persistent `alert_count` and `last_alert` across config-entry reloads, button-availability gating that respects category-enabled state, and the epoch-ms timestamp parser fix the v2 path depends on. Live-validated against a UCG-Ultra running Network 10.3.58 via the v1.6.0-pre2 canary before promotion; no functional changes between pre2 and stable.
- **release**: v1.6.0-pre2 tagged. Ships the v1.6.0 reliability batch: v2 system-log polling with legacy fallback, persistent counters across reloads, button-availability gating, plus tests / ci / docs items that closed the rest of the v1.6.0 backlog. v1.6.0-pre1 was never tagged; this checkpoint is the first published pre-release of the v1.6.0 cycle.
- **feat**: v2 `system-log/all` polling switch with capability probe and legacy fallback ([#90]). `/list/alarm` caps at ~3000 records oldest-first, so recent alarms never appear in the polled response on busy controllers; the v2 endpoint supports `timestampFrom` + pagination. Probe caches definitive 200 / 404 responses; transient errors re-probe next poll so a single network blip cannot pin a capable controller to legacy mode. Adds `from_system_log_event` parser, `SYSTEM_LOG_KEY_TO_CATEGORY`, coarse `SYSTEM_LOG_CATEGORY_FALLBACK` for unmapped keys, and warn-once observability for unknown keys.
- **fix**: `alert_count` and `last_alert` persist across config-entry reloads ([#89]). Previously every options-flow change rebuilt `_category_states` and discarded both counters; they now save alongside the existing watermark in `Store` with backward-compat for legacy payloads.
- **fix**: Clear buttons inherit `CoordinatorEntity` and gate availability on category-enabled state ([#84]). Previously appeared clickable but no-oped when their category was disabled; per-category buttons now report unavailable via dynamic `available`, and the all-clear button is unavailable when no categories are enabled.
- **fix**: polled alarms with epoch-ms `timestamp` / `datetime` fields parse correctly ([#83]). Previously `datetime.fromisoformat(str(ts))` rejected numeric strings and fell back to "now", corrupting `received_at`. Also DEBUG-logs 400-response bodies that fail JSON parsing during alarm-endpoint probing. Prerequisite for the v2 system-log switch.
- **tests**: webhook-mid-poll interleaving regression test ([#88]). Asserts that a webhook arriving during an in-flight poll cannot regress `is_alerting` to False; documents an existing invariant for future refactors.
- **ci**: `make lint` now covers `tests/` in addition to `custom_components/` ([#87]). Seven test files reformatted by `ruff format` autofix; no test-logic changes.
- **docs**: README "Updating the integration" section between Installation and Setup ([#86]). Live-tested against v1.5.0-pre3: HACS file copy plus config-entry Reload is not enough; a full HA restart is required because Reload runs against the cached in-memory module.
- **docs**: README and info.md entity-ID examples refreshed to match the slugified IDs HA actually generates ([#85]). Credential-setup copy purged of "older controllers" and self-hosted Network Application references now that UniFi OS is required.
- **docs**: retire the `main > dev` sync-merge step from the release workflow ([#81]). With merge-commit-only on `main`, `dev`'s tip is already the second parent of the release commit; the merge base advances correctly without a sync PR.
- **chore**: start v1.6.0-pre1 development cycle ([#82]). Manifest bumped to `1.6.0-pre1`; no tag pushed.

## 2026-05-07

- **release**: v1.5.0 tagged. Ships the v1.5.0 security-hardening II + field-confirmed reliability scope: HA-managed clientsession for credential validation, sanitised auth-failure log lines and exception messages, three coordinator reliability bugs (watermark-aware `is_alerting`, persistent `_auto_clear` watermark, optimistic `open_count` increment on the webhook path), and the options-flow atomicity refactor that stages credential / `verify_ssl` / secret-rotation changes and persists them only when the user submits the finish step.
- **fix**: options flow now stages credential changes and persists them atomically in the finish step; abandoning the dialog after the credentials step no longer leaves a new password (or rotated webhook secret) committed against the user's intent. The `verify_ssl` toggle is included in change detection so flipping the checkbox alone is no longer a silent no-op ([#76]). Closes the v1.5.0 options-flow atomicity defects.
- **chore**: align HISTORY cadence with release tags; entries are now written once per tag (pre-release or stable) by the version-bump PR rather than on every PR ([#73]). Removes the duplication between HISTORY (per-PR) and CHANGELOG `[Unreleased]` (per-PR) and eliminates the standalone backfill PRs that interrupted sessions left behind.
- **chore**: doc-only fast path; new `make doc-check` target runs `validate_docs.py` and translation drift only (no venv required), and CLAUDE.md gains a "Doc-only PRs" subsection that skips `make setup`, plan-mode, and Explore agents for prose-only edits ([#73]). CI still runs the full suite as the safety net.
- **chore**: pre-push hook now delegates to `make check`; previously re-implemented every step inline, which drifted from the Makefile (e.g. `make doc-check` was missing) ([#73]).
- **docs**: per-file repo annotations extracted from CLAUDE.md to new `docs/REPO_LAYOUT.md`; CLAUDE.md keeps a one-line pointer ([#73]). Smaller always-loaded context per session, same detail when needed.
- **build**: `make help` is the new default goal; `make setup-lint` installs only ruff and mypy via `requirements-lint.txt` for lint-only or typecheck-only PRs ([#73]). Avoids the ~200-package full install (Home Assistant + test deps) when only the linters are needed.
- **ci**: new `pr-labeler.yml` workflow auto-applies release-notes labels from Conventional Commit title prefixes (`feat`, `fix`, `docs`, `test(s)`, `ci`, `security`); manual labels always win ([#73]). Closes the gap that produced flat v1.4.0-pre2 release notes when `mcp__github__create_pull_request` (which does not accept labels) was used without a follow-up `issue_write`.
- **build**: new `scripts/bump_version.py` automates the release-prep workflow (`--pre`, `--stable`, `--next-cycle`); checks out a fresh `dev`, creates `claude/bump-<new-version>`, updates `manifest.json`, rewrites `CHANGELOG.md` on stable promotions, and prints the merge list since the previous tag ([#73]). Pure stdlib; CLAUDE.md release-workflow steps now point at the script.
- **build**: Makefile and tooling are now cross-platform; `ifeq ($(OS),Windows_NT)` selects `.venv/Scripts` vs `.venv/bin`, `py -3.12` vs `python3.12`, and `.exe` suffixes; new `scripts/check_translations.py` replaces the `diff > /dev/null` shell incantation in `make doc-check` and CI; `.githooks/pre-push` accepts either Unix or Windows venv layout ([#73]).
- **fix**: tests now run on Windows; HA core's test conftest calls `disable_socket(allow_unix_socket=True)`, which on Windows breaks `ProactorEventLoop.__init__` (uses `socket.socketpair()` for the self-pipe) and `aiodns` (requires `SelectorEventLoop`). New `tests/conftest.py` neutralises `pytest_socket.disable_socket` on Windows and rebinds `asyncio.WindowsProactorEventLoopPolicy._loop_factory` to `SelectorEventLoop` so HA's per-test policy inherits the Selector factory ([#74]). No-op on Linux/macOS.

## 2026-05-06

- **fix**: three coordinator reliability bugs ([#72]). Polling now applies the watermark filter to the `is_alerting` branch (was only filtering `open_count`), so a stale pre-Clear alarm cannot re-flip the binary sensor to Problem after auto-clear. `_auto_clear` now persists the advanced watermark, so an HA restart immediately after a timer-triggered clear no longer resets `open_count` to the lifetime total. `push_alert` increments `open_count` optimistically so the count sensor moves with the binary sensor instead of lagging by up to one poll interval; polling reconciles on the next refresh. +7 regression tests in `test_coordinator.py`.
- **docs**: backfill HISTORY entries for #69 and #70; add HISTORY audit step to "Resuming an interrupted session" in CLAUDE.md; tighten HISTORY rule to require self-entry in every PR ([#71]). Closes the gap where sessions ending mid-closeout left merged PRs unrecorded.
- **docs**: rewrite TODO/ROADMAP/CHANGELOG/HISTORY; refresh ARCHITECTURE, HOMEASSISTANT, UNIFI, TESTING, DEVELOPING to match current dev state; add `scripts/validate_docs.py` prose linter wired into `make validate`, pre-push hook, and CI ([#69]). Single source of truth for docs conventions; linter prevents em-dash and banned-framing regressions.
- **docs**: record v2 system-log API findings and 3000-record cap on `/list/alarm` ([#70]). Confirms why `open_count` reads 0 on busy controllers and locks in the v2 polling strategy as the v1.6.0 fix.

## 2026-05-04

- **security**: config flow uses HA's `async_get_clientsession` for credential validation; `aiohttp` dropped from manifest requirements ([#68]). Honours HA proxy / connection-pool / per-session SSL settings on credential-test requests.
- **security**: sanitise three `ConfigEntryAuthFailed` / `ConfigEntryNotReady` messages and paired `_LOGGER.error` calls in `__init__.py`; `UniFiClient.close()` logout failures log at WARNING with class name ([#67]). Prevents credential fragments from leaking into HA logs and the repair UI.
- **docs**: SECURITY.md gains a "Webhook secret rotation" section explaining that rotation replaces the bearer token but reuses the URL path ([#67]). Documents the partial-revocation contract.
- **docs**: `docs/HOMEASSISTANT.md` rewritten to mandate `async_get_clientsession` for all session creation; bare `aiohttp.ClientSession()` is explicitly the wrong pattern ([#68]).
- **docs**: v1.4.0 closeout - HISTORY entry, ROADMAP checkboxes, status line ([#66]).
- **release**: v1.4.0 tagged. Diagnosed and fixed the squash-merge trap where v1.3.0's squash commit was never made an ancestor of dev, causing v1.4.0's release PR to conflict on every file. Added `claude/sync-main-to-dev-1.4.0` PR with proper merge-commit parents. Documented the trap and the mandatory main->dev sync step in CLAUDE.md and `docs/DEVELOPING.md`. Branch rulesets configured: dev allows squash only, main allows merge-commit only.

## 2026-05-01

- **security**: SSL fail-open across 4 `unifi_client.py` call sites; all `self._config.get(CONF_VERIFY_SSL, ...)` fallbacks now use `DEFAULT_VERIFY_SSL` (True) so a missing key fails closed ([#58]). New `TestSslFailOpen` covers the absent-key case.
- **fix**: `_get_coordinators` in `services.py` now filters by `ConfigEntryState.LOADED`; `async_entries(DOMAIN)` could previously return entries in `SETUP_RETRY` / `SETUP_ERROR` whose `runtime_data` was unset, raising `AttributeError` ([#58]). New `TestGetCoordinatorsGuard` covers both branches.
- **feat**: drop legacy self-hosted code paths from `unifi_client.py`; remove `_detect_unifi_os()`, `_network_path()`, `_is_unifi_os` attribute, and detection-based branching in `authenticate()`, `close()`, `_login_userpass()`. All paths hardcode `/proxy/network` and `/api/auth/login` / `/api/auth/logout`. Net removal: ~60 lines ([#59]). Eliminates a persistent source of bugs.
- **chore**: `async_migrate_entry` strips `is_unifi_os` from existing entries; `ConfigFlow.VERSION` bumped 1 to 2 ([#59]). Existing installs migrate without user action.
- **docs**: README and info.md add "⚠ Requires UniFi OS" prerequisite section listing tested console models; classic self-hosted explicitly unsupported ([#59]).
- **feat**: migrate to `entry.runtime_data` (HA 2024.2+); add `RuntimeData` dataclass to `models.py`; `async_setup_entry` populates `entry.runtime_data` instead of `hass.data[DOMAIN][entry_id]` ([#57]). Cleaner API; HACS minimum HA version set in `hacs.json`.

## 2026-04-30

- **feat**: diagnostics expose per-category state including `last_cleared_at`, `is_alerting`, `open_count`, `alert_count`, `enabled` ([#55]). Users debugging unexpected `open_count` values can now see the per-category acknowledgement watermark.
- **docs**: codebase audit refreshed TODO and ROADMAP for v1.4.0+; new entries: `_auto_clear` does not persist watermarks, button entities missing `CoordinatorEntity` mixin, `async_migrate_entry` for `is_unifi_os` removal. Three intermediate releases (v1.5.0 / v1.6.0 / v1.7.0) added between v1.4.0 and v2.0.0 ([#52]).
- **chore**: TODO audit against current dev codebase; dropped already-shipped items, added newly surfaced gaps ([#56]).
- **chore**: label-setup script added; tightens PR-label doctrine. Required so `--generate-notes` categorises PRs correctly ([#54]).

## 2026-04-29

- **release**: v1.3.0 tagged. Five pre-release checkpoints on dev. Ships post-install bug fixes, API-key + UniFi OS path coercion, alarm endpoint probe-chain extension, and the pre-release `grep` terminator fix ([#46]).
- **security**: webhook security hardening - per-entry `CONF_WEBHOOK_ID_SUFFIX` (8-char hex) prevents multi-entry collisions; `hmac.compare_digest` for token comparison; `?token=` redacted to `?token=***` in setup logs; webhook payload DEBUG log narrowed to `{category, alert_key, severity, device_name}`; per-(category, alert_key) 5s rate-limit; webhook secret rotation via options flow; `register_all()` rolls back on partial failure; webhook decode failures log at WARNING with class name and 80-byte body preview ([#50]). 26 new tests; `tests/integration/test_multi_entry.py` is the red-green pair.
- **chore**: repo hygiene + release pipeline - `CHANGELOG.md` (Keep-a-Changelog, back-filled v1.0.0 to v1.3.0), `SECURITY.md`, `CODEOWNERS`, GitHub bug-report and feature-request issue templates, `.github/dependabot.yml` (github-actions ecosystem, weekly), `.github/release.yml` categories, `release.yml` workflow migrated from `softprops/action-gh-release` to `gh release create --generate-notes` ([#51]). Eliminates the only third-party action in the release pipeline.
- **feat**: per-category acknowledgement watermark for `open_count` ([#44]). Pressing Clear advances `last_cleared_at`; polling counts only alarms newer than the watermark; watermarks persisted via `Store` and survive HA restarts. Without this, `open_count` is a lifetime counter that only grows.
- **fix**: alarm endpoint probe chain extended to `[/list/alarm, /alarm, /stat/alarm]`, newest first, for UniFi Network 9.x+ ([#41]). 9.x changed the alarm endpoint path; modern firmware succeeds in one call, older firmware falls back.
- **fix**: three v1.3.0 post-install bugs - options flow no longer loops between pages 1 and 2 (restructured to mirror initial setup: credentials, categories, finish); proactive device registration via `dr.async_get_or_create` so Services card appears immediately; message sensor defaults to `"No alerts yet"`; `EntityCategory.DIAGNOSTIC` on message sensors; `EntityCategory.CONFIG` on clear buttons; `EventDeviceClass.BUTTON` removed from event entities ([#36]).

## 2026-04-22

- **release**: v1.2.0 tagged. Internal critical-review pass; the audit findings were carried forward into 1.3.0 / 1.4.0.
- **ci**: pre-release `grep` regex fix - `--` terminator added to `grep -qE -- '-pre[0-9]+$'` so `vX.Y.Z-preN` tags stop being parsed as CLI flags. Every pre-release tag was being published as stable. `softprops/action-gh-release` bumped v2 to v3 (Node 24, ahead of Node 20 EOL) ([#34]).
- **fix**: invalid `limit=200` query parameter removed from `/alarm` calls; try-both path fallback (`/alarm`, then `/stat/alarm`); HTTP 400 handler reads `meta.msg` (e.g. `api.err.InvalidObject`) and surfaces it in `CannotConnectError` ([#32]). Controllers with >200 open alarms no longer silently drop results.
- **fix**: API-key auth coerces `_is_unifi_os = True` on successful verification; HTTP status codes surfaced in `CannotConnectError` messages ([#31]). Prevents `_detect_unifi_os()` false negatives from breaking subsequent calls (UCG-Ultra, reverse-proxy setups).

## 2026-04-21

- **docs**: extended v1.2 critical-review audit added 13 new ROADMAP items including the multi-entry webhook ID collision (CRITICAL), bare `aiohttp.ClientSession` in config flow, credential fragments in exception messages, no rate limiting, epoch-ms timestamp drop, `open_count` stale on webhook ([#21]).
- **fix**: distinguish re-auth failure from post-re-auth update failure in polling. Split the single retry handler into two `try/except` blocks; re-auth failures raise `ConfigEntryAuthFailed` (triggers HA reauth UI), post-reauth poll failures raise `UpdateFailed` with a distinct message ([#14]).
- **docs**: README Lovelace card and automation example added; replaces the minimal one-liner stub with a working entities card and a `platform: state` automation against an `EventEntity` ([#15]).
- **docs**: `info.md` HACS display page added (56 lines) ([#16]).
- **ci**: all GitHub Actions `uses:` references pinned to commit SHAs with trailing version comments ([#18]). Eliminates supply-chain risk from floating refs.
- **feat**: `unifi_alerts.clear_category` and `unifi_alerts.clear_all` services with voluptuous schemas and per-entry filtering ([#17]).
- **feat**: config-entry repair flow - `async_step_reauth` / `async_step_reauth_confirm` and an `issue_registry` repair card on auth failure ([#19]). Users can rotate credentials in-place.
- **feat**: options flow can update credentials and controller URL without re-adding the integration; blank fields preserve existing values ([#20]).

## 2026-04-15

- **security**: credentials leak via exception messages closed - `fetch_alarms()` and `_login_userpass()` now raise `CannotConnectError(type(err).__name__)` only ([#13]). Some `aiohttp.ClientError` subclasses embed credential-bearing URLs in `__str__`.
- **security**: `WEBHOOK_MAX_BODY_BYTES = 8192` cap on inbound webhook bodies; oversized POSTs return HTTP 413 ([#13]). Prevents unbounded memory growth from malformed payloads.
- **ci**: two-branch model adopted - `main` for stable, `dev` for `X.Y.Z-preN`. New `version-check.yml` enforces the format per branch; `release.yml` switched from `release: published` trigger to `push: tags`, validates tag matches `manifest.json`, auto-detects pre-release ([#12]).

## 2026-04-11

- **release**: v1.1.0 tagged. Security hardening (SSRF scheme validation, body cap, credentials-leak fix), reliability (split re-auth retry handler), services (`clear_category` / `clear_all`), reauth + repair flow, options-flow credentials, README examples, `info.md`, SHA-pinned CI ([#22]).
- **fix**: silent `api.err.InvalidObject` from polling - `fetch_alarms()` now validates `meta.rc` and raises `CannotConnectError` on non-`"ok"`; `CONF_IS_UNIFI_OS` persisted to `entry.data` so re-detection cannot flip the path between sessions; alarm endpoint validated at config-flow time ([#11]). Two bugs combined to make `meta.rc != "ok"` errors silent and unrecoverable.

## 2026-04-10

- **feat**: full integration test suite using `pytest_homeassistant_custom_component` `hass` fixture; tests/unit and tests/integration peer dirs; `entry` / `mock_unifi_client` / `_prime_pycares_shutdown_thread` fixtures ([#9]). 16 new tests cover entity creation, options flow, auto-clear, webhook dispatch end-to-end.
- **fix**: auto-clear race fixed in integration tests - `_schedule_clear` switched to `hass.async_create_background_task`; tests await `hass.async_block_till_done(wait_background_tasks=True)` followed by a second drain ([#9]).
- **docs**: API-key instructions are now firmware-version agnostic (lists both common navigation paths). Multi-site support via `CONF_SITE` / `DEFAULT_SITE` ([#8]). 9 new tests including options-flow boundary values.
- **fix**: four bugs in one PR - aiohttp session ownership (raw `aiohttp.ClientSession` in config flow, not HA-managed); URL scheme validation prevents SSRF; `_verify_api_key` hardcodes `/proxy/network` regardless of detection; `_detect_unifi_os` adds `/api/system` fallback probe for UCG-Ultra; `params={"limit": 200}` cap on `/alarm` ([#7]).
- **fix**: three more v1pre2 fixes - mask password / API key fields with `TextSelectorType.PASSWORD`; error-recovery schema omits defaults for sensitive fields; coordinator polling skips disabled categories; webhook handler `except Exception` narrowed to `JSONDecodeError` / `TypeError` ([0d951b3]).
- **fix**: four v1pre1 install-testing blockers - UCG-Ultra dual-path fallback in `_login_userpass`; demote webhook URL logging from INFO to DEBUG; config-flow session always closed in `try/finally`; at-least-one-category validation in initial setup and options flow ([0f17afb]).
- **chore**: release prep for 1.0.0-pre3; ROADMAP/TODO tidy-up ([#10]).

## 2026-04-09

- **docs**: full documentation pass aligning CLAUDE.md, README.md, TESTING.md, HOMEASSISTANT.md, ARCHITECTURE.md with the new tooling (Makefile, requirements-dev.txt, pre-push hook, HACS pre-flight) ([204e34e]).
- **chore**: local dev tooling - `Makefile` (default `make check`); `requirements-dev.txt` (single source of truth, used by both CI jobs); pre-push hook adds mypy and translation drift; `strings.json` ↔ `translations/en.json` drift caught by CI's `lint` job ([#4]).
- **ci**: `scripts/validate_hacs.py` HACS manifest pre-flight + `hacs-preflight` CI job + pre-push hook entry ([#4]). Catches `dependencies` mistakes locally before CI.
- **fix**: revert `"webhook"` manifest dependency that broke HACS CI; non-negotiable constraint added to CLAUDE.md - never list HA core built-ins in `dependencies` ([#3]).
- **tests**: 103 new tests across 5 files (`test_webhook_handler.py`, `test_init.py`, plus extensions to `test_unifi_client.py`, `test_coordinator.py`, `test_entities.py`) covering webhook auth, setup/unload lifecycle, polling error paths, rollup properties, all entity property methods ([7ae5e19]).

## 2026-04-08

- **release**: v1-pre1 tagged. Initial workflow run failed with `Resource not accessible by integration`; fixed by adding `permissions: contents: write` to `release.yml` ([38c4366]).
- **ci**: GitHub Actions upgraded to Node.js 24 - `actions/checkout` v4 to v6, `actions/setup-python` v5 to v6, `softprops/action-gh-release` v2 to v2.6.1 ([7ab9657]). Silences "Node.js 20 deprecated" warnings.
- **fix**: four post-v1 must-fix bugs - config-flow user step preserves submitted values on validation error; `_detect_unifi_os` follows redirects (`allow_redirects=True`) and drops the `or status == 200` heuristic; `_login_userpass` distinguishes 400 (`CannotConnectError`) from 401/403 (`InvalidAuthError`); webhook URLs displayed as copyable form fields instead of `description_placeholders`; SSL warning copy corrected after the default flip ([ae4e30b]).

## 2026-04-07

- **fix**: all v1.0.0 blocking bugs resolved - UTC-aware datetimes everywhere; options flow reads `entry.options` first; `cancel_clear` cancels pending auto-clear; polling sets `is_alerting`/`last_alert` directly (no more event misfires every poll); manual clear cancels auto-clear; `ConfigEntryNotReady` on auth and first-refresh failure ([#1]). `pytest.ini` `filterwarnings` suppress third-party deprecation noise.

## 2026-04-02

- **security**: per-entry webhook bearer token authentication - `CONF_WEBHOOK_SECRET` generated via `secrets.token_urlsafe(32)` at first auth; webhook URLs include `?token=`; `webhook_handler` rejects missing/wrong token with HTTP 401; `GET` removed from `allowed_methods` (was firing spurious alerts on health checks); `?token=` stripped from diagnostics URLs ([bff5060]).
- **security**: `DEFAULT_VERIFY_SSL` flipped from `False` to `True`; setup-time WARNING log when verification is disabled ([ae04888]).
- **docs**: V1 UX/documentation pass - `network_device` and `network_client` default OFF (alert fatigue); `strings.json` rewritten with API key vs userpass guidance, SSL warning, finish-step copy fix; README setup steps reordered with webhook URL retrieval as numbered step 5 ([d2363a2]).
- **fix**: V1 quick wins - `str(payload)` fallback to `"Unknown alert"`; `__import__("logging")` to standard import; `CONF_USERNAME` redacted in diagnostics; raw `"verify_ssl"` string replaced with `CONF_VERIFY_SSL` constant; contradictory `filename` field removed from `hacs.json` ([7c19b61]).
- **docs**: ROADMAP.md added; TODO expanded with multi-reviewer pre-V1 findings (8 blocking + 4 UX gaps) ([80becb9]).
- **ci**: hassfest manifest key order (`domain`, `name`, then alphabetical); HACS validation passes after repo description, topics, and 256x256 brand icon added ([dfdd13d]).

## 2026-04-01

- **fix**: graceful shutdown - `async_shutdown()` cancels pending `_clear_tasks` on entry unload; called from `async_unload_entry` ([f236b82]). Stops `CancelledError` noise on HA stop.
- **feat**: webhook URL display in config flow - `async_step_finish` shows pre-generated URLs as `description_placeholders` for the user to copy into UniFi Alarm Manager; options flow `init` step also lists current URLs ([6b3cb9c]).
- **feat**: `UNIFI_KEY_TO_CATEGORY` map expanded from 26 to 62 entries (DM, XG, roam, rogue AP/DHCP, PoE overload, client blocked); DEBUG logging of unclassified keys; GitHub issue template `unclassified_event_key.yml` for community reporting ([7d3c4a0]).

## 2026-03-31

- **feat**: 256x256 brand icon added; required by HACS and HA's integrations UI ([4df1807]).
- **fix**: silence coroutine-never-awaited warning in coordinator tests; `MagicMock()` for `hass.async_create_task` replaced with helper that calls `coro.close()` ([5622d7c]).
- **fix**: silence `asyncio_default_fixture_loop_scope` deprecation by setting `asyncio_default_fixture_loop_scope = function` in `pytest.ini`.
- **fix**: config-flow duplicate-entry guard via `async_set_unique_id` + `_abort_if_unique_id_configured`; full ruff + mypy clean pass.
- **docs**: `DEVELOPING.md` added covering local setup, venv, tests, lint, type check, branching.
- **feat**: diagnostics platform exposes per-category webhook URLs; passwords / API keys redacted via `_TO_REDACT`. Closes the "users hunting through logs" UX gap.
- **chore**: project conventions established - HISTORY log appended after every task; tests required for new functionality; memories/history/TODOs local to the repo.

[#1]: https://github.com/PHeonix25/unifi_alerts/pull/1
[#3]: https://github.com/PHeonix25/unifi_alerts/pull/3
[#4]: https://github.com/PHeonix25/unifi_alerts/pull/4
[#7]: https://github.com/PHeonix25/unifi_alerts/pull/7
[#8]: https://github.com/PHeonix25/unifi_alerts/pull/8
[#9]: https://github.com/PHeonix25/unifi_alerts/pull/9
[#10]: https://github.com/PHeonix25/unifi_alerts/pull/10
[#11]: https://github.com/PHeonix25/unifi_alerts/pull/11
[#12]: https://github.com/PHeonix25/unifi_alerts/pull/12
[#13]: https://github.com/PHeonix25/unifi_alerts/pull/13
[#14]: https://github.com/PHeonix25/unifi_alerts/pull/14
[#15]: https://github.com/PHeonix25/unifi_alerts/pull/15
[#16]: https://github.com/PHeonix25/unifi_alerts/pull/16
[#17]: https://github.com/PHeonix25/unifi_alerts/pull/17
[#18]: https://github.com/PHeonix25/unifi_alerts/pull/18
[#19]: https://github.com/PHeonix25/unifi_alerts/pull/19
[#20]: https://github.com/PHeonix25/unifi_alerts/pull/20
[#21]: https://github.com/PHeonix25/unifi_alerts/pull/21
[#22]: https://github.com/PHeonix25/unifi_alerts/pull/22
[#31]: https://github.com/PHeonix25/unifi_alerts/pull/31
[#32]: https://github.com/PHeonix25/unifi_alerts/pull/32
[#34]: https://github.com/PHeonix25/unifi_alerts/pull/34
[#36]: https://github.com/PHeonix25/unifi_alerts/pull/36
[#41]: https://github.com/PHeonix25/unifi_alerts/pull/41
[#44]: https://github.com/PHeonix25/unifi_alerts/pull/44
[#46]: https://github.com/PHeonix25/unifi_alerts/pull/46
[#50]: https://github.com/PHeonix25/unifi_alerts/pull/50
[#51]: https://github.com/PHeonix25/unifi_alerts/pull/51
[#52]: https://github.com/PHeonix25/unifi_alerts/pull/52
[#54]: https://github.com/PHeonix25/unifi_alerts/pull/54
[#55]: https://github.com/PHeonix25/unifi_alerts/pull/55
[#56]: https://github.com/PHeonix25/unifi_alerts/pull/56
[#57]: https://github.com/PHeonix25/unifi_alerts/pull/57
[#58]: https://github.com/PHeonix25/unifi_alerts/pull/58
[#59]: https://github.com/PHeonix25/unifi_alerts/pull/59
[#66]: https://github.com/PHeonix25/unifi_alerts/pull/66
[#67]: https://github.com/PHeonix25/unifi_alerts/pull/67
[#68]: https://github.com/PHeonix25/unifi_alerts/pull/68
[#69]: https://github.com/PHeonix25/unifi_alerts/pull/69
[#71]: https://github.com/PHeonix25/unifi_alerts/pull/71
[#70]: https://github.com/PHeonix25/unifi_alerts/pull/70
[#72]: https://github.com/PHeonix25/unifi_alerts/pull/72
[#73]: https://github.com/PHeonix25/unifi_alerts/pull/73
[#74]: https://github.com/PHeonix25/unifi_alerts/pull/74
[#76]: https://github.com/PHeonix25/unifi_alerts/pull/76
[#81]: https://github.com/PHeonix25/unifi_alerts/pull/81
[#82]: https://github.com/PHeonix25/unifi_alerts/pull/82
[#83]: https://github.com/PHeonix25/unifi_alerts/pull/83
[#84]: https://github.com/PHeonix25/unifi_alerts/pull/84
[#85]: https://github.com/PHeonix25/unifi_alerts/pull/85
[#86]: https://github.com/PHeonix25/unifi_alerts/pull/86
[#87]: https://github.com/PHeonix25/unifi_alerts/pull/87
[#88]: https://github.com/PHeonix25/unifi_alerts/pull/88
[#89]: https://github.com/PHeonix25/unifi_alerts/pull/89
[#90]: https://github.com/PHeonix25/unifi_alerts/pull/90
[#94]: https://github.com/PHeonix25/unifi_alerts/pull/94
[#95]: https://github.com/PHeonix25/unifi_alerts/pull/95
[#96]: https://github.com/PHeonix25/unifi_alerts/pull/96
[#97]: https://github.com/PHeonix25/unifi_alerts/pull/97
[#98]: https://github.com/PHeonix25/unifi_alerts/pull/98
[#99]: https://github.com/PHeonix25/unifi_alerts/pull/99
[#100]: https://github.com/PHeonix25/unifi_alerts/pull/100
[#101]: https://github.com/PHeonix25/unifi_alerts/pull/101
[#103]: https://github.com/PHeonix25/unifi_alerts/pull/103
[#104]: https://github.com/PHeonix25/unifi_alerts/pull/104
[#105]: https://github.com/PHeonix25/unifi_alerts/pull/105
[#106]: https://github.com/PHeonix25/unifi_alerts/pull/106
[#107]: https://github.com/PHeonix25/unifi_alerts/pull/107

[0d951b3]: https://github.com/PHeonix25/unifi_alerts/commit/0d951b3
[0f17afb]: https://github.com/PHeonix25/unifi_alerts/commit/0f17afb
[204e34e]: https://github.com/PHeonix25/unifi_alerts/commit/204e34e
[38c4366]: https://github.com/PHeonix25/unifi_alerts/commit/38c4366
[4df1807]: https://github.com/PHeonix25/unifi_alerts/commit/4df1807
[5622d7c]: https://github.com/PHeonix25/unifi_alerts/commit/5622d7c
[6b3cb9c]: https://github.com/PHeonix25/unifi_alerts/commit/6b3cb9c
[7ab9657]: https://github.com/PHeonix25/unifi_alerts/commit/7ab9657
[7ae5e19]: https://github.com/PHeonix25/unifi_alerts/commit/7ae5e19
[7c19b61]: https://github.com/PHeonix25/unifi_alerts/commit/7c19b61
[7d3c4a0]: https://github.com/PHeonix25/unifi_alerts/commit/7d3c4a0
[80becb9]: https://github.com/PHeonix25/unifi_alerts/commit/80becb9
[ae04888]: https://github.com/PHeonix25/unifi_alerts/commit/ae04888
[ae4e30b]: https://github.com/PHeonix25/unifi_alerts/commit/ae4e30b
[bff5060]: https://github.com/PHeonix25/unifi_alerts/commit/bff5060
[d2363a2]: https://github.com/PHeonix25/unifi_alerts/commit/d2363a2
[dfdd13d]: https://github.com/PHeonix25/unifi_alerts/commit/dfdd13d
[f236b82]: https://github.com/PHeonix25/unifi_alerts/commit/f236b82
