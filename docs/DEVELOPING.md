# Developing unifi_alerts

## Prerequisites

- Python 3.12 or newer
- Git

## Local setup

```bash
git clone https://github.com/PHeonix25/unifi_alerts
cd unifi_alerts

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
.\.venv\Scripts\Activate.ps1    # Windows (PowerShell)

# Install test and lint dependencies
pip install pytest pytest-asyncio pytest-homeassistant-custom-component aiohttp ruff mypy
```

## Running tests

```bash
# Run all tests
pytest tests/ -v

# Run a single file
pytest tests/test_coordinator.py -v

# Run with coverage
pytest tests/ --cov=custom_components/unifi_alerts --cov-report=term-missing
```

All tests must pass before committing. See `TESTING.md` for what is and isn't covered.

## Linting and type checking

```bash
# Lint (errors only)
ruff check custom_components/

# Format check
ruff format --check custom_components/

# Auto-fix formatting
ruff format custom_components/

# Type check
mypy custom_components/unifi_alerts --ignore-missing-imports
```

CI runs all of these on every push via `.github/workflows/ci.yml`. Fix any failures before opening a PR.

## Project structure

See `ARCHITECTURE.md` for a full module breakdown and data-flow diagram. The short version:

```
custom_components/unifi_alerts/   # integration source
tests/                            # unit tests (plain mocks, no real HTTP)
.github/workflows/                # CI (hassfest, HACS validate, ruff, mypy, pytest)
```

## Adding a new alert category

1. Add a `CATEGORY_*` constant to `const.py`.
2. Append it to `ALL_CATEGORIES`.
3. Add entries to `CATEGORY_LABELS`, `CATEGORY_ICONS`, and `CATEGORY_ICONS_OK`.
4. Map any known UniFi event keys to it in `UNIFI_KEY_TO_CATEGORY`.
5. Add parametrised test cases to `tests/test_unifi_client.py::TestClassify::test_known_keys`.

## Adding new UniFi event keys

When a user reports an unrecognised alert key, add it to `UNIFI_KEY_TO_CATEGORY` in `const.py` and add a corresponding entry to `tests/test_unifi_client.py::TestClassify::test_known_keys`. See `UNIFI.md` for the key taxonomy.

## Keeping strings.json and translations/en.json in sync

HA requires `strings.json` and `translations/en.json` to match exactly. Edit both files together — they are intentionally kept as copies of each other. A future CI check will catch drift (see TODO).

## Testing manually in Home Assistant

1. Copy `custom_components/unifi_alerts/` into your HA `config/custom_components/` directory.
2. Restart HA.
3. Go to **Settings → Devices & Services → Add Integration** and search for "UniFi Alerts".
4. Complete the config flow (controller URL, credentials, categories).
5. After setup, navigate to **Settings → Devices & Services → UniFi Alerts → Download diagnostics** to find your webhook URLs.
6. Paste each webhook URL into UniFi Alarm Manager (one per category).
7. Trigger a test alert from the UniFi controller and confirm the binary sensor flips on.

## CI overview

| Job | What it does |
|---|---|
| `validate` | Runs HA's `hassfest` action — validates manifest, quality scale, translations |
| `hacs` | Validates `hacs.json` and repository structure for HACS listing |
| `lint` | `ruff` + `mypy` on Python 3.12 |
| `test` | `pytest` on Python 3.12 |

All four jobs must pass before merging to `main`.

## Branching and PRs

- Work on a feature branch (`feat/...`) or fix branch (`fix/...`).
- Keep PRs focused — one logical change per PR.
- Every PR that adds functionality must include tests.
- Update `HISTORY.md` with a dated entry describing the change.

## Release process

Stable releases require **three** PRs, in order. Skipping or mis-ordering them causes merge-base drift that turns the next release into a conflict storm.

### PR 1 — version bump + CHANGELOG (feature/* → dev)

1. Bump `manifest.json` version from `X.Y.Z-preN` to `X.Y.Z`.
2. In `CHANGELOG.md`: rename `[Unreleased]` to `[X.Y.Z] — YYYY-MM-DD`, insert a fresh empty `[Unreleased]` above it, and add a `[X.Y.Z]: …/releases/tag/vX.Y.Z` compare link at the bottom.
3. Open a PR targeting `dev`. Merge it normally (squash is fine for feature→dev).

### PR 2 — dev → main (the release PR)

> **MUST be merged as "Create a merge commit". Never squash.**

GitHub's "Squash and merge" collapses all dev commits into a single new commit whose only parent is the previous `main` tip. This severs `dev`'s ancestry from `main`: the merge base never advances, and the next release will conflict on every file both branches touched since the previous release.

After this PR merges, push the version tag:

```bash
git checkout main && git pull origin main
git tag vX.Y.Z && git push origin vX.Y.Z
```

### PR 3 — main → dev (sync merge, mandatory)

Immediately after PR 2 merges, bring the new squash commit into `dev`'s ancestry:

```bash
git checkout dev && git pull origin dev
git checkout -b claude/sync-main-to-dev-X.Y.Z
git merge origin/main          # merge the new squash commit as a second parent
# resolve any trivial conflicts (version number: take dev's X.(Y+1).0-pre1)
git push -u origin claude/sync-main-to-dev-X.Y.Z
```

Open a PR targeting `dev`. **Merge as "Create a merge commit"** — not squash. The resulting commit will have `origin/main`'s tip as its second parent, making `git merge-base dev main` point at the new `vX.Y.Z` squash commit rather than the previous release.

> **Common mistake (v1.3.0 / PR #47):** merging `origin/main` while `main` still points at the *previous* stable tag instead of the new squash commit. The tree content looks correct so CI passes, but the parent pointer is wrong and the merge base does not advance. Always run `git fetch origin main && git log --oneline origin/main -1` to confirm `main` is at the new release commit before running `git merge origin/main`.
