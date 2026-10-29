"""Rule-based verdicts.

Each trace gets exactly one of five verdicts, plus the name of the rule that
decided it, a human-readable reason and the step where the rule fired. Rules run
in order and the first one that matches wins. Anything no rule can decide is
`Unknown`; an optional LLM judge may look at those later, but its answer is
stored separately and never replaces the rule verdict.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass

SUCCESS = "Success"
SKILL_ERROR = "Skill error"
UNEXPECTED = "Unexpected behavior"
OTHER_ERROR = "Other error"
UNKNOWN = "Unknown"
VERDICTS = [SUCCESS, SKILL_ERROR, UNEXPECTED, OTHER_ERROR, UNKNOWN]

MAX_RETRIES = 3  # identical tool calls allowed before it counts as a retry loop

# Errors caused by the environment rather than by what the skill told the agent to do.
ENVIRONMENT_ERRORS = re.compile(
    r"lock timeout|LockNotAvailable|ECONNRESET|connection refused|503 Service Unavailable|network unreachable",
    re.IGNORECASE,
)
ERROR_IN_OUTPUT = re.compile(r"Traceback \(most recent call last\)|^\w*Error:", re.MULTILINE)

FINAL_OUTPUT = -1  # step_index used when a rule fired on the final output


@dataclass
class Verdict:
    verdict: str
    rule: str
    reason: str
    step_index: int | None = None  # index into trace["steps"], FINAL_OUTPUT, or None
    judge_verdict: str | None = None  # set only by the optional LLM judge
    judge_reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def tool_calls(trace: dict) -> list[tuple[int, dict]]:
    return [(i, s) for i, s in enumerate(trace.get("steps") or []) if s.get("type") == "tool_call"]


def classify(trace: dict, expected_output: list[str] | None = None) -> Verdict:
    """Return the verdict for one trace. `expected_output` comes from the skill's frontmatter."""
    calls = tool_calls(trace)
    final = trace.get("final_output")
    feedback = trace.get("agent_feedback") or {}
    said_success = feedback.get("rating") == "success"

    # 1. Empty trace: nothing to judge.
    if not calls and not final:
        return Verdict(UNKNOWN, "empty_trace", "Trace has no tool calls and no final output.", None)

    # 2. Truncated trace: the run stopped mid-step.
    if final is None:
        idx = calls[-1][0] if calls else None
        return Verdict(UNKNOWN, "truncated_trace",
                       "Trace ends mid-run: the last step has no output and there is no final output.", idx)

    # 3. Retry loop: the same call repeated more than MAX_RETRIES times.
    counts = Counter((s["tool"], s["input"]) for _, s in calls)
    (tool, inp), n = counts.most_common(1)[0]
    if n > MAX_RETRIES:
        repeated = [(i, s) for i, s in calls if (s["tool"], s["input"]) == (tool, inp)]
        failing = [i for i, s in repeated if s.get("exit_code") not in (0, None)]
        idx = failing[-1] if failing else repeated[-1][0]
        return Verdict(UNEXPECTED, "retry_threshold",
                       f"`{tool}` was called {n} times with the same input (threshold {MAX_RETRIES}).", idx)

    # 4. Final tool call failed: the exit code decides, whatever the agent says.
    last_idx, last = calls[-1]
    if last.get("exit_code") not in (0, None):
        note = " Agent feedback said success; the exit code wins." if said_success else ""
        if ENVIRONMENT_ERRORS.search(last.get("output") or ""):
            return Verdict(OTHER_ERROR, "final_exit_code_environment",
                           f"Final tool call `{last['input']}` exited {last['exit_code']} "
                           f"with an environment error.{note}", last_idx)
        return Verdict(SKILL_ERROR, "final_exit_code",
                       f"Final tool call `{last['input']}` exited {last['exit_code']}.{note}", last_idx)

    # 5. Error text in the final output.
    if ERROR_IN_OUTPUT.search(final):
        return Verdict(SKILL_ERROR, "error_in_output", "Final output contains an error message.", FINAL_OUTPUT)

    # 6. Expected output missing.
    missing = [m for m in (expected_output or []) if m not in final]
    if missing:
        note = " Agent feedback said success." if said_success else ""
        return Verdict(UNEXPECTED, "missing_expected_output",
                       f"Final output is missing expected output '{missing[0]}'.{note}", FINAL_OUTPUT)

    # 7. Clean outcome but the agent reports failure: ambiguous, left for review.
    if feedback.get("rating") == "failure":
        return Verdict(UNKNOWN, "feedback_contradicts_outcome",
                       f"Outcome looks clean but agent feedback reports failure: \"{feedback.get('comment', '')}\"",
                       FINAL_OUTPUT)

    # 8. Success, possibly after recovering from intermediate errors.
    failed = [i for i, s in calls if s.get("exit_code") not in (0, None)]
    if failed:
        return Verdict(SUCCESS, "recovered",
                       f"Succeeded after {len(failed)} failed intermediate tool call(s).", failed[0])
    return Verdict(SUCCESS, "all_checks_passed", "All tool calls exited 0 and the expected output is present.", None)


def error_line(trace: dict, v: Verdict) -> str:
    """The raw text that best describes why a trace failed; used to build its signature."""
    steps = trace.get("steps") or []
    if v.rule == "missing_expected_output":
        return v.reason.split(".")[0]
    if v.step_index is not None and v.step_index >= 0:
        s = steps[v.step_index]
        out = (s.get("output") or "").splitlines()
        line = next((l for l in out if "error" in l.lower()), out[0] if out else "")
        if v.rule == "retry_threshold":
            return f"retry loop on {s['tool']}: {line}"
        return line
    return v.reason
