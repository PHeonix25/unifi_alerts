# Developing unifi_alerts

## Prerequisites

- Python 3.12 or newer
- Git

## Local setup

```bash
git clone https://github.com/PHeonix25/unifi_alerts
cd unifi_alerts
git config core.hooksPath .githooks   # enable the pre-push gate
make setup                             # python3.12 -m venv .venv + pip install -r requirements-dev.txt
```

`requirements-dev.txt` is the single source of truth for dev dependencies; both CI jobs install from the same file.

## Running checks

```bash
make check       # default; runs lint + typecheck + HACS preflight + translation drift + pytest
make lint        # ruff lint + format check
make typecheck   # mypy
make validate    # scripts/validate_hacs.py (HACS manifest pre-flight)
make test        # pytest
```

All `make` targets use `.venv` in the repo root; never the system Python.

If you prefer raw commands:

```bash
.venv/bin/pytest tests/ -v                                  # all tests (unit + integration)
.venv/bin/pytest tests/unit/test_coordinator.py -v          # one file
.venv/bin/pytest tests/integration/ -v -m integration       # integration only
.venv/bin/pytest tests/ --cov=custom_components/unifi_alerts --cov-report=term-missing
```

CI runs the same checks on every push via `.github/workflows/ci.yml`. The pre-push hook at `.githooks/pre-push` runs them locally first; do not bypass with `--no-verify`.

## Project structure

See `docs/ARCHITECTURE.md` for the full module breakdown. Short version:

```
custom_components/unifi_alerts/   # integration source
tests/unit/                       # unit tests (plain mocks, no real HTTP)
tests/integration/                # full HA lifecycle tests using the hass fixture
.github/workflows/                # CI (hassfest, HACS validate, ruff, mypy, pytest, version-check, release)
```

## Adding a new alert category

1. Add a `CATEGORY_*` constant to `const.py`.
2. Append it to `ALL_CATEGORIES`.
3. Add entries to `CATEGORY_LABELS`, `CATEGORY_ICONS`, and `CATEGORY_ICONS_OK`.
4. Map any known UniFi event keys to it in `UNIFI_KEY_TO_CATEGORY`.
5. Add parametrised test cases to `tests/unit/test_unifi_client.py::TestClassify::test_known_keys`.

## Adding new UniFi event keys

When a user reports an unrecognised alert key, add it to `UNIFI_KEY_TO_CATEGORY` in `const.py` and add a corresponding entry to `tests/unit/test_unifi_client.py::TestClassify::test_known_keys`. See `docs/UNIFI.md` for the key taxonomy.

## Keeping strings.json and translations/en.json in sync

HA requires `strings.json` and `translations/en.json` to match exactly. Edit both files together; the CI `lint` job and the pre-push hook diff the two files and fail on drift.

## Testing manually in Home Assistant

1. Copy `custom_components/unifi_alerts/` into your HA `config/custom_components/` directory.
2. Restart HA.
3. Go to **Settings > Devices & Services > Add Integration** and search for "UniFi Alerts".
4. Complete the config flow (controller URL, credentials, categories).
5. After setup, navigate to **Settings > Devices & Services > UniFi Alerts > Download diagnostics** to find your webhook URLs.
6. Paste each webhook URL into UniFi Alarm Manager (one per category).
7. Trigger a test alert from the UniFi controller and confirm the binary sensor flips on.

## CI overview

| Job | What it does |
|---|---|
| `validate` | Runs HA's `hassfest` action; validates manifest, quality scale, translations |
| `hacs-preflight` | Runs `scripts/validate_hacs.py` (pure-Python pre-flight) before the slower HACS action |
| `hacs` | Validates `hacs.json` and repository structure for HACS listing |
| `lint` | `ruff check` + `ruff format --check` + `mypy` + `strings.json`/`translations/en.json` drift diff |
| `test` | `pytest` against `tests/unit/` and `tests/integration/` |
| `pip-audit` | Dependency vulnerability scan against `requirements-dev.txt`. Advisory only (`continue-on-error` on the audit step); it never blocks a merge |

Static security analysis (CodeQL SAST) for Python runs through GitHub's CodeQL **default setup**, configured in Settings > Code security and analysis, with findings in the repository Security tab. It is not a workflow in this repository: an advanced workflow-based CodeQL config cannot coexist with default setup (GitHub rejects the SARIF upload), so SAST lives in default setup and the workflow below owns dependency auditing only.

`dependency-audit.yml` holds the `pip-audit` job. It runs on every push and pull request to `dev` and `main`, plus a weekly Monday 06:00 UTC schedule so newly disclosed vulnerabilities are caught even when the code has not changed. `pip-audit` is intentionally non-blocking: the maintainer reviews its output and bumps `requirements-dev.txt` when a finding warrants it. `continue-on-error` sits on the audit step (not the job) so a finding leaves the check green while the report still appears in the log.

`version-check.yml` enforces the version format per branch (`X.Y.Z` on `main`, `X.Y.Z-preN` on `dev`). `release.yml` triggers on tags and publishes via `gh release create --generate-notes`. All checks except `pip-audit` must pass before merging.

### PR guards (`pr-guards.yml`)

Three additional checks run on every pull request to `dev` or `main`:

| Check | What it enforces |
|---|---|
| `changelog-guard` | `custom_components/` edits must be accompanied by a `CHANGELOG.md` update. Fails if code changes but the changelog does not. |
| `label-guard` | The PR must carry at least one label recognised by `.github/release.yml` (`security`, `bug`/`fix`, `enhancement`/`feat`, `documentation`, `tests`, `ci`, `github-actions`, `dependencies`). `pr-labeler.yml` auto-applies labels for PRs with Conventional Commit prefixes; for others, apply manually. |
| `history-guard` | `docs/HISTORY.md` may only be modified on `claude/bump-*` branches (version-bump PRs). Feature and fix PRs must not touch it. |

**Escaping the changelog guard:** apply the `skip-changelog` label if a code change genuinely has no user-visible effect (e.g. a coverage-only test change that incidentally touches a production file). The `ci`, `tests`, `documentation`, `dependencies`, and `github-actions` labels also bypass the guard automatically, since those categories of work rarely need a user-facing changelog entry.

**Label timing:** `pr-labeler.yml` and `label-guard` run concurrently on PR open. If the auto-labeller wins first, both pass in a single round. If `label-guard` fires before the label is applied, it fails on the first run but re-runs on the `labeled` event and passes once the label is present. This is expected behaviour; the status check clears without any manual intervention.

## Branching and PRs

- Work on a `feature/...`, `fix/...`, or `claude/...` branch off `dev`.
- Keep PRs focused: one logical change per PR.
- Every PR that adds functionality must include tests.
- Apply a label recognised by `.github/release.yml` (`security`, `feat`/`enhancement`, `fix`/`bug`, `documentation`, `tests`, `ci`, `dependencies`) so auto-generated release notes group the PR correctly. The `label-guard` CI check enforces this mechanically.
- `docs/HISTORY.md` is updated only in version-bump PRs (`scripts/bump_version.py --pre` or `--stable`), not in individual feature or fix PRs. The bump PR adds a single `## YYYY-MM-DD` block summarising every PR merged since the previous tag. The `history-guard` CI check enforces this mechanically.
- For user-visible changes, add a bullet under `[Unreleased]` in `CHANGELOG.md`. The `changelog-guard` CI check enforces this mechanically for `custom_components/` edits.

## Release process

Stable releases require **two** PRs, in order. Skipping or mis-ordering them causes merge-base drift that turns the next release into a conflict storm.

### PR 1 - version bump + CHANGELOG (feature/* > dev)

1. Bump `manifest.json` version from `X.Y.Z-preN` to `X.Y.Z`.
2. In `CHANGELOG.md`: rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, insert a fresh empty `[Unreleased]` above it, and add a `[X.Y.Z]: …/releases/tag/vX.Y.Z` compare link at the bottom.
3. Open a PR targeting `dev`. Merge it normally (squash is fine for feature>dev).

### PR 2 - dev > main (the release PR)

> **MUST be merged as "Create a merge commit". Never squash.**

GitHub's "Squash and merge" collapses all dev commits into a single new commit whose only parent is the previous `main` tip. This severs `dev`'s ancestry from `main`: the merge base never advances, and the next release will conflict on every file both branches touched since the previous release.

After this PR merges, push the version tag:

```bash
git checkout main && git pull origin main
git tag vX.Y.Z && git push origin vX.Y.Z
```

> **No `main > dev` sync merge needed.** Earlier releases (v1.3.0, v1.4.0) ran a third PR (`claude/sync-main-to-dev-X.Y.Z`) because the `dev > main` PR was squash-merged, which left the release commit out of dev's ancestry. With merge-commit-only on `main` (PR 2 above), dev's tip is already the second parent of the release commit; the merge base advances correctly and no sync is required. Attempting one now also conflicts with the squash-only-on-dev ruleset.
