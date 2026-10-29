"""Draft one skill edit per failure cause.

The default drafter is deterministic: a small library of templates, each matched
against the cause's error text and turned into a concrete edit of the SKILL.md
file. If no template matches, it falls back to a generic "known failure" note.
When an LLM is configured (see loop/llm.py) the wording of the edit can come
from the model instead; the mock is still used if that call fails.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Callable

from loop.cluster import Cause

MAX_CITED = 5


@dataclass
class Draft:
    id: str
    skill: str
    cause_id: str
    title: str
    summary: str  # one sentence: what the edit changes
    rationale: str
    cited: list[str]
    old_text: str
    new_text: str
    diff: str
    source: str = "mock"
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------ text edit helpers

def _section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    start = next((i for i, l in enumerate(lines) if l.strip().lower() == f"## {heading}".lower()), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def add_precheck(text: str, bullet: str) -> str:
    """Add a bullet to a "Before you start" section placed just above Steps (keeps the diff small)."""
    lines = text.split("\n")
    if _section_bounds(lines, "Before you start"):
        return add_to_section(text, "Before you start", bullet)
    steps = _section_bounds(lines, "Steps")
    if not steps:
        return add_note(text, bullet)
    lines[steps[0]:steps[0]] = ["## Before you start", f"- {bullet}", ""]
    return "\n".join(lines)


def amend_step(text: str, keyword: str, extra: str) -> str:
    lines = text.split("\n")
    bounds = _section_bounds(lines, "Steps")
    if bounds:
        for i in range(*bounds):
            if re.match(r"^\d+\. ", lines[i]) and keyword.lower() in lines[i].lower():
                lines[i] = f"{lines[i]} {extra}"
                return "\n".join(lines)
    return add_note(text, extra)


def add_to_section(text: str, heading: str, bullet: str) -> str:
    lines = text.split("\n")
    bounds = _section_bounds(lines, heading)
    if not bounds:
        body = text.rstrip("\n")
        return f"{body}\n\n## {heading}\n- {bullet}\n"
    end = bounds[1]
    while end > bounds[0] + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, f"- {bullet}")
    return "\n".join(lines)


def add_note(text: str, bullet: str) -> str:
    return add_to_section(text, "Notes", bullet)


def unified_diff(skill: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/skills/{skill}/SKILL.md", tofile=f"b/skills/{skill}/SKILL.md",
    ))


# --------------------------------------------------------------------- templates

# Each template: (pattern on the raw error text, builder(match, skill_text) -> (title, summary, new_text))
Template = tuple[re.Pattern, Callable[[re.Match, str], tuple[str, str, str]]]


def _env_var(m, text):
    var = m.group(1)
    step = (f"Check that `{var}` is set (`test -n \"${var}\"`). If it is empty, stop and ask the user "
            f"to export it; do not try to continue without it.")
    return f"Check {var} before starting", f"Adds a pre-check that `{var}` is set.", add_precheck(text, step)


def _renamed_flag(m, text):
    old, new = m.group(1), m.group(2)
    if old in text:
        return (f"Replace removed flag {old} with {new}",
                f"The CLI rejects `{old}` and suggests `{new}`; the skill now uses `{new}`.",
                re.sub(re.escape(old) + r"(?![\w-])", new, text))
    return (f"Use {new} instead of {old}", f"Adds a note that `{old}` was replaced by `{new}`.",
            add_note(text, f"Newer CLI versions reject `{old}`; use `{new}`."))


def _protected_branch(m, text):
    branch = m.group(1)
    step = (f"Run `git branch --show-current`. If it is `{branch}`, do not deploy it: switch to the "
            f"user's feature branch first, and ask which one if it is unclear.")
    return f"Never deploy from {branch}", "Adds a pre-check that the agent is on a feature branch.", \
        add_precheck(text, step)


def _file_name(m, text):
    pattern = m.group(1).strip("'.")
    extra = (f"Name it `{pattern}`, where `<n>` is one more than the latest version and `<name>` "
             f"is a short snake_case description.")
    return "Spell out the migration file name format", f"Tells the agent the required name format `{pattern}`.", \
        amend_step(text, "migration file", extra)


def _missing_output(m, text):
    item = m.group(1)
    bullet = f"Always include `{item}`. Do not finish until it is in the output."
    new = add_to_section(text, "Output", bullet)
    if item == "down()":
        new = amend_step(new, "migration file", "Also write a `down()` that exactly reverses `up()`.")
    return f"Require {item} in the output", f"Makes `{item}` an explicit part of the expected output.", new


def _rate_limit(m, text):
    tool = m.group(1)
    bullet = (f"If `{tool}` returns HTTP 429, wait for the `retry after` time and use exponential backoff. "
              f"Make at most 3 attempts, then tell the user the service is rate limited.")
    return f"Back off on 429s from {tool}", "Caps retries and adds exponential backoff.", add_note(text, bullet)


def _context_length(m, text):
    extra = ("If the transcript is over the token limit, request it in chunks (`chunk=1..n`), summarize "
             "each chunk, then merge the chunk summaries.")
    return "Chunk long transcripts", "Tells the agent to load and summarize long transcripts in chunks.", \
        amend_step(text, "transcript", extra)


def _lock_timeout(m, text):
    bullet = ("Before `migrate apply`, run `SET lock_timeout = '5s'`. If it still times out, report the "
              "blocked table and suggest running outside peak hours instead of retrying.")
    return "Set a lock timeout and report contention", "Adds a lock_timeout setting and a clear failure message.", \
        add_note(text, bullet)


TEMPLATES: list[Template] = [
    (re.compile(r"environment variable (\w+) is not set", re.I), _env_var),
    (re.compile(r"unknown or unexpected option: (--[\w-]+).*?use (--[\w=-]+) instead", re.I), _renamed_flag),
    (re.compile(r"refusing to deploy protected branch '([^']+)'", re.I), _protected_branch),
    (re.compile(r"invalid migration filename .*expected (\S+)", re.I), _file_name),
    (re.compile(r"missing expected output '([^']+)'", re.I), _missing_output),
    (re.compile(r"retry loop on ([\w.]+):.*(?:429|rate limit)", re.I), _rate_limit),
    (re.compile(r"ContextLengthError|tokens, limit", re.I), _context_length),
    (re.compile(r"lock timeout|LockNotAvailable", re.I), _lock_timeout),
]


def _fallback(cause: Cause, text: str):
    bullet = f"Known failure seen in {cause.count} runs: `{cause.label}`. Check for it before finishing."
    return "Document a known failure", "No template matched; adds a note describing the failure.", \
        add_note(text, bullet)


# ------------------------------------------------------------------------ public

def rationale_for(cause: Cause, summary: str, skill_failures: int) -> tuple[str, list[str]]:
    cited = cause.trace_ids[:MAX_CITED]
    share = round(100 * cause.count / skill_failures) if skill_failures else 0
    text = (f"{cause.count} of {skill_failures} failed runs of `{cause.skill}` in the mining set ({share}%) "
            f"share the signature `{cause.signature}` (most are '{cause.verdict}'). {summary}")
    return text, cited


def mock_draft(cause: Cause, skill_text: str, skill_failures: int) -> Draft:
    raw = cause.raw_errors[0] if cause.raw_errors else cause.label
    for pattern, build in TEMPLATES:
        m = pattern.search(raw)
        if m:
            title, summary, new_text = build(m, skill_text)
            break
    else:
        title, summary, new_text = _fallback(cause, skill_text)
    rationale, cited = rationale_for(cause, summary, skill_failures)
    return Draft(
        id=cause.id, skill=cause.skill, cause_id=cause.id, title=title, summary=summary,
        rationale=rationale, cited=cited, old_text=skill_text, new_text=new_text,
        diff=unified_diff(cause.skill, skill_text, new_text), source="mock",
    )


def draft(cause: Cause, skill_text: str, skill_failures: int,
          examples: list[dict] | None = None, use_llm: bool = False) -> Draft:
    """Draft an edit for one cause, using the LLM if asked to and the mock otherwise."""
    from loop import llm

    base = mock_draft(cause, skill_text, skill_failures)
    if not use_llm:
        return base
    new_text, err = llm.draft_skill_edit(skill_text, cause, examples or [])
    if not new_text or new_text.strip() == skill_text.strip():
        base.notes.append(f"LLM drafter fell back to the template: {err or 'no change returned'}.")
        return base
    base.new_text = new_text
    base.diff = unified_diff(cause.skill, skill_text, new_text)
    base.source = f"llm:{llm.model()}"
    return base


def added_lines(diff: str) -> str:
    """The text a diff adds, used by replay to look for fix markers."""
    return "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
