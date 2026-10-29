"""Optional LLM calls through LiteLLM: a judge for Unknown traces and a skill-edit drafter.

Both are off unless LLM_MODEL is set (and the provider's API key, e.g.
ANTHROPIC_API_KEY or OPENAI_API_KEY). Without it, the app uses the rule
verdicts and the template drafter only. Judge output is stored as
`judge_verdict` and never replaces the rule verdict.
"""

from __future__ import annotations

import json
import os
import re

from loop.verdict import VERDICTS

MAX_STEP_CHARS = 400


def model() -> str:
    return os.environ.get("LLM_MODEL", "").strip()


def enabled() -> bool:
    if not model():
        return False
    try:
        import litellm  # noqa: F401
    except ImportError:
        return False
    return True


def _complete(prompt: str, max_tokens: int = 1500) -> str:
    import litellm

    resp = litellm.completion(
        model=model(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=max_tokens,
        timeout=60,
    )
    return resp.choices[0].message.content or ""


def _trace_summary(trace: dict) -> str:
    lines = []
    for i, s in enumerate(trace.get("steps") or []):
        out = (s.get("output") or "")[:MAX_STEP_CHARS]
        lines.append(f"[{i}] {s['type']} {s.get('tool') or ''} input={s.get('input')!r} "
                     f"exit={s.get('exit_code')} output={out!r}")
    lines.append(f"final_output={trace.get('final_output')!r}")
    lines.append(f"agent_feedback={json.dumps(trace.get('agent_feedback'))}")
    return "\n".join(lines)


def judge(trace: dict, skill_text: str) -> tuple[str | None, str]:
    """Ask the model for a verdict on an ambiguous trace. Returns (verdict or None, reason)."""
    prompt = (
        "You review runs of an AI agent that followed a skill file. Rule-based checks could not decide "
        "whether this run succeeded. Agent feedback is one signal; agents can be wrong about their own success.\n\n"
        f"Skill file:\n{skill_text}\n\nTrace:\n{_trace_summary(trace)}\n\n"
        f"Answer with JSON only: {{\"verdict\": one of {VERDICTS}, \"reason\": one sentence}}."
    )
    try:
        raw = _complete(prompt, max_tokens=300)
        data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        verdict = data.get("verdict")
        if verdict not in VERDICTS:
            return None, f"judge returned an invalid verdict: {verdict!r}"
        return verdict, str(data.get("reason", ""))
    except Exception as e:  # network, auth, parse: the rule verdict stands
        return None, f"judge call failed: {type(e).__name__}"


def draft_skill_edit(skill_text: str, cause, examples: list[dict]) -> tuple[str | None, str]:
    """Ask the model for a revised SKILL.md that prevents this failure. Returns (new_text or None, error)."""
    shown = "\n\n".join(_trace_summary(t) for t in examples[:3])
    prompt = (
        "You maintain a skill file that tells an AI agent how to do a task. Several runs failed the same way.\n\n"
        f"Failure signature: {cause.signature}\nFailed runs: {cause.count}\n\nExample traces:\n{shown}\n\n"
        f"Current skill file:\n```markdown\n{skill_text}```\n\n"
        "Make the smallest edit to the skill file that would prevent this failure. Keep everything else "
        "unchanged, including the frontmatter. Return the full revised file in one ```markdown block."
    )
    try:
        raw = _complete(prompt)
    except Exception as e:
        return None, f"call failed: {type(e).__name__}"
    m = re.search(r"```(?:markdown|md)?\n(.*?)```", raw, re.S)
    if not m:
        return None, "no markdown block in the response"
    text = m.group(1)
    return (text if text.endswith("\n") else text + "\n"), ""
