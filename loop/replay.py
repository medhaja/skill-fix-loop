"""Simulated replay of approved edits on the held-out traces.

This does not re-run any agent. Each injected cause in the synthetic data has a
fix marker: a phrase an edit must add to the skill to address it. A held-out
trace that failed with that cause counts as fixed if an approved edit for the
same skill adds its marker. Rejected edits change nothing. It's a stand-in for
re-running agents and overstates real gains.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loop.drafter import added_lines
from loop.pipeline import State
from loop.verdict import SUCCESS

FIX_MARKERS = {
    "missing_env_var": "VERCEL_TOKEN",
    "wrong_cli_flag": "--target=preview",
    "unspecified_branch": "feature branch",
    "invalid_migration_name": "V<n>__",
    "missing_down_migration": "down()",
    "lock_timeout": "lock_timeout",
    "transcript_too_long": "chunk",
    "missing_action_items": "## Action items",
    "rate_limit_retry_loop": "backoff",
}


@dataclass
class SkillResult:
    skill: str
    heldout: int
    before: int
    after: int
    fixed_by_cause: dict[str, int] = field(default_factory=dict)
    approved_edits: int = 0

    @property
    def before_rate(self) -> float:
        return self.before / self.heldout if self.heldout else 0.0

    @property
    def after_rate(self) -> float:
        return self.after / self.heldout if self.heldout else 0.0


def replay(state: State, approved: list[dict]) -> dict[str, SkillResult]:
    """`approved` is a list of review entries ({skill, diff, ...}) whose decision is approved or edited."""
    results = {}
    for skill in state.skills:
        added = "\n".join(added_lines(e["diff"]) for e in approved if e["skill"] == skill)
        heldout = state.traces_for(skill, "heldout")
        before = sum(state.verdicts[t["id"]].verdict == SUCCESS for t in heldout)
        fixed: dict[str, int] = {}
        for t in heldout:
            cause = t.get("injected_cause")
            if state.verdicts[t["id"]].verdict == SUCCESS or cause not in FIX_MARKERS:
                continue
            if FIX_MARKERS[cause] in added:
                fixed[cause] = fixed.get(cause, 0) + 1
        results[skill] = SkillResult(
            skill, len(heldout), before, before + sum(fixed.values()), fixed,
            sum(1 for e in approved if e["skill"] == skill),
        )
    return results
