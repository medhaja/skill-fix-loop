"""Group failed traces into named causes, and spot repeated workflows.

A failure's signature is its error line with paths, IDs and numbers stripped,
so "dpl_8f3a2c" and "dpl_19be07" look the same. Signatures are turned into
TF-IDF vectors and grouped with agglomerative clustering (cosine distance,
average linkage, fixed distance threshold), separately for each skill.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

DISTANCE_THRESHOLD = 0.6
EXAMPLES_PER_CAUSE = 3

_PATH = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][\w.\-]+){2,}[\\/]?")
_URL = re.compile(r"https?://\S+")
_QUOTED_FILE = re.compile(r"'[^'\s]+\.\w{1,5}'")
_PREFIXED_ID = re.compile(r"\b[a-z]{2,5}_[0-9a-f]{4,}\b")
_HEX = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{6,}\b")
_NUMBER = re.compile(r"\d+(?:\.\d+)*")


def normalize(text: str, lower: bool = True) -> str:
    """Strip the parts of an error line that differ between runs of the same failure."""
    s = _URL.sub("<url>", text)
    s = _QUOTED_FILE.sub("'<file>'", s)
    s = _PATH.sub("<path>", s)
    s = _PREFIXED_ID.sub("<id>", s)
    s = _HEX.sub("<id>", s)
    s = _NUMBER.sub("<n>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower() if lower else s


@dataclass
class Cause:
    id: str
    skill: str
    label: str
    signature: str
    verdict: str  # most common verdict among its traces
    trace_ids: list[str]
    examples: list[str]  # up to EXAMPLES_PER_CAUSE trace ids
    raw_errors: list[str] = field(default_factory=list)  # one raw error line per trace, same order as trace_ids

    @property
    def count(self) -> int:
        return len(self.trace_ids)


def cluster_failures(skill: str, items: list[tuple[str, str, str]]) -> list[Cause]:
    """Cluster one skill's failures. `items` is a list of (trace_id, verdict, raw_error_line).

    Returns causes ranked by count, largest first.
    """
    if not items:
        return []
    sigs = [normalize(err) for _, _, err in items]
    if len(items) == 1:
        labels = [0]
    else:
        vectors = TfidfVectorizer(token_pattern=r"[\w\-<>']{2,}").fit_transform(sigs).toarray()
        model = AgglomerativeClustering(
            n_clusters=None, metric="cosine", linkage="average", distance_threshold=DISTANCE_THRESHOLD,
        )
        labels = model.fit_predict(vectors)

    groups: dict[int, list[int]] = {}
    for idx, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(idx)

    causes = []
    for members in sorted(groups.values(), key=lambda m: (-len(m), sigs[m[0]])):
        top_sig = Counter(sigs[i] for i in members).most_common(1)[0][0]
        rep = next(i for i in members if sigs[i] == top_sig)
        verdict = Counter(items[i][1] for i in members).most_common(1)[0][0]
        ids = [items[i][0] for i in members]
        causes.append(Cause(
            id="",
            skill=skill,
            label=_label(normalize(items[rep][2], lower=False)),
            signature=top_sig,
            verdict=verdict,
            trace_ids=ids,
            examples=ids[:EXAMPLES_PER_CAUSE],
            raw_errors=[items[i][2] for i in members],
        ))
    for n, c in enumerate(causes, 1):
        c.id = f"{skill}-c{n}"
    return causes


def _label(sig: str, limit: int = 110) -> str:
    sig = re.sub(r"\s*\((?:request id|deployment|pid|trace) <id>\)|\s*\(trace <id>\)", "", sig)
    sig = sig.rstrip(".")
    return sig if len(sig) <= limit else sig[: limit - 1].rstrip() + "…"


def purity(causes: list[Cause], truth: dict[str, str]) -> float:
    """Share of clustered traces whose cluster's majority injected cause matches their own."""
    total = agree = 0
    for c in causes:
        counts = Counter(truth[t] for t in c.trace_ids)
        agree += counts.most_common(1)[0][1]
        total += c.count
    return agree / total if total else 1.0


# ------------------------------------------------------------- repeated workflows

@dataclass
class WorkflowCandidate:
    skill: str
    commands: list[str]
    trace_ids: list[str]

    @property
    def count(self) -> int:
        return len(self.trace_ids)


def _command_key(step: dict) -> str:
    if step.get("tool") == "bash":
        return " ".join((step.get("input") or "").split()[:2])
    return step.get("tool") or ""


def find_repeated_workflows(skill: str, skill_text: str, traces: list[dict],
                            min_share: float = 0.08, min_len: int = 2) -> list[WorkflowCandidate]:
    """Find extra command sequences that agents keep running in successful traces.

    A command is "extra" when the skill never mentions it and it shows up in
    fewer than half of the runs (so it isn't just part of the normal flow). Runs
    that share the same ordered list of extra commands form a candidate. These
    are candidates for a new skill, not failures to fix.
    """
    per_trace = {}
    for t in traces:
        per_trace[t["id"]] = [_command_key(s) for s in t.get("steps") or [] if s.get("type") == "tool_call"]
    frequency = Counter(k for keys in per_trace.values() for k in set(keys))
    common = {k for k, n in frequency.items() if n >= len(traces) / 2}

    groups: dict[tuple, list[str]] = {}
    for tid, keys in per_trace.items():
        extra = tuple(k for k in keys if k not in common and k.split()[0] not in skill_text)
        if len(extra) >= min_len:
            groups.setdefault(extra, []).append(tid)
    threshold = max(3, int(min_share * len(traces)))
    found = [WorkflowCandidate(skill, list(cmds), ids) for cmds, ids in groups.items() if len(ids) >= threshold]
    return sorted(found, key=lambda w: -w.count)
