"""Quality numbers shown on the Results page."""

from __future__ import annotations

from loop.cluster import purity
from loop.pipeline import State
from loop.verdict import UNKNOWN


def verdict_accuracy(state: State, labels: dict[str, str]) -> tuple[int, int]:
    ids = [i for i in labels if i in state.verdicts]
    return sum(state.verdicts[i].verdict == labels[i] for i in ids), len(ids)


def cluster_purity(state: State) -> float:
    truth = {tid: t["injected_cause"] for tid, t in state.traces.items()}
    return purity([c for cs in state.causes.values() for c in cs], truth)


def judge_eval(state: State, labels: dict[str, str]) -> dict:
    """On Unknown traces: how many the judge moved out of Unknown, and agreement with labels where we have them."""
    unknown = [i for i, v in state.verdicts.items() if v.verdict == UNKNOWN]
    judged = [i for i in unknown if state.verdicts[i].judge_verdict]
    moved = [i for i in judged if state.verdicts[i].judge_verdict != UNKNOWN]
    labeled = [i for i in judged if i in labels]
    agree = sum(state.verdicts[i].judge_verdict == labels[i] for i in labeled)
    return {"unknown": len(unknown), "judged": len(judged), "moved": len(moved),
            "labeled": len(labeled), "agree": agree}
