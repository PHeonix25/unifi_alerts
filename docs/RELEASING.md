# Releasing - unifi_alerts

Branching model, version formats, and the full release workflow. `CLAUDE.md` keeps only a short two-branch summary and points here; read this document when cutting a release or bumping a version.

## Branching strategy and versioning

This project uses a two-branch model. All active development happens on `dev`; `main` is stable-only.

### Branches

| Branch | Purpose | Version format | Example |
|--------|---------|---------------|---------|
| `main` | Stable releases only. CI enforces no pre-release suffix. | `X.Y.Z` | `1.0.0`, `1.1.0` |
| `dev` | Active development. CI accepts `-preN` during development, or stable `X.Y.Z` when preparing a release. | `X.Y.Z-preN` or `X.Y.Z` | `1.1.0-pre1`, `1.1.0` |
| `feature/*` or `claude/*` | Short-lived work. **Must branch off `dev`, not `main`.** No version format enforced by CI. | Any | - |

### Versioning conventions

- **Minor bumps on main:** releases from `main` increment the minor version (`1.0.0 > 1.1.0 > 1.2.0`). Patch releases (`1.0.1`) are reserved for critical hotfixes.
- **Pre-release sequence on dev:** each tagged checkpoint on `dev` increments the pre-release counter (`1.1.0-pre1 > 1.1.0-pre2`). The base version (`1.1.0`) matches the *next* planned minor release on `main`.
- **`manifest.json` is the single source of truth** for the version - the release workflow validates the pushed tag matches it exactly.

### Release workflow

```
dev  ──┬── (work) ──► tag v1.1.0-pre1  ──► GitHub pre-release  (automated)
       │
       ├── (work) ──► tag v1.1.0-pre2  ──► GitHub pre-release  (automated)
       │
       ├── bump manifest to 1.1.0 (via claude/* PR > dev)
       │    └─► PR dev > main  [MERGE COMMIT - never squash]
       │         └─► tag v1.1.0  ──► GitHub stable release  (automated)
       │
       └── bump manifest to 1.2.0-pre1 (via claude/* PR > dev)  (start next cycle)
```

**Use `scripts/bump_version.py` for steps 2, 3, and 4 below.** It computes the next version per these rules, checks out a fresh `dev`, creates the `claude/bump-<new-version>` branch, updates `manifest.json` (and `CHANGELOG.md` for stable promotions), stages the change, and prints the `git log <prev-tag>..HEAD --merges` list ready to summarise into `docs/HISTORY.md`. Modes: `--pre`, `--stable`, `--next-cycle`.

1. **Development:** work on `dev`. Version in manifest stays at `X.Y.Z-preN`.
2. **Pre-release checkpoint:** run `python3 scripts/bump_version.py --pre` to bump the `N` in manifest (e.g. `pre1 > pre2`) on a short-lived `claude/bump-*` branch, then open a PR targeting `dev`, merge it, and provide the user with the tag command (Claude cannot push tags). **In the same PR, write the HISTORY block** for this tag: the script prints the merge list since the previous tag; summarise it into a single `## YYYY-MM-DD` block in `docs/HISTORY.md` (newest first). **Drop completed items** from `docs/ROADMAP.md` for the section this tag advances. `CHANGELOG.md` is NOT touched on pre-release bumps. After the PR merges, the user runs:
   ```bash
   git checkout dev && git pull origin dev
   git tag vX.Y.Z-preN && git push origin vX.Y.Z-preN
   ```
   GitHub Actions creates a pre-release automatically.
3. **Stable release:** run `python3 scripts/bump_version.py --stable` to bump manifest from `X.Y.Z-preN` to `X.Y.Z` and rewrite `CHANGELOG.md` (rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, insert a fresh `[Unreleased]` above it, add the `[X.Y.Z]: .../releases/tag/vX.Y.Z` link reference). Open PR targeting `dev`. **In the same PR, write the HISTORY block** covering every PR merged since the previous tag (the most recent pre-release). `dev` CI now accepts stable versions, so this passes. Merge to `dev`, then open a PR from `dev` > `main`. After that merges, provide the user with the tag command:
   ```bash
   git checkout main && git pull origin main
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```
   GitHub Actions creates a stable release automatically; the auto-generated notes are grouped by the labels on PRs merged between the previous tag and this one.

   > **CRITICAL - use "Create a merge commit", never "Squash and merge", for the `dev > main` PR.** Squashing creates a new commit on `main` whose only parent is the previous `main` tip; dev's individual commits have no ancestry path through it. The merge base between `main` and `dev` never advances past the last stable release, so the next release produces a conflict storm across every file that both branches touched. A regular merge commit preserves both parents and keeps the merge base current. The `main` ruleset is configured to enforce merge-commit-only.

   > **No `main > dev` sync merge needed.** Earlier releases (v1.3.0, v1.4.0) ran a `claude/sync-main-to-dev-X.Y.Z` PR after every stable release because the `dev > main` PR was squash-merged, which left the release commit out of dev's ancestry. With merge-commit-only on `main` (above), dev's tip is already the second parent of the release commit; the merge base advances correctly and no sync is required. Attempting one now contradicts the squash-only-on-dev ruleset.

4. **Start next cycle:** run `python3 scripts/bump_version.py --next-cycle` to bump manifest to `X.(Y+1).0-pre1` on a `claude/bump-*` branch, open PR targeting `dev`, merge. Development continues forward. Notable changes between releases accumulate under `CHANGELOG.md` `[Unreleased]` as their PRs land - don't batch them at release time.

> **Tag convention reminder:** Claude cannot push tags directly. Whenever the user says "update the tag", "cut a release", "tag the branch", or similar - open a version-bump PR to `dev` (or `main` for stable), wait for merge, then give the user the exact `git tag` + `git push origin <tag>` commands to run locally.

### CI enforcement

- `version-check.yml` blocks pushes and PRs that violate the format for the target branch.
- `release.yml` fails if the pushed tag does not exactly match `manifest.json`.
- Never manually create a GitHub release - always push a version tag and let the workflow do it.

### Branch protection (configure once in GitHub Settings > Branches)

Recommended rules:
- **`main`:** require PR, require status checks (`CI / *`, `Version Check / *`), no direct push, no force-push.
- **`dev`:** require PR, require status checks (`CI / *`, `Version Check / *`), no direct push, no force-push. Version bumps go via a short-lived `claude/bump-*` branch PR (created by `scripts/bump_version.py`).
