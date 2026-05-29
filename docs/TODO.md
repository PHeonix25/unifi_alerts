# TODO

Outstanding work only. Items are removed when they ship; completion lives in `docs/HISTORY.md`, and the per-release plan lives in `docs/ROADMAP.md`. Within each release the items are ordered by value (highest first); the trailing size tag (S/M/L) is a rough effort and review-time guide, so a free slot can take the next item that fits it.

## v1.8.0: Trust and Hardening

Correctness, privacy, security, and onboarding-confidence work. The items marked "v2.0 gate" are also prerequisites for the HACS default submission (see `docs/ROADMAP.md`).

### High value

- **Stop persisting raw alert payloads to disk** (`models.py`, `coordinator.py`) [S, v2.0 privacy gate]: `UniFiAlert.to_dict()` serialises the entire `raw` payload (client MACs, IPs, hostnames) into `.storage`, the one place those fields are not already redacted, and a non-JSON value in `raw` can break `Store.async_save`. Persist an explicit scalar field list (`message`, `received_at`, `key`, `device_name`, `site`, `severity`) and default `raw={}` in `from_dict`.
- **Fix stale `alert_received` replay on reload** (`event.py`) [S]: `_last_seen_count` resets to 0 in `__init__`, so the first coordinator update after any options save (which triggers a full reload) re-fires the last alert into users' automations. Seed `_last_seen_count` from the restored `state.alert_count` in `async_added_to_hass`, before the first `_handle_coordinator_update`.
- **Webhook health signal** (`webhook_handler.py`, `coordinator.py`, `diagnostics.py`) [S-M, v2.0-adjacent]: a per-category "last webhook received" timestamp plus a healthy/stale indicator, so a mis-pasted or never-pasted Alarm Manager URL surfaces as a visible state instead of indefinite silence. This is the single biggest source of "it does not work" reports for a push integration.
- **Coalesce watermark persistence and surface failures** (`coordinator.py`) [S]: the per-push fire-and-forget `async_save` has a lost-update hazard under bursts and no error path, so a failed persist dies silently. Route writes through `Store.async_delay_save`, and run background tasks through a shared helper whose done-callback logs any non-`CancelledError` exception.

### Medium value

- **Consolidate alert classification into a single seam** (`unifi_client._classify` vs `models.from_system_log_event`) [M]: two parallel category resolvers (legacy prefix-match map in the client; exact-key plus enum fallback in the model) with two separate unknown-key warning mechanisms. Collapse the taxonomy into one location so the v2 path and the legacy path share resolution and warning dedup, and the process-global `_unknown_system_log_keys` set stops being shared mutable state.
- **Extract controller auth into a dedicated seam** (`unifi_client.py`) [M-L]: auth-method autodetect, session state, login, key verification, and header construction are interleaved with transport, version probing, pagination, and parsing in one class. Pull the auth concern into its own strategy so a future third auth method or token refresh slots in cleanly and auth becomes unit-testable in isolation.
- **End-to-end secret-rotation test** (`tests/integration/`) [M]: prove the full cycle (options finish -> entry update -> reload -> webhook re-register) so the rotated `?token=` and the handler's compared secret stay in agreement; assert the old token returns 401 and the new token returns 200 after reload. Rotation is a security boundary, so this is worth more than its previous "every step is unit-tested" framing implied.
- **Catch `InvalidAuthError` on the re-auth retry** (`coordinator.py`) [S]: after a 401 triggers re-authentication, the retried fetch only catches `CannotConnectError`; a second `InvalidAuthError` escapes `_async_update_data` as a generic error instead of raising `ConfigEntryAuthFailed` to trigger HA re-auth. Catch it and add a coordinator test for the "re-auth succeeds, retry still 401" sequence.
- **Harden `_render_message_raw` substitution** (`models.py`) [S, M if a fix is needed]: sequential `str.replace` over controller-supplied `parameters` is order-dependent and lets a parameter value that itself contains a `{TOKEN}` be re-substituted. Switch to single-pass substitution and add tests for embedded-token, overlapping-prefix (`{IP}` vs `{IP_DST}`), and non-string parameter values.
- **Define the empty or malformed webhook contract** (`webhook_handler.py`, `coordinator.push_alert`) [S]: an authenticated POST with an empty or unrecognisable body currently flips the binary sensor to "Problem" and fires an event. Decide during implementation whether to skip `push_callback` when no recognisable fields are present, or to keep the behaviour; either way add a test that locks the chosen contract in.
- **Retention and data-handling clarity** (`coordinator.py`, README) [S-M, v2.0 privacy gate]: `clear()` advances the watermark but leaves `last_alert` (message, device name) in state and on disk, so a "cleared" category still retains identifying content. Clear `last_alert` on `clear()` (or document that clearing is acknowledgement, not deletion), and add a short README "Data handled and retention" section covering what is stored, where, and how to purge it.
- **Complete the Alarm Manager onboarding docs** (README, `docs/`) [S, v2.0 docs gate]: add a per-category trigger-mapping table and annotated screenshots for the Alarm Manager side (the most error-prone half of setup), and remove the "copy URLs before clicking Submit" footgun by re-showing the URLs after the entry is created (the options flow already supports this).

### Low value and guardrails

- **Disable redirect-following on authenticated outbound calls** (`unifi_client.py`) [S]: pass `allow_redirects=False` and treat a 3xx as an error, so the `X-API-Key` header and session cookie cannot ride a controller-issued redirect to another host.
- **Length-validate inbound `key`, `severity`, `device_name`** (`models.from_webhook_payload`) [S]: truncate them the same way `message` is, so a token-bearing caller cannot push unbounded values into state and logs.
- **Document the diagnostics content exclusion** (`diagnostics.py`) [S]: add a comment recording that per-category alert content (`message`, `device_name`, `raw`) is deliberately excluded and must stay excluded; if alert detail is ever added, route it through a field redactor.
- **Optional host guard on the controller URL** (`config_flow.py`) [S]: validation is scheme-only today. Optionally reject loopback and link-local hosts, or document that the URL is fully trusted under the local-admin model. Low priority guardrail.
- **Reconcile `docs/REPO_LAYOUT.md` with the file tree** [S]: add the missing `services.py`, `services.yaml`, `scripts/run_lint.py`, and `scripts/run_typecheck.py` rows; optionally add a `scripts/validate_docs.py` check that every `*.py` under `custom_components/` and `scripts/` appears at least once.
- **Fix the Actions version comments in `copilot-setup-steps.yml`** [S]: the pinned SHAs carry `# v4` and `# v5` comments but resolve to `# v6`, breaking the human-readable pin contract that Dependabot review relies on.

## v1.9.0: Localisation and Scale

### High value

- **Translatable category labels** (`const.py` `CATEGORY_LABELS`, platform files) [M]: entity name templates already use `_attr_translation_key`, but the `{category}` placeholder is filled from an English-only dict, leaving entity names half-translated for non-English Home Assistant. Give each category its own `translation_key` so the label resolves through the translation layer.
- **Self-healing system-log key map** (`models.py`, `const.py`, `diagnostics.py`) [S]: `SYSTEM_LOG_KEY_TO_CATEGORY` is intentionally incomplete, and the `SYSTEM_LOG_CATEGORY_FALLBACK` enum keeps unmapped events in roughly the right category, but there is no user-visible signal when a key is unclassified, so the map only improves via users who dig through DEBUG logs. Add an "uncategorised" counter or a diagnostics field listing recently seen unmapped keys so every install passively contributes the keys that surface in the wild.

### Medium value

- **Severity filtering for noisy categories** (config and options flow, coordinator) [M]: noisy categories are blunt on/off toggles today. A min-severity option (or a consistently surfaced severity attribute users can key automations off) makes them usable instead of muted on day one.
- **Clamp the watermark fetch window** (`coordinator.py`) [S-M]: `since = min(watermarks)` lets the fetch window grow without bound when one category is rarely cleared, re-paginating the full range every poll and risking recent alarms being pushed past `MAX_SYSTEM_LOG_PAGES`. Clamp to `max(min(watermarks), now - lookback_cap)` and log when the page cap is hit.
- **Probe backoff for the system-log endpoint** (`unifi_client.probe_system_log_endpoint`) [S]: a persistent non-404 failure re-probes on every poll forever, doubling the request rate against a misbehaving endpoint. Add a transient-failure counter that caches "legacy" after a threshold, with periodic re-probe.
- **Localise remaining inline strings** (`sensor.py` "No alerts yet", `strings.json`) [S]: move the code-level state string to a translation key, and replace emoji and em-dash-carried meaning in config descriptions with plain-text prefixes, so meaning survives translation and screen readers.
- **Multi-controller docs clarity** (README) [S]: document the multi-controller and multi-site pattern and clarify the `site` field. Defer full per-category site config (parked below, low value).

### Low value

- **Unicode and large-volume round-trip tests** (`tests/`) [S]: assert that non-ASCII alert text (emoji, CJK, RTL) and 300-character strings survive parse -> store -> restore and 255-character truncation, and that a roughly 500-alert batch keeps counts and watermark filtering deterministic.
- **Coverage measurement in CI** (`Makefile`, CI) [S]: add `--cov` reporting (not necessarily a gate) so thin-test regressions become visible.
- **Pin dev dependencies** (`requirements-dev.txt`) [M]: the unpinned `homeassistant`, `ruff`, `mypy`, and `pytest` floats make CI and local `make check` non-reproducible. Maintainer call on whether a hashed constraints file is warranted without enabling the pip Dependabot ecosystem.

### Process

- **Adopt GitHub Issues for the backlog** [M]: move outstanding items from this file into tracked issues so each carries a stable identifier that can be referenced in PRs and release notes, instead of local shorthand. Target landing this during the v1.9 cycle.

## Backlog: not yet scheduled

- **HACS default catalogue submission**: open the PR to <https://github.com/hacs/default> once the v1.x items and the v2.0 gates above are closed.
- **Tier 2 docs linter (markdownlint)**: layer `markdownlint-cli2` on top of `scripts/validate_docs.py` to catch structural issues (heading-level skips, mixed list markers, bare URLs, trailing whitespace) that a regex linter cannot. Adds a Node dependency; commit a `.markdownlint.json` config tuned for this repo. Run it from CI's `lint` job and the pre-push hook alongside the existing prose check. Low user value; revisit only if doc structure regressions recur.

## Known issues: intentional, do not action

- **`_device_info()` duplication**: duplicated identically across `binary_sensor.py`, `sensor.py`, `event.py`, `button.py`. Intentional for platform isolation; extract to a shared `entity_base.py` only if it becomes a maintenance burden.
