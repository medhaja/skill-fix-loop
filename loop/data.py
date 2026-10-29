"""Loading skills and traces from disk."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


@dataclass
class Skill:
    name: str
    text: str
    description: str = ""
    expected_output: list[str] = field(default_factory=list)


def parse_frontmatter(text: str) -> dict:
    """Parse the small YAML subset used in SKILL.md frontmatter (scalars and string lists)."""
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)[1]
    meta: dict = {}
    key = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and key:
            meta.setdefault(key, []).append(line[4:].strip().strip('"'))
        elif ":" in line:
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if value:
                meta[key] = value.strip('"')
    return meta


def load_skills(data_dir: Path = DATA_DIR) -> dict[str, Skill]:
    skills = {}
    for path in sorted((data_dir / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        meta = parse_frontmatter(text)
        name = meta.get("name", path.parent.name)
        skills[name] = Skill(name, text, meta.get("description", ""), meta.get("expected_output", []))
    return skills


def load_traces(data_dir: Path = DATA_DIR) -> list[dict]:
    with open(data_dir / "traces.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_eval_labels(data_dir: Path = DATA_DIR) -> dict[str, str]:
    with open(data_dir / "eval_labels.jsonl", encoding="utf-8") as f:
        return {row["id"]: row["label"] for row in map(json.loads, f) if row}
