# History

Dated record of completed work. Newest first. Format per entry: category, short description, PR or commit reference, short why.

## 2026-08-21

- **release**: v2.1.0-pre1 tagged. First checkpoint of the v2.1.0 "severity follow-through and test coverage" cycle: closes most of the #331 review follow-ups (config/options flow accessibility fixes, `severity.py` cleanup, a latent `from_dict` truncation bug), the deferred `_device_info()` duplication (issue #383), a regression test locking down webhook secret-leak safety (issue #379), and the remaining v2.1.0 test-coverage gaps for entity actions, webhook edge cases, and coordinator/service error handling. The "Test Webhook" button (issue #384) was descoped: its literal spec (a live button embedded in the options flow finish step) doesn't fit how HA config flows work, and the auto-clear timing needs more design thought. Issues #355, #356, #357, #385 remain open for the next checkpoint.
- **feat**: restructured the config/options flow finish-step description into headed sections (Authentication, Legacy Method, Retrieve Later) and replaced per-category webhook URL form fields, which looked editable but silently discarded any edits, with plain-text placeholders; added help text for all 7 `min_severity_*` selectors on the categories step ([#405]). Closes #395, #354.
- **security**: added a regression test asserting webhook error-log output never leaks the legacy `?token=` query string, across the malformed-body and auth-failure paths ([#407]). Closes #379.
- **fix**: `UniFiAlert.from_dict()` now truncates `severity` to 32 characters, matching `from_webhook_payload()`/`from_api_alarm()`/`from_system_log_event()`; extracted the four duplicated `_device_info()` helpers into `entity_helpers.device_info_for_entry()` and centralised `UNIFI_OS_NETWORK_PREFIX` into `const.py` ([#409]). Closes #359, #383.
- **chore**: cleaned up `severity.py`: removed the unused legacy-severity synonym table, added `Literal` type aliases for severity/minimum-severity strings, inlined `filter_by_min_severity()` to remove the `severity.py`/`models.py` import cycle, and trimmed over-dense comments ([#408]). Closes #351, #352, #358, #360.
- **tests**: closed the remaining v2.1.0 test-coverage gaps: entity action coverage for `alert_received` events and button presses ([#401]), webhook body-size and malformed-JSON rejection ([#400]), and a webhook landing in the window between coordinator shutdown and webhook unregistration ([#402]). Closes #380, #381, #382.
- **docs**: added v2.1.0/v2.2.0/v2.3.0 sections to `docs/ROADMAP.md` ([#398]); resolved a documentation conflict that described the `_device_info()` duplication as an intentional trade-off instead of scheduled work ([#399]); consolidated the day's `CHANGELOG.md` `[Unreleased]` entries ([#403]).
- **ci**: hardened Python 3.14 provisioning to use `uv` when the CI base image doesn't already have it available ([#404]).

[#398]: https://github.com/PHeonix25/unifi_alerts/pull/398
[#399]: https://github.com/PHeonix25/unifi_alerts/pull/399
[#400]: https://github.com/PHeonix25/unifi_alerts/pull/400
[#401]: https://github.com/PHeonix25/unifi_alerts/pull/401
[#402]: https://github.com/PHeonix25/unifi_alerts/pull/402
[#403]: https://github.com/PHeonix25/unifi_alerts/pull/403
[#404]: https://github.com/PHeonix25/unifi_alerts/pull/404
[#405]: https://github.com/PHeonix25/unifi_alerts/pull/405
[#407]: https://github.com/PHeonix25/unifi_alerts/pull/407
[#408]: https://github.com/PHeonix25/unifi_alerts/pull/408
[#409]: https://github.com/PHeonix25/unifi_alerts/pull/409

## 2026-07-24

- **release**: v2.0.1 stable. Critical hotfix promoted straight to `main` as a patch release, shipping the single fix below.
- **fix**: the per-category minimum-severity selector on the categories step now renders as a translated dropdown instead of an untranslated radio-button list; it was missing an explicit dropdown render mode, a regression introduced with the `translation_key` selector added for v2.0.0 ([#376]). Closes #375.
- **release**: v2.0.0 stable. Promotes the "HACS default catalogue" cycle to `main`. No further changes landed on `dev` since `v2.0.0-pre2`, so this is a straight version promotion; every pre1/pre2 item ships as-is. The cycle's umbrella issue (#143) closed the same day: repository topics set, the brand icon self-hosted under `custom_components/unifi_alerts/brand/` (replacing the retired `home-assistant/brands` submission path), and a PR opened against `hacs/default`.

[#376]: https://github.com/PHeonix25/unifi_alerts/pull/376

## 2026-07-23

- **release**: v2.0.0-pre2 tagged. Second v2.0.0 checkpoint: per-category severity filtering for noisy categories lands, the HA quality-scale gaps found in the pre1 audit are closed (reconfigure flow, translated exceptions, service-call validation, SSDP host updates, localised selector labels), and the final config step now spells out the `Authorization` header for the new webhook auth. Everything bar the HACS default-catalogue submission (#143) is on `dev`.
- **feat**: added per-category minimum-severity filtering for noisy categories; each alert's severity is normalised onto a fixed scale and sub-threshold alerts are gated on both the poll and webhook paths, with unknown severities failing open so nothing is silently muted ([#331]). Closes #135. The selector's option labels moved onto a `translation_key` so they are localisable instead of hardcoded English ([#366]). Closes #353. The final "Webhook URLs" step now surfaces the `Authorization` header key and value as their own copy-paste block above the URLs, in both the config and options flows ([#370]). Closes #368.
- **feat**: added a dedicated reconfigure flow (`async_step_reconfigure`) that reuses the existing credential-validation helpers ([#364]). Closes #344. User-facing setup and update failures now carry translation keys so their text is localisable ([#363]). Closes #341.
- **fix**: SSDP rediscovery with a changed controller IP now updates the existing entry's `controller_url` and `unique_id` instead of aborting silently ([#365]). Closes #343. `clear_category`/`clear_all` now raise a `ServiceValidationError` on an unknown or unloaded `entry_id` rather than doing nothing ([#362]). Closes #340.
- **docs**: recorded the `entity-disabled-by-default` quality-scale rule as exempt, on the grounds that every entity is user-scoped and essential ([#367]). Closes #345. Added a "Use cases" section ([#361], closes #346) and an intrusion-detection example ([#369]) to the README, and backfilled the `docs/HISTORY.md` block for the v2.0.0-pre1 tag ([#350]).

[#331]: https://github.com/PHeonix25/unifi_alerts/pull/331
[#350]: https://github.com/PHeonix25/unifi_alerts/pull/350
[#361]: https://github.com/PHeonix25/unifi_alerts/pull/361
[#362]: https://github.com/PHeonix25/unifi_alerts/pull/362
[#363]: https://github.com/PHeonix25/unifi_alerts/pull/363
[#364]: https://github.com/PHeonix25/unifi_alerts/pull/364
[#365]: https://github.com/PHeonix25/unifi_alerts/pull/365
[#366]: https://github.com/PHeonix25/unifi_alerts/pull/366
[#367]: https://github.com/PHeonix25/unifi_alerts/pull/367
[#369]: https://github.com/PHeonix25/unifi_alerts/pull/369
[#370]: https://github.com/PHeonix25/unifi_alerts/pull/370

## 2026-07-21

- **release**: v2.0.0-pre1 tagged. First checkpoint of the v2.0.0 "HACS default catalogue" cycle. Headline: username/password authentication removed in favour of API-key-only auth with a reauth migration path (#328, #330), webhook authentication gains an `Authorization: Bearer` header alongside the deprecated `?token=` query parameter (#335), two architecture refactors (endpoint discovery decoupled from the alarm fetch loop, `UniFiClient` made fully stateless), fixes for unselected-category entity creation and clock-drift in the clear-watermark anchor, a quality-scale audit ahead of HACS submission, and a broad CI/tooling hardening pass (Python 3.14 baseline, Dev Container, agentrc eval harness, PR quality-score check).
- **feat**: username and password authentication removed; an API key is now the only supported credential. Config entries migrate to a version-4 schema: entries that already have a stored API key migrate silently, entries set up with only a username and password are walked through a reauth repair that asks for an API key in place, preserving existing sensors, history, and Alarm Manager webhook URLs ([#328], [#330]). Closes #278, #279.
- **feat**: audited the HA integration quality scale ahead of HACS default-catalogue submission ([#348]).
- **security**: inbound webhook authentication now accepts an `Authorization: Bearer <secret>` header in addition to the legacy `?token=` query parameter; the header is preferred since query strings routinely leak into proxy/access logs and browser history. `?token=` remains accepted through a deprecation window (no earlier than v3.0.0), with a `webhook_legacy_query_auth` repair issue nudging affected entries to migrate; the config/options "Webhook URLs" screens no longer embed the secret in the displayed URL ([#335]).
- **refactor**: `fetch_alarms()` now discovers and caches the working alarm endpoint once per site instead of walking the fallback chain and parsing an HTTP 400 body on every poll; discovery only re-runs if the cached URL stops resolving ([#329]). Closes #239. `UniFiClient` is now fully stateless: the v2 system-log-probe cache and backoff moved onto `UniFiAlertsCoordinator`, which already owns all other cross-poll state ([#336]). Closes #240.
- **fix**: unselected alert categories no longer create entities that sit at Unknown; entities are created only for chosen categories, and orphaned entities from deselected categories are removed on reload ([#308]). Clearing a category now anchors the acknowledgement watermark to the newest known alarm timestamp for that category instead of the HA host clock, keeping `open_count` correct when the controller and HA clocks drift ([#318]). Closes #268. The Dev Container added this cycle was broken on first use; fixed ([#324]).
- **docs**: added a Dev Container since native-Windows pytest is unsupported ([#323]); added `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` ([#315]); documented API-key-only auth setup and the upgrade path ([#333]). Closes #280. Applied the non-discoverable filter across agent-facing context files ([#332]).
- **ci**: raised the tooling and CI baseline to Python 3.14 and the declared minimum HA version to 2026.3.1, the first HA release requiring it ([#311]). Closes #228. Split ruff into its own fast job and routed mypy through `run_typecheck.py` ([#314]). Merged `pr-labeler` and `label-guard` to fix a tagging race ([#334]). Bumped the `github-actions` Dependabot group ([#327]).
- **chore**: added a three-phase agentic PR-quality eval harness: local single-model harness, cross-model comparison, and an advisory PR quality-score CI check ([#313], [#316], [#317], [#320], [#325]). Removed redundant button state overrides, added `PARALLEL_UPDATES`, and moved static icon definitions into `icons.json` ([#338]).
- **tests**: migrated `unifi_client` HTTP tests from `aioresponses` to Home Assistant's `aioclient_mock`, matching the fixture the rest of the suite already uses ([#321]).

[#308]: https://github.com/PHeonix25/unifi_alerts/pull/308
[#311]: https://github.com/PHeonix25/unifi_alerts/pull/311
[#313]: https://github.com/PHeonix25/unifi_alerts/pull/313
[#314]: https://github.com/PHeonix25/unifi_alerts/pull/314
[#315]: https://github.com/PHeonix25/unifi_alerts/pull/315
[#316]: https://github.com/PHeonix25/unifi_alerts/pull/316
[#317]: https://github.com/PHeonix25/unifi_alerts/pull/317
[#318]: https://github.com/PHeonix25/unifi_alerts/pull/318
[#320]: https://github.com/PHeonix25/unifi_alerts/pull/320
[#321]: https://github.com/PHeonix25/unifi_alerts/pull/321
[#323]: https://github.com/PHeonix25/unifi_alerts/pull/323
[#324]: https://github.com/PHeonix25/unifi_alerts/pull/324
[#325]: https://github.com/PHeonix25/unifi_alerts/pull/325
[#327]: https://github.com/PHeonix25/unifi_alerts/pull/327
[#328]: https://github.com/PHeonix25/unifi_alerts/pull/328
[#329]: https://github.com/PHeonix25/unifi_alerts/pull/329
[#330]: https://github.com/PHeonix25/unifi_alerts/pull/330
[#332]: https://github.com/PHeonix25/unifi_alerts/pull/332
[#333]: https://github.com/PHeonix25/unifi_alerts/pull/333
[#334]: https://github.com/PHeonix25/unifi_alerts/pull/334
[#335]: https://github.com/PHeonix25/unifi_alerts/pull/335
[#336]: https://github.com/PHeonix25/unifi_alerts/pull/336
[#338]: https://github.com/PHeonix25/unifi_alerts/pull/338
[#348]: https://github.com/PHeonix25/unifi_alerts/pull/348

## 2026-07-06

- **release**: v1.9.0 tagged. Closes out the v1.9.0 "Localisation and Scale" cycle: a webhook health sensor and setup-failure cleanup, a documented `webhook` runtime dependency, a full CI and tooling hardening pass, and a repo-wide documentation drift audit, on top of everything already shipped in pre1 through pre3.
- **ci**: bumped `actions/setup-python` from 6.2.0 to 6.3.0 via the grouped Dependabot github-actions update ([#300]).
- **ci**: single-sourced agent instructions into `AGENTS.md` and slimmed `CLAUDE.md`, added a `SessionStart` bootstrap hook so remote agent sessions install the venv automatically, aligned the declared minimum supported Home Assistant version (2025.1.0) with what CI actually tests via a new pinned-minimum test matrix leg, and expanded the ruff rule set (`ASYNC`, `RUF`, `PT`, `S`, complexity budgets) with justified suppressions ([#301]). Combines #281, #284, #286, #288.
- **feat**: unregister webhooks and close the client when setup fails after registration, so the automatic retry no longer finds every deterministic webhook ID already taken and silently loads with an empty URL map; documented the runtime dependency on the `webhook` component in the README, since `manifest.json` cannot declare it as a HACS dependency; promoted `webhook_health`/`last_webhook_at` from a buried binary-sensor attribute to a first-class per-category diagnostic sensor entity ([#302]). Closes #265, #267, #270.
- **tests**: closed five defect-detection gaps where assertions were too weak to catch a real bug even with green CI: auto-clear delay arithmetic, probe backoff duration, auto-clear strength, post-unload webhook dispatch, and same-category push concurrency; each new assertion was verified against a deliberately introduced bug before being finalised ([#303]). Closes #282.
- **tests**: factored the repeated 5-patch `async_setup_entry` collaborator stack into a shared `conftest.py` helper, deduplicated three identical coordinator test helpers into one, split three oversized test modules (each over 1300 lines) into behaviour-grouped files under 800 lines, and parametrised `TestRegisterAll`'s six near-identical bodies; no behaviour or coverage change ([#304]).
- **docs**: audited every doc for drift against current code: fixed `ARCHITECTURE.md`, `REPO_LAYOUT.md`, `HOMEASSISTANT.md`, `TESTING.md`, `DEVELOPING.md`, and `info.md`; refreshed `ROADMAP.md`'s status line; repointed stale references to the split test tree in `UNIFI.md`, `AGENTS.md`, `REPO_LAYOUT.md`, `TESTING.md`, and `.github/copilot-instructions.md` ([#305]). Closes #269.

[#300]: https://github.com/PHeonix25/unifi_alerts/pull/300
[#301]: https://github.com/PHeonix25/unifi_alerts/pull/301
[#302]: https://github.com/PHeonix25/unifi_alerts/pull/302
[#303]: https://github.com/PHeonix25/unifi_alerts/pull/303
[#304]: https://github.com/PHeonix25/unifi_alerts/pull/304
[#305]: https://github.com/PHeonix25/unifi_alerts/pull/305

## 2026-07-05

- **release**: v1.9.0-pre3 tagged. Third checkpoint of the v1.9.0 cycle. Headline: five bug fixes closing out real defects found during triage (webhook dedup, non-string payload coercion, entry-removal cleanup, stale `unique_id` on controller URL change), CI now lints and type-checks the `tests/` tree, and all three remaining `v2.0-gate` documentation items land, closing out every `v2.0-gate` issue.
- **chore**: repo hygiene quick wins from an agentic-delivery review: added the MIT `LICENSE` file (previously missing entirely, which would have blocked the HACS default catalogue submission), moved the pytest coverage gate off `addopts` onto `make test`/CI so single-file test runs no longer trip it, split cross-platform vs personal Claude Code settings, and fixed drifted references in `AGENTS.md`/`agentrc.eval.json` ([#290]).
- **fix**: `push_alert()` no longer deduplicates two distinct keyless webhook alerts against each other; only genuine duplicate keys within the dedup window are still suppressed ([#291]). Closes #263.
- **fix**: `UniFiAlert`'s three constructors now coerce `device_name`/`site` to `str` before use, matching the existing `message`/`key`/`severity` handling; a non-string value in either field previously raised `TypeError` and dropped the alert entirely ([#292]). Closes #266.
- **ci**: CI's `lint` job now runs `ruff check`/`ruff format --check` against `tests/` as well as `custom_components/`, matching what `make lint` already enforced locally ([#293]). Closes #232.
- **fix**: `async_remove_entry` now deletes the per-entry watermark storage file and all four repair issues when a config entry is removed, instead of leaving them behind permanently; the four issue-id strings were also promoted to shared `const.py` constants to prevent drift ([#294]). Closes #264.
- **fix**: the config entry's `unique_id` now updates when the controller URL changes via the options flow, so duplicate-entry prevention and SSDP discovery matching stay correct after re-pointing an entry to a different controller ([#295]). Closes #276.
- **docs**: added `docs/DATA_HANDLING.md`, the authoritative statement of what the integration persists, what stays memory-only, what appears in diagnostics downloads, and what is logged at DEBUG; linked from README and SECURITY.md ([#296]). Closes #273.
- **docs**: added `docs/ALARM_MANAGER_SETUP.md`, a step-by-step guide for wiring UniFi Alarm Manager to the integration's webhook URLs, covering verification via `webhook_health` and the four most common failure modes ([#297]). Closes #274.
- **docs**: closed out the v2.0 localisation-maturity gate: audited every translation-key surface (two gaps found and fixed, everything else clean), recorded the English-only decision for v2.0, documented the language-contribution path in `docs/LOCALISATION.md`, and removed the orphaned `config.error.unknown` translation key ([#298]). Closes #275.

[#290]: https://github.com/PHeonix25/unifi_alerts/pull/290
[#291]: https://github.com/PHeonix25/unifi_alerts/pull/291
[#292]: https://github.com/PHeonix25/unifi_alerts/pull/292
[#293]: https://github.com/PHeonix25/unifi_alerts/pull/293
[#294]: https://github.com/PHeonix25/unifi_alerts/pull/294
[#295]: https://github.com/PHeonix25/unifi_alerts/pull/295
[#296]: https://github.com/PHeonix25/unifi_alerts/pull/296
[#297]: https://github.com/PHeonix25/unifi_alerts/pull/297
[#298]: https://github.com/PHeonix25/unifi_alerts/pull/298

## 2026-07-03

- **release**: v1.9.0-pre2 tagged. Second checkpoint of the v1.9.0 "Localisation and Scale" cycle. Headline: site validation against the controller (#205), unrecognised event keys surfaced in diagnostics (#207), severity exposed on binary sensors (#210), SSDP discovery for UniFi OS consoles (#212), plus a `UniFiAuth` extraction (#218), narrowed exception handling with a `ConfigEntryAuthFailed` reauth-repair fix (#257), and test-infrastructure hardening (#258, #260) alongside an options-flow refactor (#259). Closes the five PRs carried forward from pre1.
- **feat**: non-default site names are now validated against the controller in both the config and options flow; a failed lookup shows an `invalid_site` field error instead of creating a broken entry; the default site skips the extra round-trip ([#205]). Closes #171.
- **feat**: unclassified event keys seen during polling now accumulate and appear under `coordinator.unrecognised_keys` in the HA diagnostics download, sorted by occurrence count, from both the v2 system-log and legacy alarm paths ([#207]). Closes #134.
- **feat**: `last_severity` is now exposed as an attribute on `UniFiCategoryBinarySensor` and `UniFiRollupBinarySensor`, not just the message sensor, so automations can condition on severity directly from the entity that triggers them ([#210]). Closes #135.
- **feat**: SSDP discovery for UDM, UDM Pro, UDM SE, and UDM Pro Max consoles; `async_step_ssdp` pre-fills the controller URL and forwards to the credentials step ([#212]). Closes #172.
- **refactor**: extract `UniFiAuth` from `UniFiClient` into its own module (`unifi_auth.py`) with no passthrough properties; production call sites import auth exceptions from `.unifi_auth` directly ([#218]). Closes #120.
- **fix**: `coordinator.async_config_entry_first_refresh()` no longer wraps HA core's call in a blanket `except Exception`, which was silently misclassifying `ConfigEntryAuthFailed` as `ConfigEntryNotReady` and suppressing HA's reauth-repair flow; every other blind `except Exception` (BLE001) across the integration narrowed to the specific exceptions each call site can raise ([#257]). Closes #237.
- **tests**: `test_unifi_client.py` now drives a real `aiohttp.ClientSession` through `aioresponses` instead of hand-built `MagicMock` response doubles, so tests assert on actual outbound HTTP rather than a fabricated aiohttp surface ([#258]). Closes #229.
- **refactor**: `UniFiAlertsOptionsFlow.async_step_credentials` split from a ~135-line method into a thin orchestrator over standalone helpers (form parsing, duplicate-entry detection, staged-dict builders, credential validation); no behaviour change ([#259]). Closes #238.
- **tests**: collapsed near-duplicate test-body clusters in `test_coordinator.py` and `test_entities.py` into `@pytest.mark.parametrize` cases with readable `ids`; test-item counts unchanged (90 and 84 respectively) ([#260]). Closes #231.

[#205]: https://github.com/PHeonix25/unifi_alerts/pull/205
[#207]: https://github.com/PHeonix25/unifi_alerts/pull/207
[#210]: https://github.com/PHeonix25/unifi_alerts/pull/210
[#212]: https://github.com/PHeonix25/unifi_alerts/pull/212
[#218]: https://github.com/PHeonix25/unifi_alerts/pull/218
[#257]: https://github.com/PHeonix25/unifi_alerts/pull/257
[#258]: https://github.com/PHeonix25/unifi_alerts/pull/258
[#259]: https://github.com/PHeonix25/unifi_alerts/pull/259
[#260]: https://github.com/PHeonix25/unifi_alerts/pull/260

## 2026-06-27

- **release**: v1.9.0-pre1 tagged. First checkpoint of the v1.9.0 "Localisation and Scale" cycle. Headline: translatable per-category entity labels (#133) and the v2 system-log fetch-window clamp (#136), plus large-volume serialisation tests and CI/process hardening. Five further v1.9.0 PRs (#207, #210, #205, #212, #218) remain open and will land in a later checkpoint.
- **feat**: entity display names now resolve through per-category `translation_key`s in `strings.json` / `translations/en.json` instead of a hard-coded English label map; the unused `CATEGORY_LABELS` dict was removed ([#208]). Closes #133.
- **fix**: clamp the v2 system-log fetch window to `DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS` (24h) and warn when the page cap is hit, so a rarely-cleared category can no longer anchor every poll to an arbitrarily old timestamp and silently drop recent alarms ([#204]). Closes #136.
- **tests**: add unicode round-trip and large-batch determinism coverage for `UniFiAlert` serialisation (emoji, CJK, and RTL survive `to_dict` / `from_dict`; 500-alert batches stay exact) ([#202]). Closes #140.
- **ci**: bump `actions/checkout` 6.0.2 to 7.0.0 ([#248]); move pytest config into `pyproject.toml` ([#249]); add an advanced CodeQL workflow so config-only PRs are not blocked ([#251]); bump `codecov/codecov-action` 5.4.3 to 7.0.0 ([#247]); run `pr-labeler` on `pull_request_target` so fork PRs get labelled ([#250]); allow HISTORY.md edits on the dev-to-main release merge in `history-guard` ([#245]).

[#202]: https://github.com/PHeonix25/unifi_alerts/pull/202
[#204]: https://github.com/PHeonix25/unifi_alerts/pull/204
[#208]: https://github.com/PHeonix25/unifi_alerts/pull/208
[#245]: https://github.com/PHeonix25/unifi_alerts/pull/245
[#247]: https://github.com/PHeonix25/unifi_alerts/pull/247
[#248]: https://github.com/PHeonix25/unifi_alerts/pull/248
[#249]: https://github.com/PHeonix25/unifi_alerts/pull/249
[#250]: https://github.com/PHeonix25/unifi_alerts/pull/250
[#251]: https://github.com/PHeonix25/unifi_alerts/pull/251

## 2026-06-19

- **release**: v1.8.0 stable. Promotes the "Trust and Hardening" cycle to main. All pre1-pre3 items shipped; one additional fix (#242) landed after pre3.
- **fix**: schema v2-to-v3 migration now raises a HA Repair issue when `webhook_id_suffix` is backfilled, surfacing the URL change to users instead of silently breaking webhook delivery; migrated `_LOGGER.info` to `_LOGGER.debug` ([#242]). Closes #241.

[#242]: https://github.com/PHeonix25/unifi_alerts/pull/242

## 2026-06-15

- **release**: v1.8.0-pre3 tagged. Final checkpoint of the v1.8.0 "Trust and Hardening" cycle. Closes the last remaining structural item (#119): alert classification is now a single `classify_event_key()` entry point in `const.py` used by both polling and webhook paths. UniFiAuth extraction (#120) deferred to v1.9.0. v1.8.0 is feature-complete and ready for stable promotion.
- **refactor**: consolidate alert classification into a single `classify_event_key()` function in `const.py`; remove the `_unknown_system_log_keys` module-global from `models.py` and scope warn-dedup to the coordinator instance via a `seen_keys` parameter, so warnings dedup per coordinator instance rather than per process (fixes test isolation) ([#217]). Closes #119.
- **tests**: reorganise three flat unit test files into `Test*` classes grouped by flow step or functional area (`TestUserStep`, `TestCategoriesStep`, `TestDiagnosticsRedaction`, etc.); document the convention in `docs/TESTING.md` ([#235]). Closes #233.
- **chore**: add `scripts/seed_issues.py` to bulk-seed GitHub Issues from the backlog; run idempotently to populate v1.8.0 and v1.9.0 milestones ([#234]).

## 2026-06-15

- **release**: v1.8.0-pre2 tagged. Second checkpoint of the v1.8.0 "Trust and Hardening" cycle. Headline: security hardening of the alert construction and authentication paths (redirect-blocking, raw-payload drop from in-memory state, bounded field lengths, single-pass template substitution), operational reliability fixes (probe-backoff reset after re-auth, button availability propagation, unparseable webhook rejection, post-reauth retry error handling), two user-visible features (SSL cert failure surfaces a dedicated config-flow error; webhook secret rotation creates a HA repair issue), and CI/docs infrastructure (pr-guards workflow, concurrency groups, pinned dev dependencies, pip Dependabot, per-category Alarm Manager trigger table). The two remaining v1.8.0 structural items (classify-consolidation #119 and UniFiAuth extraction #120) carry forward to pre3.
- **feat**: rotating the webhook secret in the options flow now creates a HA repair issue until the first authenticated webhook is received after the update ([#200]). Closes #167.
- **feat**: SSL certificate verification failures in the config flow now surface a dedicated, actionable error; `verify_ssl` field carries an inline MITM-risk warning ([#199]). Closes #166.
- **security**: stop retaining the raw controller payload in `UniFiAlert` after construction; `from_webhook_payload`, `from_api_alarm`, and `from_system_log_event` no longer store the full unredacted payload (client MACs, IPs, hostnames) in `last_alert.raw` for the lifetime of `CategoryState` ([#192]). Closes #164.
- **security**: `_render_message_raw` now uses a single-pass `re.sub` instead of sequential `str.replace`; the old approach allowed a parameter value containing `{TOKEN}` to be re-substituted on a later iteration and was order-dependent for overlapping key names ([#191]). Closes #123.
- **security**: `from_webhook_payload`, `from_api_alarm`, and `from_system_log_event` now truncate `key` to 64 chars, `device_name` to 255, and `severity` to 32; previously only `message` was bounded ([#189]). Closes #128.
- **security**: all authenticated outbound calls now pass `allow_redirects=False`; any 3xx response raises `CannotConnectError` rather than silently resubmitting credentials to the redirect target ([#188]). Closes #127.
- **fix**: re-authentication now resets `_probe_backoff_until`, `_probe_fail_count`, and `_has_system_log` so the integration re-probes the system-log endpoint immediately instead of staying on the legacy path for up to 1 hour after the controller becomes reachable ([#190]). Closes #168.
- **fix**: authenticated webhook POSTs with unparseable or non-UTF-8 bodies now return HTTP 400 and are discarded rather than synthesising an "Unknown alert" event; empty or field-less bodies are accepted and produce an "Unknown alert" ([#187]). Closes #173.
- **fix**: `UniFiClearCategoryButton` and `UniFiClearAllButton` now override `_handle_coordinator_update()` to call `async_write_ha_state()`, so the `available` property is re-evaluated when coordinator state changes ([#186]). Closes #170.
- **fix**: a second 401 after successful re-authentication now raises `ConfigEntryAuthFailed` instead of propagating as an unhandled `InvalidAuthError` ([#185]). Closes #122.
- **fix**: webhook body contract documented and tested: empty bodies and bodies with no recognised fields are accepted and produce an "Unknown alert"; only malformed bodies are rejected ([#197]). Closes #124.
- **tests**: end-to-end integration tests for webhook secret rotation covering the full rotation cycle from entry-data update through webhook re-registration ([#201]). Closes #121.
- **ci**: `pr-guards.yml` workflow enforces three process rules: `changelog-guard` (custom_components/ changes must accompany a CHANGELOG update), `label-guard` (every PR must carry a recognised release-notes label), `history-guard` (HISTORY.md only modifiable on bump branches) ([#206]).
- **ci**: bump `actions/checkout` to v6.0.3, hassfest and hacs/action to 2026-06-14 tips ([#224]).
- **ci**: add pip Dependabot; bump hacc to 0.13.205; document advisory scan rationale ([#215]).
- **ci**: pin dev dependencies for reproducible CI ([#211]). Closes #142.
- **ci**: add concurrency groups to `ci.yml` and `version-check.yml` to cancel redundant runs on new pushes ([#193]). Closes #175.
- **ci**: fix stale version comments in `copilot-setup-steps.yml` and `ci.yml` ([#184]). Closes #132.
- **docs**: add per-category Alarm Manager trigger table to the setup guide ([#214]).
- **docs**: clarify retention semantics: clearing is acknowledgement (the watermark advances), not deletion; alerts remain in the UniFi controller UI ([#213]).
- **docs**: document multi-controller and multi-site setup in README; clarifies the site name field and when to change from the default ([#203]). Closes #139.
- **docs**: add guardrail comment in `diagnostics.py` documenting which alert content fields are excluded and why ([#195]). Closes #129.
- **docs**: add missing files to `REPO_LAYOUT.md` ([#183]). Closes #131.
- **docs**: refresh stale CLAUDE.md references; add doc-only fast path to DEVELOPING.md ([#182]). Closes #169.

## 2026-06-12

- **release**: v1.8.0-pre1 tagged. First checkpoint of the v1.8.0 "Trust and Hardening" cycle: manifest was set to `1.8.0-pre1` by #113 at cycle start, and this tags it now that the first batch of work has merged. Headline: privacy and persistence hardening (raw payload dropped from storage, watermark persistence coalesced and now self-reporting via a repair issue), dependency and coverage detection in CI (pip-audit, Codecov), per-category webhook health visibility, and the TODO.md -> GitHub Issues workflow migration. No `CHANGELOG.md` change (pre-release).
- **ci**: add pip-audit dependency scanning, CodeQL via default setup ([#178]). Adds an advisory, non-blocking pip-audit job over `requirements-dev.txt` on every push/PR plus a weekly schedule; static analysis runs through CodeQL default setup after an advanced workflow conflicted with it. Closes the no-SAST, no-dependency-scan gap (#165); the 60 current findings are dev-toolchain only (manifest ships no pinned requirements) and tracked in #180.
- **feat**: surface watermark persist failures as a repair issue ([#179]). A failed `Store.async_save` after a Clear left the in-memory clear intact but the watermark unwritten, so `open_count` rebounded on restart; the coordinator now raises an `issue_registry` repair that self-heals on the next successful persist (#163).
- **feat**: per-category webhook health signal ([#177]). Surfaces never_received / healthy / stale health over a 7-day window (set only on the push path) so users can confirm Alarm Manager wiring without waiting for a real alert.
- **fix**: coalesce watermark persistence and surface background failures ([#160]). Coalesces watermark persists and routes background-task failures through a done-callback that logs non-`CancelledError` exceptions, the logging path #179 later built its repair issue on.
- **ci**: pin ruff and remove dead test import ([#159]). An unpinned ruff pulled 0.15.16 on fresh installs and flagged lint older ruff accepted, breaking `make check`; pin `ruff==0.15.16` for deterministic lint across CI and local.
- **docs**: add landed-in-dev label to keep the milestone view honest ([#158]). PRs target `dev` not `main`, so `Closes #NN` does not fire until release; the label distinguishes shipped-to-dev work from not-started in the milestone view.
- **fix**: transient-failure backoff for probe_system_log_endpoint ([#157]). A persistent non-404 (e.g. a proxy returning 503) made the probe fire every poll, doubling controller request rate; after 5 consecutive transient failures it now caches the legacy path for 1 hour.
- **feat**: localise remaining inline strings in the sensor platform ([#156]). Removes the last hard-coded user-facing strings (native_value returns None for HA's built-in translated Unknown state) and replaces em-dashes and emoji per the writing-style rule.
- **docs**: prefer gh issue develop so issue<>PR links register ([#152]). Documents creating branches via `gh issue develop` so the issue/PR link populates the sidebar despite PRs targeting the non-default `dev` branch.
- **fix**: force scripts/* stdout to UTF-8 on cp1252 Windows consoles ([#151]). The validators print a Unicode check-mark glyph that crashed cp1252 Windows shells with `UnicodeEncodeError` even when the underlying tool passed; force stdout to UTF-8.
- **fix**: seed event entity counter on add to prevent stale alert replay ([#150]). `_last_seen_count` started at 0, so the first update after an options-flow reload re-fired the most recent alert as a fresh event; seed it from restored `CategoryState.alert_count` in `async_added_to_hass` (#116).
- **chore**: allow gh issue commands in claude permissions ([#149]). Adds `Bash(gh issue *)` to the settings allowlist so issue triage skips the permission prompt.
- **security**: drop raw payload from persisted UniFiAlert ([#147]). `to_dict()` serialised the full UniFi payload (unredacted MACs, IPs, hostnames, possibly non-JSON-safe) into `.storage`; the persisted record now drops `raw` (#115).
- **ci**: bump home-assistant/actions ([#146]). Dependabot bump of `home-assistant/actions` to the current pinned SHA.
- **ci**: add Codecov coverage reporting with a 95% floor ([#145]). Wires `pytest-cov` and Codecov with a 95% branch-coverage minimum enforced locally and in CI, plus a README and info.md badge.
- **docs**: align agent instructions with the GitHub Issues workflow ([#144]). Follow-up to the Issues migration: updates copilot-instructions and persona surfaces to track and file work in Issues and drops the stale TODO pointer.
- **docs**: migrate work tracking from TODO.md to GitHub Issues ([#114]). A six-lens review seeded the v1.8 and v1.9 backlog into Issues and themed v1.8.0 as Trust and Hardening; work tracking moves off `docs/TODO.md`.

## 2026-05-29

- **release**: v1.7.0 tagged. Promotes v1.7.0-pre2 to stable after on-controller validation confirmed byte-identical entity_id, unique_id, and friendly_name snapshots across the pre1 -> pre2 upgrade (the ARCH-2 translation-key migration regression test). Cycle headline: documentation + architecture. Ships SEC-1 (fail-closed webhook auth with schema v3 migration), ARCH-1 (`UniFiClientConfig` TypedDict), CI-1 (`mypy --strict` enabled), ARCH-2 (entity-name translation keys, unlocking localisation), ARCH-3 (config-flow test package split), ARCH-4 (`SensorStateClass.MEASUREMENT` confirmed on count sensors), DOC-A (35-point documentation accuracy reconciliation), DOC-B (new troubleshooting / privacy / tested-controllers / uninstall sections plus README + info.md restructure), QUAL-1 (WHY comments on dedup / watermark / system-log probe), plus off-plan tooling and docs (`scripts/run_lint.py` / `run_typecheck.py`, AGENTS.md rewrite, Copilot agent definitions, 232 lines of coverage tests). Closes all v1.7.0 ROADMAP items.
- **security**: scope read-only GitHub Actions workflows to `permissions: contents: read` ([#111]). Closes a CodeQL "Workflow does not contain permissions" finding on `.github/workflows/copilot-setup-steps.yml` (shipped in #104) and pre-emptively applies the same minimum scope to `ci.yml` and `version-check.yml`, which were latent CodeQL warnings outside the diff of any individual feature PR. `release.yml` and `pr-labeler.yml` already had explicit permissions blocks.
- **chore**: start v1.8.0-pre1 development cycle ([#113]). Manifest bumped to `1.8.0-pre1`; no tag pushed. Next bump (`bump_version.py --pre`) produces the `v1.8.0-pre1` tag once the first batch of v1.8 work has merged.

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
[#111]: https://github.com/PHeonix25/unifi_alerts/pull/111
[#113]: https://github.com/PHeonix25/unifi_alerts/pull/113
[#114]: https://github.com/PHeonix25/unifi_alerts/pull/114
[#144]: https://github.com/PHeonix25/unifi_alerts/pull/144
[#145]: https://github.com/PHeonix25/unifi_alerts/pull/145
[#146]: https://github.com/PHeonix25/unifi_alerts/pull/146
[#147]: https://github.com/PHeonix25/unifi_alerts/pull/147
[#149]: https://github.com/PHeonix25/unifi_alerts/pull/149
[#150]: https://github.com/PHeonix25/unifi_alerts/pull/150
[#151]: https://github.com/PHeonix25/unifi_alerts/pull/151
[#152]: https://github.com/PHeonix25/unifi_alerts/pull/152
[#156]: https://github.com/PHeonix25/unifi_alerts/pull/156
[#157]: https://github.com/PHeonix25/unifi_alerts/pull/157
[#158]: https://github.com/PHeonix25/unifi_alerts/pull/158
[#159]: https://github.com/PHeonix25/unifi_alerts/pull/159
[#160]: https://github.com/PHeonix25/unifi_alerts/pull/160
[#177]: https://github.com/PHeonix25/unifi_alerts/pull/177
[#178]: https://github.com/PHeonix25/unifi_alerts/pull/178
[#179]: https://github.com/PHeonix25/unifi_alerts/pull/179
[#182]: https://github.com/PHeonix25/unifi_alerts/pull/182
[#183]: https://github.com/PHeonix25/unifi_alerts/pull/183
[#184]: https://github.com/PHeonix25/unifi_alerts/pull/184
[#185]: https://github.com/PHeonix25/unifi_alerts/pull/185
[#186]: https://github.com/PHeonix25/unifi_alerts/pull/186
[#187]: https://github.com/PHeonix25/unifi_alerts/pull/187
[#188]: https://github.com/PHeonix25/unifi_alerts/pull/188
[#189]: https://github.com/PHeonix25/unifi_alerts/pull/189
[#190]: https://github.com/PHeonix25/unifi_alerts/pull/190
[#191]: https://github.com/PHeonix25/unifi_alerts/pull/191
[#192]: https://github.com/PHeonix25/unifi_alerts/pull/192
[#193]: https://github.com/PHeonix25/unifi_alerts/pull/193
[#195]: https://github.com/PHeonix25/unifi_alerts/pull/195
[#197]: https://github.com/PHeonix25/unifi_alerts/pull/197
[#199]: https://github.com/PHeonix25/unifi_alerts/pull/199
[#200]: https://github.com/PHeonix25/unifi_alerts/pull/200
[#201]: https://github.com/PHeonix25/unifi_alerts/pull/201
[#203]: https://github.com/PHeonix25/unifi_alerts/pull/203
[#206]: https://github.com/PHeonix25/unifi_alerts/pull/206
[#211]: https://github.com/PHeonix25/unifi_alerts/pull/211
[#213]: https://github.com/PHeonix25/unifi_alerts/pull/213
[#214]: https://github.com/PHeonix25/unifi_alerts/pull/214
[#215]: https://github.com/PHeonix25/unifi_alerts/pull/215
[#217]: https://github.com/PHeonix25/unifi_alerts/pull/217
[#224]: https://github.com/PHeonix25/unifi_alerts/pull/224
[#234]: https://github.com/PHeonix25/unifi_alerts/pull/234
[#235]: https://github.com/PHeonix25/unifi_alerts/pull/235

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
