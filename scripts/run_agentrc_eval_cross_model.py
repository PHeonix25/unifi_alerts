#!/usr/bin/env python3
"""Run agentrc.eval.json's cases against several models and compare them.

Phase 2 of the agentic-eval-harness plan in docs/research/agentic-eval-harness.md
(#287). Wraps run_agentrc_eval.py: for each model listed in
scripts/agentrc_eval_models.json, runs every case through
run_agentrc_eval.run_case() (same plan-then-judge flow, same model grading
its own plan), then renders a markdown report showing each model's
per-checklist-item verdict side by side and flagging items where models
disagree.

Advisory and manual/scheduled only - never wired into `make check` or any
PR-blocking CI job. Run it locally, or via the weekly-scheduled,
workflow_dispatch-capable `.github/workflows/agentrc-eval-cross-model.yml`.

Model list (scripts/agentrc_eval_models.json) is plain JSON so adding or
removing a model is a one-line data change, not a script/workflow edit. Each
entry names a `token_env` - a model whose token isn't set in the environment
is skipped with a warning, not a hard failure (a single missing/expired
provider credential should not block the rest of the comparison). The
default list is all Anthropic models sharing one ANTHROPIC_API_KEY secret
(one secret per provider, not per model); there is no zero-secret entry any
more (GitHub Models, the original free default, was retired 2026-07-30 -
see docs/research/agentic-eval-harness.md and #319).

Pure stdlib (urllib) - no SDK dependency, matching this repo's
minimal-dependency preference and run_agentrc_eval.py's approach.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from dataclasses import replace
from pathlib import Path

import run_agentrc_eval
from _console import use_utf8_console

use_utf8_console()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_CONFIG = REPO_ROOT / "scripts" / "agentrc_eval_models.json"

KNOWN_PROVIDERS = {"openai-compatible", "anthropic"}


def _build_client(entry: dict[str, str]) -> run_agentrc_eval.ChatClient | None:
    """Return a client for one model config entry, or None to skip it."""
    name = entry["name"]
    token = os.environ.get(entry["token_env"], "")
    if not token:
        print(f"skipping '{name}': ${entry['token_env']} is not set", file=sys.stderr)
        return None

    provider = entry.get("provider", "")
    if provider == "openai-compatible":
        return run_agentrc_eval.ModelClient(entry["base_url"], entry["model"], token)
    if provider == "anthropic":
        return run_agentrc_eval.AnthropicClient(entry["base_url"], entry["model"], token)

    print(
        f"skipping '{name}': unknown provider '{provider}' (expected one of "
        f"{sorted(KNOWN_PROVIDERS)})",
        file=sys.stderr,
    )
    return None


def build_comparison_report(
    cases: list[dict[str, object]],
    model_names: list[str],
    results: dict[str, dict[str, run_agentrc_eval.CaseResult]],
) -> str:
    """Render a markdown report: a summary table plus a per-case checklist matrix."""
    summary = [
        "## Summary",
        "",
        "| Case | " + " | ".join(model_names) + " | Disagreements |",
        "| --- | " + " | ".join("---" for _ in model_names) + " | --- |",
    ]
    detail: list[str] = []

    for case in cases:
        case_id = str(case["id"])
        checklist = list(case.get("checklist", []))
        per_model = results.get(case_id, {})

        detail += [f"## {case_id}", ""]
        if checklist:
            detail.append("| Checklist item | " + " | ".join(model_names) + " |")
            detail.append("| --- | " + " | ".join("---" for _ in model_names) + " |")

        disagreements = 0
        for idx, item in enumerate(checklist):
            cells = []
            seen = set()
            for name in model_names:
                result = per_model.get(name)
                if result is None:
                    cells.append("n/a")
                elif result.error or idx >= len(result.verdicts):
                    cells.append("error")
                else:
                    passed = bool(result.verdicts[idx].get("pass"))
                    seen.add(passed)
                    cells.append("pass" if passed else "FAIL")
            if len(seen) > 1:
                disagreements += 1
            detail.append(f"| {item} | " + " | ".join(cells) + " |")
        detail.append("")

        pass_rate_cells = []
        for name in model_names:
            result = per_model.get(name)
            if result is None:
                pass_rate_cells.append("n/a")
            elif result.error:
                pass_rate_cells.append("error: " + result.error.replace("|", "/"))
            else:
                passed = sum(1 for v in result.verdicts if v.get("pass"))
                pass_rate_cells.append(f"{passed}/{len(checklist)}")

        summary.append(f"| {case_id} | " + " | ".join(pass_rate_cells) + f" | {disagreements} |")

    return "\n".join(
        ["# agentrc.eval.json cross-model results", "", *summary, "", *detail]
    )


def main() -> int:
    """Run every configured (and available) model against every case."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="Only run this case id (e.g. case-1)")
    parser.add_argument(
        "--models-config",
        default=DEFAULT_MODELS_CONFIG,
        type=Path,
        help=f"Path to the model list (default: {DEFAULT_MODELS_CONFIG.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--models",
        help="Comma-separated model 'name' values to restrict to (default: all configured)",
    )
    parser.add_argument(
        "--out",
        default=REPO_ROOT / ".agentrc-eval-out" / "cross-model",
        type=Path,
        help="Output directory (default: .agentrc-eval-out/cross-model/)",
    )
    args = parser.parse_args()

    instructions, cases = run_agentrc_eval.load_eval_data()
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"error: no case with id '{args.case}'", file=sys.stderr)
            return 1

    model_entries = json.loads(args.models_config.read_text(encoding="utf-8"))
    if args.models:
        wanted = {n.strip() for n in args.models.split(",")}
        model_entries = [e for e in model_entries if e["name"] in wanted]

    clients: dict[str, run_agentrc_eval.ChatClient] = {}
    for entry in model_entries:
        client = _build_client(entry)
        if client is not None:
            clients[entry["name"]] = client

    if not clients:
        print(
            "error: no models available - check token env vars against "
            f"{args.models_config}",
            file=sys.stderr,
        )
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    model_names = sorted(clients)
    results: dict[str, dict[str, run_agentrc_eval.CaseResult]] = {}

    for case in cases:
        case_id = str(case["id"])
        checklist = list(case.get("checklist", []))
        results[case_id] = {}
        for name in model_names:
            print(f"Running {case_id} against {name}...", file=sys.stderr)
            try:
                result = run_agentrc_eval.run_case(clients[name], case, instructions)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as err:
                result = run_agentrc_eval.CaseResult(case_id=case_id, error=str(err))
            results[case_id][name] = result
            run_agentrc_eval.write_case_output(
                args.out, replace(result, case_id=f"{case_id}__{name}"), checklist
            )

    report = build_comparison_report(cases, model_names, results)
    print(report)
    (args.out / "comparison.md").write_text(report + "\n", encoding="utf-8")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")

    skipped = [e["name"] for e in model_entries if e["name"] not in clients]
    if skipped:
        print(f"\nSkipped (no token): {', '.join(skipped)}", file=sys.stderr)
    print(f"\nRaw plans, verdicts, and comparison report written to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
