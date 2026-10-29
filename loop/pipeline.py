"""Run the whole loop once: verdicts -> optional judge -> clusters -> drafts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from loop import llm
from loop.cluster import Cause, WorkflowCandidate, cluster_failures, find_repeated_workflows
from loop.data import DATA_DIR, Skill, load_skills, load_traces
from loop.drafter import Draft, draft
from loop.verdict import SUCCESS, UNKNOWN, Verdict, classify, error_line


@dataclass
class State:
    skills: dict[str, Skill]
    traces: dict[str, dict]
    verdicts: dict[str, Verdict]
    causes: dict[str, list[Cause]] = field(default_factory=dict)
    drafts: dict[str, Draft] = field(default_factory=dict)
    workflows: dict[str, list[WorkflowCandidate]] = field(default_factory=dict)
    triage: dict[str, list[str]] = field(default_factory=dict)  # Unknown traces in the mining set
    judge_enabled: bool = False

    def traces_for(self, skill: str, split: str | None = None) -> list[dict]:
        return [t for t in self.traces.values() if t["skill"] == skill and (split is None or t["split"] == split)]

    def verdict_counts(self, skill: str, split: str | None = None) -> Counter:
        return Counter(self.verdicts[t["id"]].verdict for t in self.traces_for(skill, split))

    def cause_of(self, trace_id: str) -> Cause | None:
        skill = self.traces[trace_id]["skill"]
        return next((c for c in self.causes.get(skill, []) if trace_id in c.trace_ids), None)


def build(data_dir: Path = DATA_DIR, use_llm: bool | None = None) -> State:
    use_llm = llm.enabled() if use_llm is None else use_llm
    skills = load_skills(data_dir)
    traces = {t["id"]: t for t in load_traces(data_dir)}
    verdicts = {tid: classify(t, skills[t["skill"]].expected_output) for tid, t in traces.items()}
    state = State(skills, traces, verdicts, judge_enabled=use_llm)

    if use_llm:
        for tid, v in verdicts.items():
            if v.verdict == UNKNOWN and v.rule == "feedback_contradicts_outcome":
                t = traces[tid]
                v.judge_verdict, v.judge_reason = llm.judge(t, skills[t["skill"]].text)

    for name, skill in skills.items():
        mining = state.traces_for(name, "mining")
        failures = [(t["id"], verdicts[t["id"]].verdict, error_line(t, verdicts[t["id"]]))
                    for t in mining if verdicts[t["id"]].verdict not in (SUCCESS, UNKNOWN)]
        state.causes[name] = cluster_failures(name, failures)
        state.triage[name] = [t["id"] for t in mining if verdicts[t["id"]].verdict == UNKNOWN]
        state.workflows[name] = find_repeated_workflows(
            name, skill.text, [t for t in mining if verdicts[t["id"]].verdict == SUCCESS])
        for cause in state.causes[name]:
            examples = [traces[i] for i in cause.examples]
            d = draft(cause, skill.text, len(failures), examples, use_llm=use_llm)
            state.drafts[d.id] = d
    return state
