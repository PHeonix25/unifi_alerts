# Repository layout

Per-file annotations describing what lives where, what each module is responsible for, and the load-bearing details that have caused regressions before. CLAUDE.md keeps the rules tight and points here for the detail.

```plain
custom_components/unifi_alerts/   # integration source
  __init__.py                     # entry setup/teardown, platform forwarding; raises ConfigEntryNotReady on auth or first-refresh failure so HA retries; emits _LOGGER.warning when SSL verification is disabled; unload order: coordinator.async_shutdown() > unregister webhooks > client.close()
  manifest.json                   # HA metadata (domain, version, iot_class); do NOT add "homeassistant" min-version key - it is not in the HA manifest schema and breaks hassfest
  const.py                        # all constants, category defs, UniFi key>category map; DEFAULT_VERIFY_SSL = True (secure by default); CONF_WEBHOOK_SECRET = "webhook_secret"
  models.py                       # UniFiAlert and CategoryState dataclasses; all datetimes are UTC-aware (datetime.now(UTC))
  unifi_client.py                 # async HTTP client (alarm fetch, pagination, system-log probe); composes a UniFiAuth instance (self._auth) for all auth concerns - does not proxy or duplicate its state
  unifi_auth.py                   # UniFiAuth: API-key verification and X-API-Key header construction (the only supported auth method); also owns CannotConnectError/SslCertificateError/InvalidAuthError (unifi_client.py re-exports them, so existing `from .unifi_client import ...` call sites elsewhere in the integration are unaffected)
  coordinator.py                  # DataUpdateCoordinator, owns all category state; polling path sets is_alerting/last_alert directly (does NOT call apply_alert, so alert_count is not incremented); open_count filtered by last_cleared_at watermark (alarms since last Clear only); async_clear_category()/async_clear_all() are the sole clear entry points - they cancel tasks, advance watermark, persist via Store, notify; cancel_clear(category) cancels pending auto-clear tasks; async_restore_watermarks() loads persisted watermarks from storage on startup; async_shutdown() cancels all pending clear tasks on unload
  webhook_handler.py              # registers HA webhooks (POST-only), dispatches to coordinator; rejects requests missing/wrong ?token= with HTTP 401; bearer secret from CONF_WEBHOOK_SECRET
  config_flow.py                  # three-step UI setup (credentials > categories > webhook URLs with token) + options flow; generates CONF_WEBHOOK_SECRET via secrets.token_urlsafe(32) on first auth; network_device and network_client default OFF; options flow reads entry.options first, falls back to entry.data
  diagnostics.py                  # HA diagnostics platform; redacts api_key/webhook_secret, exposes webhook URLs + coordinator state
  binary_sensor.py                # per-category + rollup binary sensors
  sensor.py                       # message, count, and rollup count sensors
  event.py                        # event entities, fire per alert
  button.py                       # manual clear buttons
  services.py                     # registers unifi_alerts.clear_category and unifi_alerts.clear_all HA service calls; delegates to coordinator
  services.yaml                   # HA service schema definition (clear_category: category field, clear_all: no fields)
  strings.json                    # UI copy for config flow; must be identical to translations/en.json - CI enforces this
  translations/en.json            # runtime translation file loaded by HA; must be identical to strings.json - CI enforces this
tests/
  conftest.py                     # root shared fixtures; Windows-only event-loop and socket workarounds (no-op on Linux/macOS)
  unit/                           # plain-mock unit tests - no real HA instance
    conftest.py                   # MOCK_CONFIG; make_hass() and make_entry() helpers for setup/unload tests
    config_flow/                  # config flow tests (split from monolithic test_config_flow.py in v1.7)
      __init__.py
      conftest.py                 # shared flow helpers and mock builders (make_flow, make_options_flow, make_reauth_flow)
      test_setup.py               # initial setup flow: user, categories, finish steps
      test_discovery.py           # SSDP discovery: async_step_ssdp URL pre-fill, dedup
      test_options_credentials.py # options flow: credential/URL changes, verify_ssl, duplicate-entry guard
      test_options_helpers.py     # pure options-flow helpers: form parsing, credential overrides, pending-data builders
      test_options_rotation_validation.py # options flow: regenerate-secret rotation, controller-side validation paths
      test_reauth.py              # reauth flow: async_step_reauth, repair issue
    coordinator/                  # coordinator tests (split from monolithic test_coordinator.py)
      __init__.py
      conftest.py                 # shared coordinator fixtures
      test_autoclear.py           # auto-clear scheduling, cancellation, async_shutdown
      test_persistence.py         # watermark persist/restore, legacy string format, persist-failed repair issue
      test_polling.py             # _async_update_data: v2/legacy dispatch, open_count, already-alerting guard, auth retry
      test_push_dedup.py          # push_alert: apply_alert, webhook dedup window, optimistic open_count increment
    unifi_client/                 # UniFiClient tests (split from monolithic test_unifi_client.py)
      __init__.py
      conftest.py                 # shared client fixtures
      test_legacy.py              # _classify, fetch_alarms probe chain, categorise_alarms, authenticate, close
      test_v2.py                  # probe_system_log_endpoint (cache/backoff), fetch_system_log_alarms (pagination, watermark)
    test_console_helper.py        # tests scripts/_console.py UTF-8 stdout forcing on Windows
    test_diagnostics.py           # diagnostics platform: redaction, webhook URL exposure, coordinator state
    test_entities.py              # all entity property methods: binary_sensor, sensor, event, button
    test_init.py                  # async_setup_entry / async_unload_entry lifecycle, teardown order, migration (v1->v2->v3)
    test_models.py
    test_services.py
    test_unifi_auth.py            # UniFiAuth in isolation via make_auth() - no full UniFiClient needed
    test_webhook_handler.py       # WebhookManager: register/unregister, token auth, alert dispatch
  integration/                    # full HA lifecycle tests using hass fixture
    conftest.py                   # entry fixture, mock_unifi_client, get_coordinator(); real entry setup/teardown
    test_auto_clear.py            # auto-clear timeout resets binary sensors
    test_lifecycle.py             # entity creation, options flow, coordinator wiring
    test_multi_entry.py           # two config entries active simultaneously
    test_webhook.py               # webhook HTTP dispatch end-to-end
.github/workflows/
  ci.yml                          # hassfest + hacs-preflight + HACS action + lint (ruff, mypy, translation drift) + pytest; runs on push/PR to main and dev
  version-check.yml               # enforces version format per branch: main=X.Y.Z stable, dev=X.Y.Z-preN; runs on push/PR to main and dev
  release.yml                     # triggered by version tags (v1.0.0 stable, v1.0.0-pre1 pre-release); validates tag matches manifest, packages the integration, and publishes via `gh release create --generate-notes` (NOT softprops/action-gh-release - that was removed; do not re-introduce it). Pre-release detection regex uses `grep -qE -- '-pre[0-9]+$'` (the `--` terminator is load-bearing).
  pr-release-label.yml            # applies a release-notes label from the PR's Conventional Commit title prefix (feat/fix/docs/tests/ci/security) and verifies one is present, in a single job so the two steps can't race across separate workflow runs. Manual labels always win.
  pr-guards.yml                   # two PR checks on dev/main PRs: changelog-guard (custom_components/ edits need a CHANGELOG.md bullet), history-guard (docs/HISTORY.md only changes on claude/bump-* branches)
  codeql.yml                      # CodeQL workflow scaffold; Python SAST actually runs via GitHub's CodeQL default setup (Settings > Code security and analysis), not this workflow - see docs/DEVELOPING.md CI overview
  dependency-audit.yml            # pip-audit dependency vulnerability scan; advisory only (continue-on-error on the audit step); runs on push/PR to dev and main plus a weekly Monday 06:00 UTC schedule
  copilot-setup-steps.yml         # provisions .venv (make setup) before the GitHub Copilot coding agent starts a session
.github/
  dependabot.yml                  # tracks the github-actions ecosystem only (weekly, Brisbane TZ); minor+patch grouped, major bumps individual. Required to keep the SHA pins fresh - do NOT remove. Python deps stay manual.
  release.yml                     # release-notes categories file used by `gh release create --generate-notes` to group merged PRs by label (Security / Bug Fixes / Features / Documentation / Tests / CI / Other). DIFFERENT FILE from .github/workflows/release.yml.
  ISSUE_TEMPLATE/
    bug_report.yml                # required-field bug template; warns users to redact `?token=...` from logs.
    feature_request.yml           # problem > solution > alternatives template.
    config.yml                    # disables blank issues; surfaces the security-advisory link + Discussions.
    unclassified_event_key.yml    # for reporting UniFi event keys not yet in UNIFI_KEY_TO_CATEGORY.
.githooks/
  pre-push                        # local gate: thin wrapper around `make check`. Install with: git config core.hooksPath .githooks
scripts/
  validate_hacs.py                # pure-Python HACS manifest pre-flight; checks required fields, iot_class, dependencies (no HA core built-ins); run locally or in CI
  validate_docs.py                # pure-Python docs prose linter; bans em-dash, unicode arrows, and 'bundle/cluster/track/session N' framing; enforces HISTORY.md '## YYYY-MM-DD' h2 format. Wired into make validate, make doc-check, pre-push hook, and CI hacs-preflight job.
  check_translations.py           # pure-Python byte-identical check between strings.json and translations/en.json. Replaces the previous `diff` shell command so the check works on Windows (cmd / PowerShell) as well as Unix. Wired into make doc-check and CI lint job.
  run_lint.py                     # cross-platform entry point for `make lint`; runs ruff check and ruff format in sequence. Replaces the Makefile ifeq(OS,Windows_NT) shim so lint runs identically on Linux, macOS, and Windows.
  run_typecheck.py                # cross-platform entry point for `make typecheck`; runs mypy with the same flags CI uses. Companion to run_lint.py.
  bump_version.py                 # release-prep helper. Modes: --pre (1.5.0-pre1 -> 1.5.0-pre2), --stable (1.5.0-pre3 -> 1.5.0; also rewrites CHANGELOG.md), --next-cycle (1.5.0 -> 1.6.0-pre1). Verifies clean tree, fetches dev, creates claude/bump-<new>, updates manifest.json (+ CHANGELOG for stable), stages, prints merge list since previous tag for the docs/HISTORY.md block. Pure stdlib.
  seed_issues.py                  # one-shot migration tool that seeded the v1.8/v1.9/v2.0 backlog into GitHub Issues. Not intended for re-use; kept for reference.
  _console.py                     # shared stdout encoding helper; forces UTF-8 on Windows cp1252 consoles so scripts that print non-ASCII glyphs (e.g. the ✅ check mark) do not crash. Imported at the top of every standalone scripts/*.py entry point.
  setup-labels.sh                 # one-shot script that creates the non-default labels referenced in `.github/release.yml` (`security`, `feat`, `fix`, `tests`, `ci`, `github-actions`, `dependencies`). Run once per fork via `./scripts/setup-labels.sh`. Idempotent - existing labels skipped. The `bug`, `enhancement`, and `documentation` labels are GitHub defaults; the rest do not exist on a fresh fork and the categories file is inert without them. `feat` and `fix` are Conventional-Commits aliases for `enhancement` and `bug` respectively - either label works for those categories.
Makefile                          # convenience targets: setup, setup-lint, lint, typecheck, validate, doc-check, test, check, help (default = help). Cross-platform: detects Windows vs Unix and uses .venv/Scripts/*.exe or .venv/bin/* accordingly. `py -3.14` on Windows, `python3.14` on Unix.
requirements-dev.txt              # full dev dependencies (Home Assistant + test stack); used by make setup and CI test/lint jobs
requirements-lint.txt             # minimal lint deps (ruff + mypy only); used by make setup-lint for fast lint-only workflows
hacs.json
pyproject.toml                    # ruff and mypy config
pytest.ini
README.md                         # user-facing install, setup, and contributing guide
CHANGELOG.md                      # Keep-a-Changelog file. The `[Unreleased]` section accumulates user-visible changes between tags. `docs/HISTORY.md` is the dated narrative source-of-truth; `CHANGELOG.md` is the user-facing summary scoped to releases. Pre-releases (`X.Y.Z-preN`) are NOT listed individually - only the consolidated `X.Y.Z` entry that bundles them.
SECURITY.md                       # vulnerability disclosure policy. Reports go via GitHub private security advisories. Do NOT funnel security reports through public issues.
CODEOWNERS                        # auto-requests review from @PHeonix25 on every PR.
```
