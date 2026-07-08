# Contributing to UniFi Alerts

Thanks for your interest in contributing! This guide covers the essentials. For detailed walkthroughs, refer to the full developer documentation.

---

## Local setup

```bash
git clone https://github.com/PHeonix25/unifi_alerts
cd unifi_alerts
git config core.hooksPath .githooks   # enable the pre-push gate
make setup                             # python3.14 -m venv .venv + pip install
```

The pre-push hook at `.githooks/pre-push` runs the full test and lint suite automatically before every push. Do not bypass it with `--no-verify`.

See [docs/DEVELOPING.md](docs/DEVELOPING.md) for the full setup instructions, including agent session bootstrap and Windows-specific notes.

---

## Pull request rules

Every PR must satisfy the following checks. They all run mechanically in CI; no surprises on submission.

### Branch target

- **Target `dev`, never `main`.** The stable branch is only updated from `dev` via a merge commit. All feature and fix branches must target `dev`.

### Title format

- **Start with a Conventional Commit prefix:** `feat:`, `fix:`, `docs:`, `ci:`, `tests:`, `security:`, `chore:`, or `refactor:`.
- Example: `fix: add unit test for webhook token validation`

The `pr-labeler` workflow auto-applies release-notes labels based on your prefix. If you skip the prefix, apply a label manually (see below).

### Labels

- **Every PR must carry at least one release-notes label** so auto-generated release notes sort it into the right category. Valid labels: `security`, `bug` / `fix`, `enhancement` / `feat`, `documentation`, `tests`, `ci`, `github-actions`, `dependencies`.
- PRs with Conventional Commit titles are labelled automatically.
- If you skip the CC prefix, apply a label by hand.

The `label-guard` workflow enforces this check.

### CHANGELOG

- **For user-visible changes to `custom_components/`,** add a bullet to the `[Unreleased]` section in `CHANGELOG.md`. Use past tense: "Added support for X", "Fixed Y bug", etc. Reference the PR number at the end: `([#NN])`.
- **Exemptions:** internal changes, test-only changes, documentation changes, or changes with the `skip-changelog` label applied. Use `skip-changelog` when a code change genuinely has no user-visible effect.

The `changelog-guard` workflow enforces this check.

### Code quality

- Run `make check` locally before pushing. This runs lint, type check, HACS preflight, and all tests:

```bash
make check       # full suite: lint + typecheck + validate + tests
make lint        # ruff only
make typecheck   # mypy only
make test        # pytest only
```

For doc-only PRs (no `custom_components/` changes), use `make doc-check` instead; it skips the full test suite.

See [docs/TESTING.md](docs/TESTING.md) for test layout, conventions, and how to run individual test files.

### strings.json and translations/en.json

- These two files must remain identical. If your change touches either, edit both together. The lint check will catch drift.

---

## Further reading

| Document | When to read |
|---|---|
| [docs/DEVELOPING.md](docs/DEVELOPING.md) | Local setup, running checks, CI overview, branching and releases |
| [docs/TESTING.md](docs/TESTING.md) | Test directory structure, test conventions, running tests |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the modules fit together |
| [docs/HOMEASSISTANT.md](docs/HOMEASSISTANT.md) | Home Assistant specific patterns: coordinators, entities, config flow |
| [docs/UNIFI.md](docs/UNIFI.md) | UniFi API, auth methods, alarm payload taxonomy |
| [docs/REPO_LAYOUT.md](docs/REPO_LAYOUT.md) | Per-file responsibilities |
| [CLAUDE.md](CLAUDE.md) | Non-negotiable constraints and coding conventions |

Questions? Open an [issue](https://github.com/PHeonix25/unifi_alerts/issues) or post in the PR discussion thread.
