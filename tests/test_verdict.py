from loop.data import load_eval_labels, load_skills, load_traces
from loop.verdict import (
    OTHER_ERROR, SKILL_ERROR, SUCCESS, UNEXPECTED, UNKNOWN, classify, error_line,
)


def call(inp, out, code=0, tool="bash"):
    return {"type": "tool_call", "tool": tool, "input": inp, "output": out, "exit_code": code}


def trace(steps, final="Preview URL: x", feedback=None):
    return {"id": "t", "skill": "s", "steps": steps, "final_output": final, "agent_feedback": feedback}


EXPECTED = ["Preview URL:"]


def test_clean_run_is_success():
    v = classify(trace([call("npm ci", "ok")]), EXPECTED)
    assert (v.verdict, v.rule) == (SUCCESS, "all_checks_passed")


def test_success_despite_intermediate_error():
    v = classify(trace([call("npm ci", "ECONNRESET", 1), call("npm ci", "ok")]), EXPECTED)
    assert (v.verdict, v.rule, v.step_index) == (SUCCESS, "recovered", 0)


def test_final_exit_code_is_skill_error_and_beats_positive_feedback():
    t = trace([call("vercel deploy", "Error: unknown option", 2)], feedback={"rating": "success"})
    v = classify(t, EXPECTED)
    assert v.verdict == SKILL_ERROR
    assert "exit code wins" in v.reason
    assert v.step_index == 0


def test_environment_error_is_other_error():
    v = classify(trace([call("migrate apply", "LockNotAvailable: lock timeout", 1)]), EXPECTED)
    assert v.verdict == OTHER_ERROR


def test_missing_expected_output():
    v = classify(trace([call("x", "ok")], final="done"), EXPECTED)
    assert (v.verdict, v.rule) == (UNEXPECTED, "missing_expected_output")
    assert error_line({"steps": []}, v) == "Final output is missing expected output 'Preview URL:'"


def test_retry_threshold():
    steps = [call("fetch", "429", 1, tool="calendar")] * 4 + [call("fetch", "ok", 0, tool="calendar")]
    v = classify(trace(steps), EXPECTED)
    assert (v.verdict, v.rule) == (UNEXPECTED, "retry_threshold")


def test_empty_and_truncated_are_unknown():
    assert classify(trace([], final=None), EXPECTED).rule == "empty_trace"
    v = classify(trace([call("npm ci", None, None)], final=None), EXPECTED)
    assert (v.verdict, v.rule) == (UNKNOWN, "truncated_trace")


def test_negative_feedback_on_clean_run_is_unknown_not_failure():
    v = classify(trace([call("x", "ok")], feedback={"rating": "failure", "comment": "hm"}), EXPECTED)
    assert (v.verdict, v.rule) == (UNKNOWN, "feedback_contradicts_outcome")


def test_accuracy_on_labeled_eval_set_is_at_least_90_percent():
    skills = load_skills()
    traces = {t["id"]: t for t in load_traces()}
    labels = load_eval_labels()
    assert len(labels) == 60
    correct = sum(classify(traces[i], skills[traces[i]["skill"]].expected_output).verdict == lab
                  for i, lab in labels.items())
    assert correct / len(labels) >= 0.9, f"accuracy {correct}/{len(labels)}"


def test_every_trace_gets_a_reason():
    skills = load_skills()
    for t in load_traces():
        v = classify(t, skills[t["skill"]].expected_output)
        assert v.reason and v.rule
