import pytest

from loop import llm
from loop.cluster import Cause
from loop.drafter import added_lines, add_precheck, draft, mock_draft
from loop.pipeline import build

SKILL = """---
name: demo
---

# Demo

## Steps
1. Run `tool deploy --preview`.
2. Reply.

## Output
- `Done`
"""


def cause(error, n=6):
    ids = [f"t{i}" for i in range(n)]
    return Cause("demo-c1", "demo", error, error.lower(), "Skill error", ids, ids[:3], [error] * n)


@pytest.fixture(scope="module")
def state():
    return build(use_llm=False)


def test_flag_template_replaces_the_flag():
    d = mock_draft(cause("Error: unknown or unexpected option: --preview (cli 4). Use --target=preview instead."),
                   SKILL, 10)
    assert "--target=preview" in added_lines(d.diff)
    assert "-1. Run `tool deploy --preview`." in d.diff
    assert d.source == "mock"


def test_precheck_goes_above_steps_without_renumbering():
    new = add_precheck(SKILL, "Check X.")
    assert "## Before you start\n- Check X.\n\n## Steps\n1. Run" in new


def test_unmatched_error_falls_back_to_a_note():
    d = mock_draft(cause("something odd happened"), SKILL, 10)
    assert d.title == "Document a known failure"
    assert "## Notes" in d.new_text


def test_rationale_cites_trace_ids():
    d = mock_draft(cause("Error: Environment variable API_KEY is not set"), SKILL, 12)
    assert d.cited[:3] == ["t0", "t1", "t2"]
    assert "6 of 12" in d.rationale


def test_every_cause_with_5_or_more_traces_gets_a_diff_citing_3_traces(state):
    for causes in state.causes.values():
        for c in causes:
            if c.count >= 5:
                d = state.drafts[c.id]
                assert d.diff.startswith("--- a/skills/")
                assert len(d.cited) >= 3
                assert all(t in c.trace_ids for t in d.cited)


def test_llm_drafter_falls_back_to_mock_when_call_fails(monkeypatch):
    monkeypatch.setattr(llm, "draft_skill_edit", lambda *a: (None, "call failed: AuthenticationError"))
    d = draft(cause("Error: Environment variable API_KEY is not set"), SKILL, 10, use_llm=True)
    assert d.source == "mock"
    assert "fell back" in d.notes[0]


def test_llm_drafter_output_is_used_when_present(monkeypatch):
    monkeypatch.setattr(llm, "draft_skill_edit", lambda *a: (SKILL.replace("Reply.", "Reply with X."), ""))
    monkeypatch.setenv("LLM_MODEL", "test/model")
    d = draft(cause("whatever"), SKILL, 10, use_llm=True)
    assert d.source == "llm:test/model"
    assert "+2. Reply with X." in d.diff


def test_llm_is_off_without_model(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert llm.enabled() is False


def test_judge_never_overwrites_rule_verdict(monkeypatch):
    from loop import pipeline

    monkeypatch.setattr(pipeline.llm, "judge", lambda trace, text: ("Success", "looks fine"))
    monkeypatch.setattr(pipeline, "draft", lambda c, t, n, ex, use_llm: mock_draft(c, t, n))
    s = pipeline.build(use_llm=True)
    judged = [v for v in s.verdicts.values() if v.judge_verdict]
    assert judged, "judge should run on ambiguous Unknown traces"
    assert all(v.verdict == "Unknown" and v.judge_verdict == "Success" for v in judged)
