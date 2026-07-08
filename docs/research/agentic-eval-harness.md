# Agentic evaluation harness and repo quality score

Investigation for [#287](https://github.com/PHeonix25/unifi_alerts/issues/287): what to do with
`agentrc.eval.json`, and whether to grow it into a cross-model evaluation harness feeding an
advisory repo quality score in CI. This is a design note, not a changelog entry - it records the
recommendation and the phased plan. Update it as phases land or the plan changes.

## Where things stand

`agentrc.eval.json` holds five planning-evaluation cases: a realistic task prompt plus the
expectations a good implementation plan must meet (files touched, constants added, tests
updated). Nothing runs it. It had drifted twice: once before #287 was filed (`apply_alert()` vs
`push_alert()`, `test_config_flow.py` vs `tests/unit/config_flow/`), and again during this
investigation, when `tests/unit/test_coordinator.py` was split into `tests/unit/coordinator/*.py`
and `tests/unit/config_flow/test_options.py` was split into three files - the exact kind of rot
#287 predicted. Phase 0 below (already implemented on this branch) fixes the second drift and
adds a mechanical guard against a third.

Case-1 also has a **semantic** staleness problem a path guard cannot catch: it asks for webhook/poll
dedup keyed on `CategoryState`, but dedup already shipped (`coordinator.py`'s `_last_push_at` dict,
keyed on `(category, alert.key)`, not a `CategoryState` field) via #263. The case's proposed design
no longer matches the codebase it's supposed to be evaluated against. That needs a content review,
not a script - see Phase 1.

## Q1: Is Microsoft AgentRC the right foundation?

`agentrc.eval.json` is not just a filename inspired by AgentRC - it is the literal artifact name
[microsoft/agentrc](https://github.com/microsoft/agentrc) generates. AgentRC is a CLI + VS Code
extension that reads a repo and produces `.github/copilot-instructions.md`, `.vscode/mcp.json`,
`.vscode/settings.json`, and `agentrc.eval.json` ("test cases to measure instruction quality"), then
re-generates them on a "Measure, Generate, Maintain" cycle. This repo has the fourth artifact but
never adopted the tool that maintains it - which is exactly how it rotted.

Recommendation: **don't adopt the AgentRC CLI**. Its own README says "expect breaking changes";
taking a dependency on an experimental Microsoft tool to auto-regenerate a config file conflicts
with the repo's pure-stdlib, minimal-dependency preference, and there's no published schema
guaranteeing `agentrc.eval.json`'s shape is stable across AgentRC versions. Keep the filename
(it costs nothing and signals lineage) but treat the JSON shape as *this repo's own contract* -
version it like any other file in `custom_components/`, and let `scripts/check_agentrc_refs.py`
(and, in later phases, the harness itself) be the only things that depend on its structure.

## Q2: Alternatives evaluated

| Option | What it is | Maturity | Fit here | Lock-in |
| --- | --- | --- | --- | --- |
| **microsoft/agentrc** | CLI that generates + measures agent instruction files | Experimental, "expect breaking changes" | Low - we'd be adopting a moving target to maintain one JSON file | Medium - proprietary schema, Microsoft roadmap |
| **githubnext/agentics** | Sample pack of workflows built on gh-aw (issue triage, CI doctor, repo assist) | Research demonstrator from GitHub Next, actively developed | Low for our narrow need - these are general repo-maintenance bots, not a plan-scoring harness | High - built specifically for gh-aw's frontmatter format |
| **GitHub Agentic Workflows (gh-aw)** | `gh` CLI extension: author agents as Markdown + YAML frontmatter, compiled to a `.lock.yml` GitHub Actions workflow | Public Preview as of June 2026 ("may change significantly") | Medium - genuinely well-engineered for *running* agents in CI (auto SHA-pins actions, runs actionlint/zizmor/poutine, sandboxes the agent behind an egress firewall), but it's a new authoring format, a new CLI dependency, and a new artifact type (`.lock.yml`) layered on top of the workflows we already hand-write | High - Markdown-frontmatter DSL, compiled output, GitHub-specific |
| **Native GitHub (Actions + GitHub Models)** | Plain workflow calling the GitHub Models inference API with `GITHUB_TOKEN` (`models: read` scope, free tier) | Stable, no extra CLI | High - it's just an HTTP call from a workflow step, no new DSL, keeps the repo's existing "hand-written YAML, SHA-pinned" convention | Low - swappable for any HTTP-based model API |

Recommendation: **build the harness as a plain Python script under `scripts/`, called from a
hand-written, SHA-pinned GitHub Actions workflow, calling model APIs directly over HTTP** (GitHub
Models for the free/default path, direct Anthropic/OpenAI-compatible endpoints when cross-model
comparison needs a specific model). Revisit gh-aw once it's stable (out of Public Preview) if the
maintainer wants the sandboxing/threat-detection machinery for *other* repo-maintenance workflows
- but don't take it on just to run five plan-grading cases. This keeps the harness a small,
auditable stdlib script that fits the repo's existing testing and CI conventions rather than a new
subsystem to learn and pin.

One security note worth carrying forward regardless of which path is chosen: gh-aw's own public
preview had a disclosed "GitLost" issue where crafted issue/PR content could influence an agent
with write access into leaking private data - the general lesson (treat issue/PR/comment text as
untrusted input to any agent that has repo write scope or secrets in its context) applies whether
or not we use gh-aw. The harness in this proposal only ever *reads* the repo and a fixed local
`agentrc.eval.json`; it never ingests live issue/PR content, so this class of injection risk does
not apply to it as scoped. If a future phase feeds it real PR diffs or issue text, revisit this.

## Q3: Best practice for evaluating AI-generated plans / LLM-as-judge

- **Prefer binary/discrete checks over free-form numeric scores.** Research (e.g. the 2026
  "Reliability without Validity" study) shows numeric LLM scores are unstable across runs and
  temperature settings; binary or small-categorical rubric items are more reproducible. Each
  `agentrc.eval.json` case's `expectation` should be split into a checklist of yes/no criteria
  ("does the plan name `coordinator.py` as the dedup site?", "does it call out the
  `strings.json`/`translations/en.json` drift check?") rather than judged as one blob scored 1-10.
- **Run at temperature 0 (or the provider's deterministic-est setting) and expect residual
  flakiness anyway.** Same-verdict rates drop sharply as temperature rises; even at 0, do not
  gate CI on a single run - see below.
- **Judge validity is a separate concern from judge consistency.** A judge can be perfectly
  repeatable and still systematically wrong (position bias, length bias, favouring
  authoritative-sounding prose). Mitigate with a fixed rubric per case (already half-present in
  `expectation` text), and treat the *harness's* own scoring as needing periodic human spot-checks,
  not as ground truth.
- **Cost/reproducibility implication:** run each case 1x per model in CI (advisory, cheap), but
  when validating the harness itself (not routine PR runs), run it 3-5x and require majority
  agreement before trusting a single case's score - that's a local/manual activity, not something
  to bake into every PR's CI cost.
- **The eval file's own premise can go stale** (case-1, above) - no amount of judge reliability
  work fixes a case that's grading against a design the codebase no longer has. Content review has
  to stay a manual, PR-time responsibility (AGENTS.md already asks contributors to update case text
  when they rename referenced symbols/files); the harness can only catch mechanical drift.

## Q4: What should a "quality score" measure, and how to show it without noise

Recommend a **composite, not a single opaque number**, reported as a short table rather than one
digit:

| Signal | Source | Blocking today? |
| --- | --- | --- |
| Guard pass-rate (changelog/label/history/agentrc-refs/translations) | Already-existing CI jobs | Yes (existing) |
| Coverage % | `pytest --cov-fail-under=95` | Yes (existing) |
| Plan-eval checklist pass-rate | New: harness scoring `agentrc.eval.json` cases | No - advisory only |
| Cross-model agreement | New: variance across models on the same cases | No - advisory only |

Presentation: a PR comment (updated in place, not re-posted) summarising checklist pass-rate per
case and flagging disagreement between models, plus a workflow summary (`$GITHUB_STEP_SUMMARY`)
table for anyone who wants the detail. Do **not** add a required status check or branch-protection
gate until the harness has run advisory-only for long enough to trust its false-positive rate -
mirrors how `pr-guards.yml` checks started as mechanical, narrowly-scoped, deterministic checks
before anyone considered making them required. An LLM-judged score is not narrowly-scoped or
deterministic in the same way, so it earns "advisory" status for longer, possibly permanently.

## Q5: Cross-model validation

- **Default/cheap path:** GitHub Models via the workflow's own `GITHUB_TOKEN` (`models: read`
  scope is available with no extra secret). Free tier is rate-limited (roughly 10 RPM, tens to
  ~150 RPD depending on model tier) - fine for 5 cases run occasionally, not for running on every
  PR against multiple models.
- **Named-model path (Claude Opus 4.8 / Sonnet 5 / Haiku 4.5 / Fable 5, and any non-Anthropic
  model the maintainer wants in the comparison):** one repo secret per provider
  (`ANTHROPIC_API_KEY`, etc.), injected only into the harness job, never logged. Keep the model
  list in a small config (JSON or a constants module under `scripts/`) so adding/removing a model
  from the comparison is a one-line change, not a workflow edit.
- **Cost control:** cap to a manual/scheduled trigger (`workflow_dispatch` + a low-frequency
  `schedule`, e.g. weekly) rather than running cross-model comparison on every push - 5 cases x N
  models x cost-per-call adds up fast if it runs on every PR. A cheap single-model pass-rate check
  can run on every PR later; the multi-model comparison should not.
- **Rate limits / flakiness:** treat a provider timeout or rate-limit response as "skip, don't
  fail" for that model in that run - a single provider's outage should not block the advisory
  score or make the job itself flaky-red.

## Phased plan

**Phase 0 - mechanical reference guard (done on this branch).**
`scripts/check_agentrc_refs.py` extracts backtick-quoted file paths from each case's `prompt` and
`expectation` text and confirms they resolve to a real file in the tree. Wired into
`make doc-check`, `make validate`, and the `hacs-preflight` CI job. Deliberately does not check
bare symbol/constant names (several cases name constants a plan is expected to *add*, e.g.
`CONF_DEDUP_WINDOW` - a naive existence check would false-positive on those) or judge semantic
accuracy (see case-1 above). Fixed the drifted references found during this investigation
(`test_coordinator.py`, `tests/unit/config_flow/test_options.py`, `test_unifi_client.py`) in the
same PR that introduces the guard, matching AGENTS.md's existing "update case text in the same
PR" rule.

**Phase 1 - local single-model harness.** A `scripts/run_agentrc_eval.py` that: loads
`agentrc.eval.json`, sends each `prompt` (plus `CLAUDE.md`/`AGENTS.md` context) to one model in
plan-only mode (no repo write access), and grades the response against a checklist derived from
`expectation` (see Q3 - binary criteria, not a single score). Runs locally / on `workflow_dispatch`
only, never blocking. Output: a per-case pass/fail table plus the raw plan text for manual review.
This phase also forces the semantic-staleness question for case-1 - fixing the case content
belongs here, not in phase 0.

**Phase 2 - cross-model validation.** Extend phase 1 to loop over a configured model list
(GitHub Models for the default/free path, named-model secrets for Claude/others), run each case
per model, and report agreement/disagreement. Scheduled (e.g. weekly), not per-PR, per the cost
argument in Q5.

**Phase 3 - advisory CI quality score.** Wire a cheap single-model pass-rate check into PR CI
(non-blocking, PR-comment + step-summary output only, per Q4's composite table). Only after
phase 1/2 have run long enough locally/on schedule to establish the harness's own false-positive
rate. No branch-protection requirement without an explicit follow-up decision.

## Risks / open questions

- **LLM-judge cost creep.** Even "advisory" CI can quietly become expensive if scope grows past
  5 cases or per-PR triggering happens by accident. Keep phase 3 scheduled/opt-in until proven
  cheap.
- **Model drift.** A case that passes today may fail after a model version bump with no code
  change on our side - the harness needs to tolerate (and report, not alarm on) that rather than
  reading it as a regression.
- **Secret sprawl.** Each named model in Q5 is a new repo secret; needs a documented rotation/removal
  process before phase 2, not after.
- **Who maintains the rubric?** Splitting `expectation` prose into binary checklist items (Q3) is
  manual, human work per case. This doesn't scale automatically as more cases are added - worth
  deciding in phase 1 whether checklist authoring is part of "add a case" going forward.
- **gh-aw re-evaluation trigger.** If GitHub Agentic Workflows exits Public Preview and the
  maintainer wants sandboxed general-purpose repo-maintenance agents (issue triage, CI doctor)
  for reasons beyond this harness, that's a separate decision from this one - don't let "we
  already use gh-aw for X" become the reason to migrate this narrow harness onto it.

## Suggested follow-up issues

1. **Phase 1: local single-model plan-eval harness** (`scripts/run_agentrc_eval.py` + checklist
   rubric derived from each case's `expectation`; fix case-1's stale dedup premise in the same PR).
2. **Phase 2: cross-model comparison** (model list config, GitHub Models default path, named-model
   secrets, scheduled `workflow_dispatch`/weekly trigger, skip-not-fail on provider errors).
3. **Phase 3: advisory quality-score CI job** (PR comment + step-summary composite table per Q4;
   explicitly non-blocking; revisit branch-protection only as a separate, later decision).
4. **Rubric-authoring convention** for `agentrc.eval.json` - document (in AGENTS.md, alongside the
   existing "update case text in the same PR" rule) that new cases must ship with a binary
   checklist, not prose alone.
