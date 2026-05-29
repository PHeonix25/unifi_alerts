# TODO

Outstanding work is tracked in **GitHub Issues**, not in this file. This page is a pointer and a description of how the tracker is organised.

- Open backlog: <https://github.com/PHeonix25/unifi_alerts/issues>
- Per-release plan and themes: `docs/ROADMAP.md`
- Completed work: `docs/HISTORY.md` (written at tag time)

## How the tracker is organised

Each issue carries a **milestone**, a **category** label, a **size** label, and a **priority** label. Pick work by filtering on the milestone and sorting by priority, then by the size that fits the time you have.

| Dimension | Values | Notes |
| --- | --- | --- |
| Milestone | `v1.8.0`, `v1.9.0`, `v2.0.0` | The release the item is planned for. |
| Category | `security`, `fix`, `feat`, `enhancement`, `tests`, `ci`, `documentation`, `github-actions`, `dependencies` | Mirrors `.github/release.yml` so release notes group correctly. |
| Size | `size: S`, `size: M`, `size: L` | Rough effort and review-time guide. |
| Priority | `priority: high`, `priority: medium`, `priority: low` | Order within a milestone. |
| Gate | `v2.0-gate` | Prerequisite for the HACS default submission; lives in an earlier milestone. |

## Filing and closing work

- File new work with the **Task** issue template (or Bug / Feature where they fit). Apply a category, `size`, and `priority` label and assign a milestone.
- Close items by landing a PR that references the issue (`Closes #NN`); do not delete lines here.
- The seed/migration tool is `scripts/seed_issues.py` (idempotent; re-run to add new backlog items in bulk).

## Known issues: intentional, do not action

- **`_device_info()` duplication**: duplicated identically across `binary_sensor.py`, `sensor.py`, `event.py`, `button.py`. Intentional for platform isolation; extract to a shared `entity_base.py` only if it becomes a maintenance burden. Not tracked as an issue on purpose.
