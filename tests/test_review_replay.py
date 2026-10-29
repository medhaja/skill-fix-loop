import pytest

from loop.pipeline import build
from loop.replay import replay
from loop.review import ReviewLog


@pytest.fixture(scope="module")
def state():
    return build(use_llm=False)


@pytest.fixture
def log(tmp_path):
    return ReviewLog(tmp_path / "reviews.jsonl")


def test_review_log_keeps_latest_decision_with_timestamp(log):
    log.record("d1", "s", "approved", "+x")
    log.record("d1", "s", "rejected", "+x")
    log.record("d2", "s", "edited", "+y")
    assert [e["decision"] for e in log.entries()] == ["approved", "rejected", "edited"]
    assert all(e["timestamp"] for e in log.entries())
    assert [e["draft_id"] for e in log.approved()] == ["d2"]
    with pytest.raises(ValueError):
        log.record("d3", "s", "maybe", "")
    log.clear()
    assert log.entries() == []


def test_no_approvals_means_no_change(state):
    for r in replay(state, []).values():
        assert r.after == r.before


def test_rejected_edits_change_nothing(state, log):
    for d in state.drafts.values():
        log.record(d.id, d.skill, "rejected", d.diff)
    for r in replay(state, log.approved()).values():
        assert r.after == r.before


def test_approving_one_edit_fixes_only_its_cause(state, log):
    d = next(d for d in state.drafts.values() if d.title.startswith("Check VERCEL_TOKEN"))
    log.record(d.id, d.skill, "approved", d.diff)
    results = replay(state, log.approved())
    assert results["deploy-preview"].after > results["deploy-preview"].before
    assert set(results["deploy-preview"].fixed_by_cause) == {"missing_env_var"}
    assert results["write-migration"].after == results["write-migration"].before


def test_edited_diff_is_what_gets_replayed(state, log):
    d = next(d for d in state.drafts.values() if d.title.startswith("Check VERCEL_TOKEN"))
    log.record(d.id, d.skill, "edited", "+- Make sure the deploy works.\n")  # reviewer removed the fix
    assert replay(state, log.approved())["deploy-preview"].fixed_by_cause == {}


def test_end_to_end_with_mock_drafter(state, log):
    """Generate -> verdict -> cluster -> draft -> approve all -> replay."""
    for d in state.drafts.values():
        log.record(d.id, d.skill, "approved", d.diff)
    results = replay(state, log.approved())
    for r in results.values():
        assert r.after > r.before
        # Ambiguous and empty traces are never "fixed", so the held-out rate stays below 100%.
        assert r.after < r.heldout
