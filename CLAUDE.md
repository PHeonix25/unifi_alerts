# CLAUDE.md - unifi_alerts

This is the primary context file for Claude Code. Read this first, then follow the references.

## What this project is

[`AGENTS.md`](AGENTS.md) is the single home for the shared facts every agent needs: the repo purpose (a Home Assistant custom integration, `domain: unifi_alerts`, distributed via HACS), the tech stack, the build/test commands, and the repo map. Read it first. This file adds the Claude-specific working style, the full non-negotiable constraint list, and the day-to-day workflow rules; it does not repeat the shared facts.

## Reference documents

| File | Read when you need to... |
|---|---|
| `docs/REPO_LAYOUT.md` | Find what a specific file or module is responsible for, and the load-bearing details that have caused regressions before |
| `docs/ARCHITECTURE.md` | Understand how the modules fit together, data flow, and design decisions |
| `docs/HOMEASSISTANT.md` | Work with HA-specific patterns: coordinators, entity classes, config flows, platforms |
| `docs/UNIFI.md` | Understand the UniFi API, auth methods, alarm payloads, and event key taxonomy |
| `docs/TESTING.md` | Run, write, or extend tests |
| `docs/DEVELOPING.md` | Set up a local dev environment, run tests, contribute changes |
| GitHub Issues | Find the outstanding-work backlog. Work is tracked in Issues (filter by milestone, sort by `priority:`, pick by `size:`), not in a file. `docs/TODO.md` is a pointer that documents the label and milestone taxonomy. Historical record lives in `docs/HISTORY.md`; per-release plan lives in `docs/ROADMAP.md`. |
| `docs/ROADMAP.md` | See what's planned next per release (v1.8.0, v1.9.0, v2.0.0). Open items only; completed releases are removed once they ship. |
| `docs/RELEASING.md` | Cut a release or bump a version: the two-branch model, version formats, the pre-release/stable/next-cycle workflow, the merge-commit-vs-squash rationale, the no-sync-merge note, tag-convention reminder, CI enforcement, and branch protection. |
| `AGENTS.md` | Agent-facing context file for Copilot and third-party AI tools. Includes repo structure map, category-registration walkthrough, and common pitfalls. |
| `docs/HISTORY.md` | Dated record of completed work, newest first. **Updated only at tag time** (pre-release or stable) by the version-bump PR, which adds one date block listing every PR merged since the previous tag. Format: `## YYYY-MM-DD` heading, bullets `- **category**: short description ([#PR] or [SHA]). Short why.` Categories: `feat`, `fix`, `security`, `docs`, `ci`, `chore`, `tests`, `release`. No WHO. No "bundle/cluster/track/session N" framing. PR backlinks via reference-style at the bottom of the file. |
| `CHANGELOG.md` | User-facing release summary in [common-changelog](https://common-changelog.org) format. Past tense, one line per change, references at the bottom. Update the `[Unreleased]` section as user-visible changes land. |
| `SECURITY.md` | Vulnerability disclosure policy. If a task touches security-relevant components, check the in-/out-of-scope listing here before responding to a security report. |

## Repository layout

Per-file annotations and load-bearing details live in [`docs/REPO_LAYOUT.md`](docs/REPO_LAYOUT.md). Read it when you need to know what a specific file does or owns; do not duplicate that detail here.

## Non-negotiable constraints

- **Python 3.14 only (matching the HA baseline).** Use modern type hints (`list[str]` not `List[str]`, `X | None` not `Optional[X]`). This includes [PEP 758](https://peps.python.org/pep-0758/) (accepted for 3.14): `except A, B:` (no parentheses, no `as`) is valid and is what the pinned `ruff format` (`target-version = "py314"`) canonicalises multi-type `except` clauses to. **Do not "fix" this to `except (A, B):`** - it is not Python 2 syntax leaking in, it is correct for this project's only supported interpreter. This exact mistake was made and reverted once already in [#328](https://github.com/PHeonix25/unifi_alerts/pull/328) ("the earlier parenthesisation was a mis-diagnosis made by compiling against Python 3.13, which predates PEP 758") and reproduced independently in [#329](https://github.com/PHeonix25/unifi_alerts/pull/329). If you cannot obtain a real Python 3.14 interpreter to verify a change (older interpreters give a false-positive `SyntaxError: multiple exception types must be parenthesized` on this syntax), say so explicitly and treat CI as authoritative for anything mypy/pytest-shaped rather than "fixing" code that predates your interpreter.
- **All I/O is async.** No blocking calls anywhere. Use `aiohttp` for HTTP, never `requests`.
- **No YAML configuration.** Everything goes through the config flow. Do not add `async_setup` or `configuration.yaml` support.
- **`iot_class: local_push`** must stay in `manifest.json` - this is accurate and affects HA's energy/performance classification.
- **`manifest.json` key order is enforced by hassfest** - keys must be: `domain`, `name`, then all remaining keys alphabetically. Violating this order breaks CI.
- **`manifest.json` `dependencies` must only list HA integrations installable by HACS** - do NOT list HA core built-ins (e.g. `webhook`, `http`, `frontend`). hassfest accepts them but the HACS validator rejects them, breaking CI. Re-verified in [#267](https://github.com/PHeonix25/unifi_alerts/issues/267): confirmed locally via `scripts/validate_hacs.py` (which mirrors the real HACS Action check). `after_dependencies` was considered as an alternative but rejected - it only orders setup relative to a component that is *already* being loaded, it does not force HA to load it, so it would not fix the underlying problem (the integration hard-depends on `webhook` being active). The runtime prerequisite is documented in the README `Requirements` section instead.
- **`DEFAULT_VERIFY_SSL = True`** - SSL verification is on by default; only disable for controllers with self-signed certificates. Never silently change this default.
- **Webhooks are `local_only: True`** - do not remove this without a documented reason.
- **Webhook bearer token auth is mandatory** - every inbound webhook request must be validated against `CONF_WEBHOOK_SECRET` via `?token=` query param. Never remove this check or accept requests that fail it.
- **Category state lives only in the coordinator** - entities must not cache state themselves.
- **Every GitHub Actions `uses:` reference must be pinned to a full 40-character commit SHA** - no branch names (`@main`, `@master`), no tag names (`@v2`, `@v6`), no short SHAs. Add a trailing comment noting the resolved version or branch for human readers (e.g. `# v3.0.0` or `# master tip 2026-04-22`). This applies to every workflow in `.github/workflows/`. When bumping an action, resolve the new SHA via `gh api repos/OWNER/REPO/git/refs/tags/TAG` (or `.../heads/BRANCH` for repos without tags) and replace both the SHA and its comment in the same edit. Dependabot (`.github/dependabot.yml`) proposes these bumps weekly - review the SHA against the upstream tag before merging.
- **The release pipeline uses `gh release create --generate-notes` only**: no third-party release actions. `softprops/action-gh-release` was deliberately removed in v1.4.0; do NOT re-introduce it (or any other third-party release publisher) when editing `.github/workflows/release.yml`. The GitHub CLI is pre-installed on `ubuntu-latest` runners. `actions/checkout` in that workflow MUST keep `fetch-depth: 0`; `--generate-notes` needs the full tag history to compute the previous-tag boundary.
- **`CHANGELOG.md` must be updated alongside notable user-visible changes, in the same PR that ships the change** (not retroactively, not at release time). Format follows [common-changelog](https://common-changelog.org): past tense, one line per change, references at the bottom. Append the bullet to `[Unreleased]` in the branch that ships the change; never edit released sections. When bumping the manifest from `X.Y.Z-preN` to a stable `X.Y.Z`, rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add a fresh empty `[Unreleased]` above it, and update the link references at the bottom. Pre-release version bumps (`-preN`) do NOT touch `CHANGELOG.md`. `docs/HISTORY.md` is the dated record (written at tag time, see release workflow); `CHANGELOG.md` is the user-facing release summary (accumulated per PR). **The `changelog-guard` CI check (`.github/workflows/pr-guards.yml`) enforces this mechanically** for `custom_components/` edits; apply the `skip-changelog` label to bypass it for changes with no user-visible effect.
- **Writing style for all docs**: no em-dashes (`-`, `:`, `;` instead), no unicode arrows (`>` for nav paths, `->` for flow), no marketing prose. Tight, factual, and self-contained. Avoid "bundle/cluster/track/session N" framing; describe WHAT changed and WHY, not how the work was bundled.
- **Use British/Australian English spelling in all prose** (markdown docs, code comments, docstrings, commit messages, PR descriptions, agent instruction files under `.github/agents/`, and user-facing strings in `strings.json`/`translations/en.json`): e.g. `colour`, `behaviour`, `organise`, `localise`, `recognise`, `licence` (noun). This does NOT extend to code identifiers, filenames, external API/protocol field names, or third-party tool config keys that happen to use American spelling (e.g. the `LICENSE` filename, the CSS `color` property, GitHub Actions' `labeled`/`unlabeled` event types, Codecov's `behavior:` config key, `gh label create --color`) - those must stay exactly as the external system requires, never "corrected".
- **PRs must carry one of the labels recognised by `.github/release.yml`** so auto-generated release notes group them correctly. Valid labels (after `scripts/setup-labels.sh` has been run on the fork): `security`, `bug` / `fix`, `enhancement` / `feat`, `documentation`, `tests`, `ci`, `github-actions`, `dependencies`. **The `pr-labeler.yml` workflow handles this automatically** for PRs whose title starts with a Conventional Commit prefix (`feat:`, `fix:`, `docs:`, `test:`/`tests:`, `ci:`, `security:`); it skips when a release-notes label is already applied, so manual overrides win. If you open a PR without a CC prefix or with a prefix the workflow does not map (`chore`, `build`, `refactor`, `perf`, `style`), apply the label by hand: `mcp__github__create_pull_request` does NOT accept a `labels` field, so use `mcp__github__issue_write` with `method: "update"`, `issue_number: <PR number>`, `labels: ["<label>"]`. **Unlabelled PRs silently fall through to "🧹 Other Changes" - this was the cause of the v1.4.0-pre2 release notes coming out flat.** Verify with `mcp__github__pull_request_read`/`get` - the response includes a `labels` field; if it's missing or empty, the categorisation will fail at release time. **The `label-guard` CI check (`.github/workflows/pr-guards.yml`) enforces this mechanically.**
- **`docs/HISTORY.md` must only change in version-bump PRs** (`claude/bump-*` branches). Feature and fix PRs must never touch it. **The `history-guard` CI check (`.github/workflows/pr-guards.yml`) enforces this mechanically.**

## Coding conventions

- Module-level `_LOGGER = logging.getLogger(__name__)` in every file that logs.
- `_attr_*` class attributes for HA entity properties - only override as `@property` if the value is dynamic.
- `_device_info()` is a module-level helper function (not a method) duplicated across platform files intentionally - keeps each platform self-contained.
- All `const.py` additions go in the appropriate labelled section with a comment.
- Tests use `MagicMock` / `AsyncMock` for the UniFi client - never make real HTTP calls in tests.

## Branching and releasing

Two-branch model: all active development happens on `dev`; `main` is stable-only. Feature and `claude/*` branches must be cut from `dev` and target `dev` in their PRs, never `main`. `dev` carries `X.Y.Z-preN` versions (or a stable `X.Y.Z` when preparing a release); `main` carries stable `X.Y.Z` only. `manifest.json` is the single source of truth for the version, and `scripts/bump_version.py` drives every bump.

**Claude cannot push tags.** When the user says "cut a release", "update the tag", "tag the branch", or similar, open a version-bump PR (via `scripts/bump_version.py`) targeting `dev` (or `main` for a stable release) and, after it merges, give the user the exact `git tag` + `git push origin <tag>` commands to run locally.

The full detail - the pre-release/stable/next-cycle workflow, the merge-commit-vs-squash rationale for the `dev > main` PR, the no-sync-merge note, CI enforcement, and branch protection - lives in [`docs/RELEASING.md`](docs/RELEASING.md). Read it when cutting a release.

## Working style

- **Never assume - always ask.** If anything about the task, scope, or approach is unclear, ask before proceeding. Do not guess intent.
- **Always pull `dev` before starting work** - run `git pull origin dev` at the start of every session to avoid diverging from origin. Never start implementing changes on a stale branch. Pull `main` only when checking stable state.
- **Work on `dev`, not `main`** - `main` is only updated via PRs from `dev`. Never commit directly to `main`.
- **Feature and claude/* branches must be created from `dev`** - run `git checkout dev && git pull origin dev && git checkout -b <branch>`. Never branch off `main`. PRs from feature branches must target `dev`, not `main`.
- **When a branch maps to a GitHub Issue, create it via `gh issue develop`, not `git checkout -b`.** This registers a first-class link between the issue and the branch in GitHub's "Development" panel, which propagates to any PR opened from that branch. Without it, the `Closes #NN` keyword in the PR body is purely cosmetic until the change reaches `main`, because GitHub's keyword auto-linking only fires on PRs that target the repository's default branch (`main` here) - and our PRs target `dev`. Use: `gh issue develop <NN> --base dev --branch-name claude/issue-<NN>-<slug> --checkout`. Then proceed normally (edits, commits, `gh pr create --base dev`). The opened PR will appear in the issue's sidebar immediately, and `Closes #NN` will still close the issue at the eventual `dev > main` release-merge.
- **Always start fresh from `dev` for new work.** At the very start of a new task, even if a branch is already specified by the system instructions, run `git checkout dev && git pull origin dev` first, then create or recreate the working branch from that fresh `dev` tip. Never inherit whatever branch the previous session left checked out - it may be a stale `claude/bump-*` or other already-merged branch, and committing on top of it produces a branch that contains commits already in `dev`.
- **After a PR merges, delete the local branch and switch back to `dev`** - run `git checkout dev && git pull origin dev && git branch -D <merged-branch>`. This forces the next task to branch off a clean `dev` instead of accidentally building on a stale, already-merged branch.
- **Move into the working directory at the start of every session** - avoids needing path prefixes on every command.
- Always run `make check` before committing - never commit broken code. `make check` runs lint, typecheck, HACS preflight, translation drift check, and the full test suite in one shot.
- Update `docs/HISTORY.md` **only in the version-bump PR** (pre-release or stable), not on every PR. The bump PR adds a single `## YYYY-MM-DD` block (newest first) summarising every PR merged since the previous tag, plus the corresponding `[#PR]` reference links at the bottom. Format: `- **category**: short description ([#PR]). Short why.` Categories: `feat`, `fix`, `security`, `docs`, `ci`, `chore`, `tests`, `release`. No WHO, no multi-paragraph stories, no "bundle/cluster/session" framing. Feature/fix PRs do not touch HISTORY at all.
- **Outstanding work lives in GitHub Issues, not in a file.** Close an item by landing a PR that references it (`Closes #NN` in the PR body); never track completion by deleting prose. Because our PRs target `dev`, not the default branch `main`, that keyword does NOT fire at merge time (see the branching bullet above): the issue stays open until the change reaches `main` at release. So the moment a PR resolving an issue merges to `dev`, apply the **`landed-in-dev`** label to that issue. This keeps the milestone view honest, distinguishing "done, shipped to `dev`, awaiting the next stable release" from genuinely not-started work. The label is created once per fork by `scripts/setup-labels.sh`. **When reporting outstanding work for a milestone, exclude it:** query `is:open milestone:vX.Y.Z -label:landed-in-dev`, never the bare `is:open milestone:vX.Y.Z` (which lists already-shipped items as if untouched). The eventual `dev > main` release-merge closes the issue via the original `Closes #NN`. File new work with the **Task** template (or Bug / Feature where they fit) and apply a category label, a `size:` label, a `priority:` label, and the target milestone (taxonomy documented in `docs/TODO.md`). `scripts/seed_issues.py` is the idempotent bulk-seeder. When asked to "pick up issue #NN" or "the next one in the `vX.Y.Z` milestone", read the issue, create the branch with `gh issue develop <NN> --base dev --branch-name claude/issue-<NN>-<slug> --checkout` (see the branching bullet above for why), do the work, and close the issue via the PR. Tick or remove items from `docs/ROADMAP.md` in the same PR that ships them, not at release time; once a release ships, drop its section from ROADMAP entirely. The historical record belongs in `docs/HISTORY.md`. Do not rely on memory or Git history alone.
- At the end of the day, make sure there are no commits outstanding and no changes locally that need to be pushed (`git status` shows a clean tree). This ensures a clean slate for the next session.

## Resuming an interrupted session

Interruptions (timeouts, hibernation, re-login) are common. When a new conversation starts mid-task, always do this before anything else:

1. **Read `docs/HISTORY.md`** - the last entry describes what was most recently completed.
2. **Run `git status` and `git diff HEAD`** - uncommitted changes show exactly what was in-flight.
3. **Check the open GitHub Issues** for the active milestone (highest `priority:` first) - that is the likely in-flight work. `docs/TODO.md` describes the taxonomy.
4. **If a version-bump PR is in flight, audit its HISTORY block** - run `git log <prev-tag>..HEAD --merges --oneline` and confirm every merge appears in the new `docs/HISTORY.md` date block. Missing entries are the most common gap left by an interrupted release-prep session. Feature/fix PRs do NOT need HISTORY entries (HISTORY is written at tag time only); skip this step unless a `claude/bump-*` branch is active.
5. **Check the venv** - on Linux/Mac: `ls .venv/bin/pytest`; on Windows PowerShell: `Test-Path .venv\Scripts\pytest.exe`. If missing, recreate it:
   - **Linux/Mac:** `make setup` (or manually: `python3.14 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt --quiet`)
   - **Windows:** `py -3.14 -m venv .venv && .venv\Scripts\pip install -r requirements-dev.txt --quiet`
6. **Resume from where the diff left off** - do not re-do already-applied changes. Pick up at the next pending step (usually: run tests, fix lint, commit).

## Before making changes

1. Check the open GitHub Issues for context on what's known to be incomplete or broken.
2. Run `make check` to run all local validation in one shot:
   - ruff lint + format check
   - mypy type check
   - HACS manifest pre-flight (`scripts/validate_hacs.py`)
   - strings.json ↔ translations/en.json drift check
   - full pytest suite
3. Individual targets: `make lint`, `make typecheck`, `make validate`, `make test`. Run `make help` for the full list.
4. All commands use the `.venv` in the repo root - never the system Python. Use `make setup-lint` instead of `make setup` when you only need ruff and mypy (skips the ~200-package Home Assistant install).

## Doc-only PRs (lighter path)

If a PR only touches `*.md`, `docs/**`, `CHANGELOG.md`, `CLAUDE.md`, `README.md`, or `SECURITY.md`, skip the full `make check` cycle:

1. Run `make doc-check`. This runs `scripts/validate_docs.py` (prose linter, HISTORY h2 format) plus the `strings.json` / `translations/en.json` drift check. No venv required for either step.
2. `python3 scripts/validate_docs.py` works standalone if you do not even want to use `make`. It is pure stdlib.
3. Skip `make setup` for a doc-only branch on a fresh clone. The full setup installs Home Assistant and ~200 packages just to give you `pytest`/`ruff`/`mypy`, none of which inspect docs.
4. CI still runs the full suite on push. Treat that as the safety net rather than a local gate.

For Claude specifically: do not invoke plan-mode or Explore agents for prose-only edits. `grep -n` to locate the section, `Read` with `offset`/`limit` to load just the lines being changed, then `Edit`. Reading whole files "to be safe" is the most common token waste; `Edit` already errors if the file changed underneath you.

## Pre-push hook (install once per clone)

A git hook at `.githooks/pre-push` runs all of the above automatically before every `git push`. Activate it once after cloning:

```bash
git config core.hooksPath .githooks
```

If the hook is not installed, run `scripts/validate_hacs.py` manually before every push that touches `manifest.json` or `hacs.json`.
