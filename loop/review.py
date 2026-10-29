"""Human review decisions, appended to reviews.jsonl. The latest decision per draft wins."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loop.data import DATA_DIR

APPROVED, EDITED, REJECTED = "approved", "edited", "rejected"
DECISIONS = (APPROVED, EDITED, REJECTED)
DEFAULT_PATH = DATA_DIR / "reviews.jsonl"


class ReviewLog:
    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)

    def record(self, draft_id: str, skill: str, decision: str, diff: str, reviewer: str = "demo-reviewer") -> dict:
        if decision not in DECISIONS:
            raise ValueError(f"unknown decision {decision!r}")
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "draft_id": draft_id,
            "skill": skill,
            "decision": decision,
            "reviewer": reviewer,
            "diff": diff if decision != REJECTED else "",
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def latest(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.entries():
            out[e["draft_id"]] = e
        return out

    def approved(self) -> list[dict]:
        """Latest decision per draft, keeping only approved or edited-and-approved ones."""
        return [e for e in self.latest().values() if e["decision"] in (APPROVED, EDITED)]

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
