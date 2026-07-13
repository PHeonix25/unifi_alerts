#!/usr/bin/env python3
"""Run agentrc.eval.json's planning-evaluation cases against one model.

Phase 1 of the agentic-eval-harness plan in docs/research/agentic-eval-harness.md
(#287). For each case: ask a model for an implementation PLAN ONLY (a single
chat completion, no tool access, so it cannot touch the repo), then ask the
same model to grade that plan against the case's `checklist` as independent
binary criteria (pass/fail per item, not one aggregate score - see the design
note's LLM-as-judge section for why). Writes each case's raw plan and verdict
to an output directory for manual review, and prints a summary table.

This is advisory: it is not wired into `make check`, and any PR-triggered use
of it (phase 3, `.github/workflows/agentrc-quality-score.yml`) only ever
posts a comment/step-summary, never a blocking check. Costs a model API call
per case (plan) plus one more (judge). Run it locally, via the
`workflow_dispatch`-only `.github/workflows/agentrc-eval.yml`, or via phase
3's PR-triggered workflow.

Defaults to Anthropic's Messages API (--provider anthropic, model
claude-haiku-4-5-20251001 - the cheapest of the three Anthropic models this
repo has evaluated so far). Needs an ANTHROPIC_API_KEY with API access; there is no
zero-secret default any more (GitHub Models, the original default, was
retired 2026-07-30 - see docs/research/agentic-eval-harness.md and #319).
--provider openai-compatible switches to any OpenAI-chat-completions-shaped
endpoint via --base-url/--model/--token instead. This script takes one model
per invocation on purpose; run_agentrc_eval_cross_model.py (phase 2) is the
multi-model wrapper - it imports run_case()/ChatClient/AnthropicClient from
here and loops over a configured model list.

Pure stdlib (urllib) - no SDK dependency, matching this repo's
minimal-dependency preference.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from _console import use_utf8_console

use_utf8_console()

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_FILE = REPO_ROOT / "agentrc.eval.json"

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 4096
REQUEST_TIMEOUT_SECONDS = 120

PLAN_SYSTEM_PROMPT = """\
You are a senior engineer scoping a change to the repository described below \
before any code is written. Produce an IMPLEMENTATION PLAN ONLY: prose and/or \
a bulleted list of the files you would touch and what changes each needs, and \
which tests you would add or update. Do not write code, diffs, or shell \
commands. Be specific about file and symbol names where you know them from \
the context given."""

JUDGE_SYSTEM_PROMPT = """\
You are grading an implementation plan against a fixed checklist. For each \
checklist item, decide whether the plan satisfies it: true if the plan \
clearly addresses that point, false otherwise. Do not be lenient - a vague \
or missing mention is false. Respond with ONLY a JSON array, one object per \
checklist item, in the same order as given, each shaped exactly like: \
{"pass": true, "reason": "one short sentence"}. No prose outside the JSON."""


@dataclass
class CaseResult:
    """Outcome of running and grading one eval case."""

    case_id: str
    plan_text: str = ""
    verdicts: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None


class ChatClient(Protocol):
    """Structural interface run_case() needs from any model client.

    This is a typing.Protocol, not a base class - nothing inherits from it
    and it is never instantiated, so the `...` body below is correct and
    complete, not a stub someone forgot to fill in. It exists purely so
    run_case()'s `client` parameter documents what it actually calls
    (`.complete()`) without forcing every provider to subclass one type.
    ModelClient (below) and run_agentrc_eval_cross_model.py's AnthropicClient
    (a different wire format - Anthropic's Messages API, not OpenAI chat
    completions) both satisfy this just by having a matching method; mypy
    checks that structurally wherever this type hint is used, but note
    scripts/ isn't in this repo's mypy scope (pyproject.toml's [tool.mypy]
    only covers custom_components/unifi_alerts), so nothing enforces it here
    today - it's documentation-as-code, not a hard guarantee.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class ModelClient:
    """Minimal OpenAI-chat-completions-compatible client over urllib."""

    def __init__(self, base_url: str, model: str, token: str) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._token = token

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the assistant message content for one chat completion."""
        body = json.dumps(
            {
                "model": self._model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return str(payload["choices"][0]["message"]["content"])


class AnthropicClient:
    """Minimal Anthropic Messages API client over urllib.

    A different wire format than ModelClient (Anthropic's Messages API, not
    OpenAI chat completions), but satisfies ChatClient the same way - just by
    having a matching .complete() method. This is the default provider (see
    DEFAULT_PROVIDER); run_agentrc_eval_cross_model.py (phase 2) imports this
    class rather than defining its own copy.
    """

    def __init__(self, base_url: str, model: str, token: str) -> None:
        self._url = base_url.rstrip("/") + "/v1/messages"
        self._model = model
        self._token = token

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the assistant text for one Messages API call."""
        body = json.dumps(
            {
                "model": self._model,
                "max_tokens": ANTHROPIC_MAX_TOKENS,
                "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._token,
                "anthropic-version": ANTHROPIC_API_VERSION,
            },
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return "".join(block.get("text", "") for block in payload.get("content", []))


def _extract_json_array(text: str) -> list[dict[str, object]] | None:
    """Best-effort extraction of a JSON array from a judge response.

    Models sometimes wrap JSON in a code fence despite instructions not to.
    Falls back to the first `[...]` span in the text.
    """
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped)
    match = re.search(r"\[.*\]", stripped, re.DOTALL)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def load_eval_data() -> tuple[str, list[dict[str, object]]]:
    """Return (instructions text, cases) loaded from agentrc.eval.json.

    Shared by both the single-model (this script) and cross-model
    (run_agentrc_eval_cross_model.py) entry points.
    """
    data = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    instructions = (REPO_ROOT / data["instructionFile"]).read_text(encoding="utf-8")
    return instructions, data["cases"]


def run_case(
    client: ChatClient, case: dict[str, object], instructions: str
) -> CaseResult:
    """Run one case: generate a plan, then grade it against its checklist."""
    case_id = str(case["id"])
    prompt = str(case["prompt"])
    checklist = list(case.get("checklist", []))

    result = CaseResult(case_id=case_id)

    user_prompt = (
        f"Repository instructions:\n\n{instructions}\n\n"
        f"Task: {prompt}"
    )
    try:
        result.plan_text = client.complete(PLAN_SYSTEM_PROMPT, user_prompt).strip()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as err:
        result.error = f"plan request failed: {err}"
        return result

    if not checklist:
        result.error = "no checklist defined for this case - nothing to grade"
        return result

    checklist_block = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(checklist))
    judge_prompt = (
        f"Task the plan was written for: {prompt}\n\n"
        f"Checklist ({len(checklist)} items):\n{checklist_block}\n\n"
        f"Plan to grade:\n{result.plan_text}"
    )
    try:
        judge_raw = client.complete(JUDGE_SYSTEM_PROMPT, judge_prompt)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as err:
        result.error = f"judge request failed: {err}"
        return result

    parsed = _extract_json_array(judge_raw)
    if parsed is None or len(parsed) != len(checklist):
        result.error = (
            f"judge response did not parse into {len(checklist)} verdicts "
            f"(got: {judge_raw[:200]!r})"
        )
        return result

    result.verdicts = parsed
    return result


def write_case_output(out_dir: Path, result: CaseResult, checklist: list[str]) -> None:
    """Write one case's plan and verdicts to `out_dir/<case-id>.md`."""
    lines = [f"# {result.case_id}", ""]
    if result.error:
        lines += [f"**Error:** {result.error}", ""]
    if result.plan_text:
        lines += ["## Plan", "", result.plan_text, ""]
    if result.verdicts:
        lines += ["## Checklist verdicts", ""]
        for item, verdict in zip(checklist, result.verdicts, strict=False):
            mark = "x" if verdict.get("pass") else " "
            reason = verdict.get("reason", "")
            lines.append(f"- [{mark}] {item} - {reason}")
    (out_dir / f"{result.case_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_inline_result(result: CaseResult, checks: int) -> None:
    """Print an in-line summary of the results"""
    passes = sum(1 for v in result.verdicts if v.get("pass"))
    print(f" ({passes}/{checks})", file=sys.stderr)


def build_summary_table(results: list[CaseResult], checklists: dict[str, list[str]]) -> str:
    """Render a per-case pass-rate table as markdown."""
    lines = ["| Case | Pass rate | Status |", "| --- | --- | --- |"]
    for result in results:
        checklist = checklists.get(result.case_id, [])
        if result.error:
            lines.append(f"| {result.case_id} | - | error: {result.error} |")
            continue
        passed = sum(1 for v in result.verdicts if v.get("pass"))
        total = len(checklist)
        lines.append(f"| {result.case_id} | {passed}/{total} | completed |")
    return "\n".join(lines)


def print_summary(
    results: list[CaseResult], checklists: dict[str, list[str]], out_dir: Path
) -> None:
    """Print the pass-rate table, and write it to out_dir/summary.md and
    $GITHUB_STEP_SUMMARY (if set) for downstream consumers (e.g. phase 3's
    PR-comment step)."""
    table = build_summary_table(results, checklists)
    print(table)

    (out_dir / "summary.md").write_text(table + "\n", encoding="utf-8")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("## agentrc.eval.json results\n\n" + table + "\n")


def main() -> int:
    """Run the harness against every case (or one, via --case)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=["anthropic", "openai-compatible"],
        default=os.environ.get("AGENTRC_EVAL_PROVIDER", DEFAULT_PROVIDER),
        help=f"Which wire format to speak (default: {DEFAULT_PROVIDER})",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("AGENTRC_EVAL_MODEL", DEFAULT_MODEL),
        help=f"Model id (default: {DEFAULT_MODEL}, or $AGENTRC_EVAL_MODEL)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENTRC_EVAL_BASE_URL"),
        help=(
            f"API base URL (default: {DEFAULT_ANTHROPIC_BASE_URL} for "
            "--provider anthropic; required for --provider openai-compatible, "
            "no default - there is no free/standard endpoint every user shares)"
        ),
    )
    parser.add_argument(
        "--token",
        default=(
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("GITHUB_TOKEN")
            or os.environ.get("AGENTRC_EVAL_TOKEN")
        ),
        help="API key/bearer token (default: $ANTHROPIC_API_KEY, then $GITHUB_TOKEN, then $AGENTRC_EVAL_TOKEN)",
    )
    parser.add_argument("--case", help="Only run this case id (e.g. case-1)")
    parser.add_argument(
        "--out",
        default=REPO_ROOT / ".agentrc-eval-out",
        type=Path,
        help="Output directory for raw plans and verdicts (default: .agentrc-eval-out/)",
    )
    args = parser.parse_args()

    if not args.token:
        print(
            "error: no token available - set ANTHROPIC_API_KEY (for the default "
            "--provider anthropic) or pass --token",
            file=sys.stderr,
        )
        return 1

    if args.provider == "openai-compatible" and not args.base_url:
        print(
            "error: --provider openai-compatible needs --base-url (or "
            "$AGENTRC_EVAL_BASE_URL) - there is no shared default endpoint",
            file=sys.stderr,
        )
        return 1
    base_url = args.base_url or DEFAULT_ANTHROPIC_BASE_URL

    instructions, cases = load_eval_data()
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"error: no case with id '{args.case}'", file=sys.stderr)
            return 1

    args.out.mkdir(parents=True, exist_ok=True)
    client: ChatClient = (
        AnthropicClient(base_url, args.model, args.token)
        if args.provider == "anthropic"
        else ModelClient(base_url, args.model, args.token)
    )

    checklists = {str(c["id"]): list(c.get("checklist", [])) for c in cases}
    results = []
    for case in cases:
        print(f"Running {case['id']} against {args.model}...", file=sys.stderr, end="")
        result = run_case(client, case, instructions)
        print_inline_result(result, len(checklists[result.case_id]))
        write_case_output(args.out, result, checklists[result.case_id])
        results.append(result)

    print_summary(results, checklists, args.out)
    print(f"\nRaw plans and verdicts written to {args.out}", file=sys.stderr)

    # Advisory only: never fail the run, but surface a non-zero-looking hint
    # in the log if every case errored (likely a config/auth problem).
    if results and all(r.error for r in results):
        print("warning: every case errored - check --provider/--model/--base-url/--token", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
