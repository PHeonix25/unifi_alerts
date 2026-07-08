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

Case-1 also had a **semantic** staleness problem a path guard cannot catch: it asked for webhook/poll
dedup keyed on `CategoryState`, but dedup had already shipped (`coordinator.py`'s `_last_push_at`
dict, keyed on `(category, alert.key)`, not a `CategoryState` field, and webhook-only - polling
never touches `alert_count`) via #263. The case's proposed design no longer matched the codebase it
was supposed to be evaluated against. Fixed in Phase 1 (below): case-1 now asks for a currently-true
gap (the dedup window is a single fixed constant, not configurable per category) instead of a
scenario that no longer applies.

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
| **Native GitHub (Actions + GitHub Models)** | Plain workflow calling the GitHub Models inference API with `GITHUB_TOKEN` (`models: read` scope, free tier) | **Retiring 2026-07-30** (announced after this row was written - closed to new customers June 2026; see the risk entry below) | High while it lasted - it's just an HTTP call from a workflow step, no new DSL, keeps the repo's existing "hand-written YAML, SHA-pinned" convention. The *pattern* (plain HTTP call, no SDK) outlives the specific service - `ModelClient` in `scripts/run_agentrc_eval.py` works against any OpenAI-chat-completions-compatible endpoint, not just this one | Low - swappable for any HTTP-based model API, which is exactly what has to happen now |

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
  PR against multiple models. **Superseded: GitHub Models retires 2026-07-30** (see the risk entry
  below) - this stops being available at all, not just rate-limited, within weeks of this being
  written. Kept here as the historical rationale for the original design; a replacement default
  hasn't been chosen yet.
- **Named-model path (Claude Opus 4.8 / Sonnet 5 / Haiku 4.5, and any non-Anthropic
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

**Phase 1 - local single-model harness (done).** `scripts/run_agentrc_eval.py`: loads
`agentrc.eval.json`, sends each `prompt` (plus the file named in the eval file's `instructionFile`
field, currently `CLAUDE.md`) to one model as a single chat completion in plan-only mode (no tool
access, so it cannot touch the repo either way), then asks the same model to grade the plan against
that case's new `checklist` array as independent binary criteria (see Q3 - pass/fail per item, not
one aggregate score). Writes each case's raw plan and verdicts to `.agentrc-eval-out/<case-id>.md`
for manual review, and prints/appends a per-case pass-rate summary table
(`$GITHUB_STEP_SUMMARY` when running in Actions). Pure stdlib (`urllib` for the HTTP call - no SDK
dependency). Defaults to GitHub Models via the ambient `GITHUB_TOKEN` (`models: read`, no extra
secret); `--model`/`--base-url`/`--token` point it at any other OpenAI-chat-completions-compatible
endpoint, which is the seam phase 2 will loop over. Wired into a `workflow_dispatch`-only workflow
(`.github/workflows/agentrc-eval.yml`) that uploads the output directory as a build artifact - never
runs on push/PR, never blocks anything.

Each case now carries a `checklist` array alongside `prompt`/`expectation` - the binary rubric Q3
recommends, authored by hand per case. This is the rubric-authoring convention flagged as an open
question below: **new cases must ship with a `checklist`, not prose alone** (documented in
`AGENTS.md`). `scripts/check_agentrc_refs.py` (phase 0) does not validate the checklist field's
presence or shape; that is left to human review when a case is added or changed, same as case
content generally.

This phase also resolved case-1's semantic-staleness problem (see "Where things stand" above): it
now asks for a per-category configurable dedup window - a real, currently-unimplemented gap in the
shipped dedup design - instead of a scenario the codebase had already outgrown.

**Phase 2 - cross-model validation (done).** `scripts/run_agentrc_eval_cross_model.py` wraps phase
1: it imports `run_case()`/`ChatClient`/`load_eval_data()` from `run_agentrc_eval.py` rather than
duplicating them, loops over the model list in `scripts/agentrc_eval_models.json` (plain JSON - one
line per model, no script/workflow edit needed to add or remove one), and runs every case against
every model that has a credential available. The default list has four entries: GitHub Models'
`openai/gpt-4o-mini` (ambient `GITHUB_TOKEN`, no extra secret) plus three Anthropic models - Opus
4.8, Sonnet 5, Haiku 4.5 - sharing one `ANTHROPIC_API_KEY` repo secret (one secret per *provider*,
not per model, per Q5). Each entry (both providers) carries its own `base_url`, so pointing a model
at a proxy or a different region is a config change, not a code change. A model whose `token_env`
isn't set is skipped with a stderr warning, never a hard failure - a missing/expired credential for
one provider doesn't block the rest of the comparison (Q5's skip-not-fail requirement). Output:
per-`(case, model)` raw plan and verdicts
(`.agentrc-eval-out/cross-model/<case-id>__<model-name>.md`), plus a `comparison.md` report with a
per-case checklist x model matrix and a disagreement count per case - a checklist item where models
don't unanimously agree is flagged, which is the actual cross-model signal (Q3's warning that a
single judge's consistency isn't validity; seeing several models diverge on the same item is a much
stronger "this plan is ambiguous here" signal than one model's opinion).

Wired into `.github/workflows/agentrc-eval-cross-model.yml`: `workflow_dispatch` (optional
`case`/`models` inputs) only for now - the weekly `schedule` this was designed for is commented out
in the workflow pending a decision on run cadence/cost, never on push/PR either way. Same
`models: read` permission as phase 1's workflow; `ANTHROPIC_API_KEY` is read from secrets only if
present - nothing to configure if it isn't (the run just skips those three models and reports on
GitHub Models alone).

**GitHub Models is being retired 2026-07-30** (announced after this phase's initial implementation
- confirmed via GitHub's changelog, closed to new customers June 2026, brownouts July 16/23). This
breaks the "free, no-extra-secret default path" premise this phase (and phase 1) were built on: the
`github-gpt-4o-mini` entry, `run_agentrc_eval.py`'s own defaults, and both harness workflows'
`models: read` permission all assume an inference API that stops existing within the month. Not yet
resolved here - see the risk entry and follow-up below.

**Gotcha that affects both phase 1 and phase 2's workflows:** `workflow_dispatch` and `schedule`
triggers only fire for a workflow file that exists on the repository's default branch - `main`
here, not `dev`. Both `agentrc-eval.yml` and `agentrc-eval-cross-model.yml` will sit inert (not
listed in the Actions tab, cron silently not firing) until the next `dev -> main` stable release
carries them across. Until then, run either script locally - same code path, same output format,
just on your own machine instead of a runner.

**Phase 3 - advisory CI quality score.** Wire a cheap single-model pass-rate check into PR CI
(non-blocking, PR-comment + step-summary output only, per Q4's composite table). Only after
phase 1/2 have run long enough locally/on schedule to establish the harness's own false-positive
rate. No branch-protection requirement without an explicit follow-up decision.

## Risks / open questions

- **GitHub Models retires 2026-07-30.** The single biggest open item: the "no extra secret" default
  path both phases were built around stops working within weeks of this being written. Options -
  pick a new no-secret default (there may not be one), make a named-provider entry (e.g.
  `claude-haiku-4-5`, already cheapest of the three configured) the default instead and accept that
  phase 1's zero-secret pitch no longer holds, or drop the "free default" framing from Q2/Q5
  entirely and document that a secret is now always required. Needs a decision before phase 3 (or
  any real usage) - not resolved in this phase; tracked as
  [#319](https://github.com/PHeonix25/unifi_alerts/issues/319).
- **LLM-judge cost creep.** Even "advisory" CI can quietly become expensive if scope grows past
  5 cases or per-PR triggering happens by accident. Keep phase 3 scheduled/opt-in until proven
  cheap.
- **Model drift.** A case that passes today may fail after a model version bump with no code
  change on our side - the harness needs to tolerate (and report, not alarm on) that rather than
  reading it as a regression.
- **Secret sprawl.** Phase 2 landed with exactly one new secret (`ANTHROPIC_API_KEY`, shared by all
  four Claude entries) rather than one per model, which keeps this manageable for now - but adding
  a second non-Anthropic named provider means a second secret, and there's still no documented
  rotation/removal process for any of them.
- **Who maintains the rubric?** Resolved in phase 1: checklist authoring is now part of "add a
  case" (`AGENTS.md`). It's still manual, human work per case and doesn't scale automatically -
  worth revisiting if the case count grows well past five.
- **Judge reliability hasn't been measured yet.** Phase 1 runs the plan and the judge as two calls
  to the same model at temperature 0, but nothing in this repo yet checks the judge's own
  consistency (Q3's "run 3-5x and require majority agreement" is documented, not automated). Do
  that before leaning on phase 1's output for anything beyond "does this look plausible".
- **gh-aw re-evaluation trigger.** If GitHub Agentic Workflows exits Public Preview and the
  maintainer wants sandboxed general-purpose repo-maintenance agents (issue triage, CI doctor)
  for reasons beyond this harness, that's a separate decision from this one - don't let "we
  already use gh-aw for X" become the reason to migrate this narrow harness onto it.

## Suggested follow-up issues

1. **Replace the GitHub Models default path before 2026-07-30** - filed as
   [#319](https://github.com/PHeonix25/unifi_alerts/issues/319). Decide the new default (see the
   risk above), update `run_agentrc_eval.py`'s `DEFAULT_BASE_URL`/`DEFAULT_MODEL`,
   `scripts/agentrc_eval_models.json`, both workflows' `models: read` permission, and the Q2/Q5
   "no extra secret" framing in this document. Time-sensitive - the brownouts start 2026-07-16.
2. **Phase 3: advisory quality-score CI job** (PR comment + step-summary composite table per Q4;
   explicitly non-blocking; revisit branch-protection only as a separate, later decision).
3. **Judge reliability check** - run phase 1's harness 3-5x against a fixed case/model pair and
   measure verdict agreement, per Q3's reliability recommendation; currently undocumented in
   practice, only in principle.
4. **Secret rotation/removal process** for `ANTHROPIC_API_KEY` and any future named-provider
   secrets phase 2 accumulates (see "Secret sprawl" above) - currently undocumented.
5. **Reintroduce the weekly `schedule` trigger** in `agentrc-eval-cross-model.yml` (currently
   commented out per review feedback) once the harness has proven itself worth running unattended.
