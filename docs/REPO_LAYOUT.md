# Repository layout

Per-file annotations describing what lives where, what each module is responsible for, and the load-bearing details that have caused regressions before. CLAUDE.md keeps the rules tight and points here for the detail.

```
custom_components/unifi_alerts/   # integration source
  __init__.py                     # entry setup/teardown, platform forwarding; raises ConfigEntryNotReady on auth or first-refresh failure so HA retries; emits _LOGGER.warning when SSL verification is disabled; unload order: coordinator.async_shutdown() > unregister webhooks > client.close()
  manifest.json                   # HA metadata (domain, version, iot_class); do NOT add "homeassistant" min-version key - it is not in the HA manifest schema and breaks hassfest
  const.py                        # all constants, category defs, UniFi key>category map; DEFAULT_VERIFY_SSL = True (secure by default); CONF_WEBHOOK_SECRET = "webhook_secret"
  models.py                       # UniFiAlert and CategoryState dataclasses; all datetimes are UTC-aware (datetime.now(UTC))
  unifi_client.py                 # async HTTP client, auth auto-detect
  coordinator.py                  # DataUpdateCoordinator, owns all category state; polling path sets is_alerting/last_alert directly (does NOT call apply_alert, so alert_count is not incremented); open_count filtered by last_cleared_at watermark (alarms since last Clear only); async_clear_category()/async_clear_all() are the sole clear entry points - they cancel tasks, advance watermark, persist via Store, notify; cancel_clear(category) cancels pending auto-clear tasks; async_restore_watermarks() loads persisted watermarks from storage on startup; async_shutdown() cancels all pending clear tasks on unload
  webhook_handler.py              # registers HA webhooks (POST-only), dispatches to coordinator; rejects requests missing/wrong ?token= with HTTP 401; bearer secret from CONF_WEBHOOK_SECRET
  config_flow.py                  # three-step UI setup (credentials > categories > webhook URLs with token) + options flow; generates CONF_WEBHOOK_SECRET via secrets.token_urlsafe(32) on first auth; network_device and network_client default OFF; options flow reads entry.options first, falls back to entry.data
  diagnostics.py                  # HA diagnostics platform; redacts password/api_key/username, exposes webhook URLs + coordinator state
  binary_sensor.py                # per-category + rollup binary sensors
  sensor.py                       # message, count, and rollup count sensors
  event.py                        # event entities, fire per alert
  button.py                       # manual clear buttons
  strings.json                    # UI copy for config flow; must be identical to translations/en.json - CI enforces this
  translations/en.json            # runtime translation file loaded by HA; must be identical to strings.json - CI enforces this
tests/
  conftest.py                     # shared fixtures, MOCK_CONFIG; make_hass() and make_entry() module-level helpers for setup/unload tests
  test_models.py
  test_coordinator.py
  test_unifi_client.py
  test_config_flow.py             # config flow steps, webhook URL token display, options flow defaults
  test_diagnostics.py             # diagnostics platform: redaction, webhook URL exposure, coordinator state
  test_webhook_handler.py         # WebhookManager: register/unregister, token auth, alert dispatch
  test_init.py                    # async_setup_entry / async_unload_entry lifecycle, teardown order
  test_entities.py                # all entity property methods: binary_sensor, sensor, event, button
.github/workflows/
  ci.yml                          # hassfest + hacs-preflight + HACS action + lint (ruff, mypy, translation drift) + pytest; runs on push/PR to main and dev
  version-check.yml               # enforces version format per branch: main=X.Y.Z stable, dev=X.Y.Z-preN; runs on push/PR to main and dev
  release.yml                     # triggered by version tags (v1.0.0 stable, v1.0.0-pre1 pre-release); validates tag matches manifest, packages the integration, and publishes via `gh release create --generate-notes` (NOT softprops/action-gh-release - that was removed; do not re-introduce it). Pre-release detection regex uses `grep -qE -- '-pre[0-9]+$'` (the `--` terminator is load-bearing).
  pr-labeler.yml                  # auto-applies a release-notes label to PRs based on Conventional Commit title prefix (feat/fix/docs/tests/ci/security). Manual labels always win. Eliminates the need to follow up `mcp__github__create_pull_request` with a manual `issue_write` label call.
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
  bump_version.py                 # release-prep helper. Modes: --pre (1.5.0-pre1 -> 1.5.0-pre2), --stable (1.5.0-pre3 -> 1.5.0; also rewrites CHANGELOG.md), --next-cycle (1.5.0 -> 1.6.0-pre1). Verifies clean tree, fetches dev, creates claude/bump-<new>, updates manifest.json (+ CHANGELOG for stable), stages, prints merge list since previous tag for the docs/HISTORY.md block. Pure stdlib.
  setup-labels.sh                 # one-shot script that creates the non-default labels referenced in `.github/release.yml` (`security`, `feat`, `fix`, `tests`, `ci`, `github-actions`, `dependencies`). Run once per fork via `./scripts/setup-labels.sh`. Idempotent - existing labels skipped. The `bug`, `enhancement`, and `documentation` labels are GitHub defaults; the rest do not exist on a fresh fork and the categories file is inert without them. `feat` and `fix` are Conventional-Commits aliases for `enhancement` and `bug` respectively - either label works for those categories.
Makefile                          # convenience targets: setup, setup-lint, lint, typecheck, validate, doc-check, test, check, help (default = help). Cross-platform: detects Windows vs Unix and uses .venv/Scripts/*.exe or .venv/bin/* accordingly. `py -3.12` on Windows, `python3.12` on Unix.
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
