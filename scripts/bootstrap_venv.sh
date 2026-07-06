#!/bin/sh
# SessionStart bootstrap for unifi_alerts.
#
# Creates the .venv dev environment (Home Assistant + full test stack) when it
# is missing, so a fresh remote agent session can run `make test` without any
# manual setup step. It mirrors what .github/workflows/copilot-setup-steps.yml
# does for the Copilot coding agent, keeping every agent surface on the same
# environment.
#
# Design guarantees:
#   * No-op when .venv already exists (local devs and cached remote containers).
#   * Non-blocking: wired as an async SessionStart hook, so the session starts
#     immediately and this install runs in the background.
#   * Tolerant: a failed install never aborts the session; failures are logged
#     and the script exits 0 so Claude can still lint and inspect the tree.
#   * Remote-only: gated on $CLAUDE_CODE_REMOTE so local sessions keep their
#     existing behaviour (a local dev runs `make setup` deliberately).
#   * POSIX sh, cross-platform-safe (checks both bin/ and Scripts/ layouts).
set -u

# Emit the async directive first so Claude Code starts the session immediately
# and runs the rest of this script in the background.
printf '{"async": true, "asyncTimeout": 600000}\n'

# Only bootstrap in a remote agent container. Local developers set up their
# venv on their own terms and should not have a ~200-package install kicked off
# behind their back.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# No-op when a usable venv already exists. Cover both the Unix (bin/) and
# Windows (Scripts/) venv layouts.
if [ -x ".venv/bin/pytest" ] || [ -x ".venv/Scripts/pytest.exe" ]; then
  echo "[bootstrap] .venv already present; skipping setup." >&2
  exit 0
fi

echo "[bootstrap] .venv missing; running 'make setup' (Home Assistant + test stack)." >&2

# Tolerant install: a failure must not abort the session. Log and exit 0 either
# way so the session stays usable for lint-only or read-only work.
if make setup >&2 2>&1; then
  echo "[bootstrap] setup complete; 'make test' is now available." >&2
else
  echo "[bootstrap] setup failed; run 'make setup' manually. Session continues." >&2
fi

exit 0
