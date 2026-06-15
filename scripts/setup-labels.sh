#!/usr/bin/env bash
# Create the labels referenced in `.github/release.yml` so `gh release
# create --generate-notes` actually groups merged PRs into the right
# sections. Without these, every PR falls through to the wildcard `*`
# rule and ends up under "🧹 Other Changes".
#
# Idempotent: existing labels are skipped, never overwritten. Run once
# per fork.
#
# Usage:   ./scripts/setup-labels.sh
# Requires:  gh CLI authenticated against this repo
set -euo pipefail

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)

# (name|color|description) — keep in lockstep with .github/release.yml
LABELS=(
  "security|b60205|Security-related changes (vulnerabilities, hardening)"
  "feat|a2eeef|Conventional Commits alias for enhancement (new feature or capability)"
  "fix|d73a4a|Conventional Commits alias for bug (bug fix)"
  "tests|bfdadc|Test changes (additions, refactors, fixtures)"
  "ci|ededed|Continuous-integration / build / release-pipeline changes"
  "github-actions|000000|Changes to GitHub Actions workflows or pinned-action bumps (Dependabot)"
  "dependencies|0366d6|Dependency bumps (Dependabot auto-applies this)"
)

# Process labels: NOT referenced by `.github/release.yml`. These track
# workflow state, not release-note grouping. `landed-in-dev` marks an issue
# whose fix has merged to `dev` but not yet shipped to `main`. Our PRs target
# `dev`, so `Closes #NN` does not fire until the `dev > main` release-merge;
# this label keeps the milestone view honest in the meantime. Apply it when a
# PR resolving the issue merges to `dev`; the release-merge then closes it.
#
# `skip-changelog` opts a PR out of the changelog-guard check in
# `pr-guards.yml`. Use it for custom_components/ changes that are internal
# refactors with no user-visible effect and therefore do not warrant a
# CHANGELOG entry (e.g. test-only changes that touch production code,
# or coverage-only commits).
LABELS+=(
  "landed-in-dev|0e8a16|Fix merged to dev, awaiting the next stable release on main"
  "skip-changelog|e4e669|Exempt from the CHANGELOG guard (no user-visible effect)"
)

# Cache the existing labels once so we don't hit the API per name.
existing=$(gh label list --repo "$REPO" --limit 200 --json name -q '.[].name')

for entry in "${LABELS[@]}"; do
  IFS='|' read -r name color description <<< "$entry"
  if grep -qxF "$name" <<< "$existing"; then
    printf "  skip  %s (already exists)\n" "$name"
  else
    gh label create "$name" \
      --color "$color" \
      --description "$description" \
      --repo "$REPO"
    printf "  ok    %s\n" "$name"
  fi
done

cat <<EOF

Labels are now in place. The release workflow will use them on the next
\`gh release create --generate-notes\` run, scoped between the previous
tag and the new one.

If you have already-merged PRs that landed unlabeled (and would
otherwise fall through to "🧹 Other Changes"), apply the right label
retroactively with:

  gh pr edit <NUMBER> --add-label <label> --repo $REPO

EOF
