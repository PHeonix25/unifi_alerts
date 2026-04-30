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
  "tests|bfdadc|Test changes (additions, refactors, fixtures)"
  "ci|ededed|Continuous-integration / build / release-pipeline changes"
  "github-actions|000000|Changes to GitHub Actions workflows or pinned-action bumps (Dependabot)"
  "dependencies|0366d6|Dependency bumps (Dependabot auto-applies this)"
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
