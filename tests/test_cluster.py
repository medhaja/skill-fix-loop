from loop.cluster import cluster_failures, find_repeated_workflows, normalize, purity
from loop.data import load_skills, load_traces
from loop.verdict import SUCCESS, UNKNOWN, classify, error_line


def test_normalize_strips_paths_ids_and_numbers():
    a = "Error: refusing to deploy branch 'main' (deployment dpl_8f3a2c91e0) in /home/runner/work/app-1/x"
    b = "Error: refusing to deploy branch 'main' (deployment dpl_19be07aa42) in /home/runner/work/app-7/x"
    assert normalize(a) == normalize(b)
    assert "<id>" in normalize(a) and "<path>" in normalize(a)
    assert normalize("tokens 48213, limit 32000") == "tokens <n>, limit <n>"
    assert normalize("bad name '2026_01_02_x.sql'") == "bad name '<file>'"


def test_near_duplicates_cluster_together_and_different_errors_apart():
    items = [
        ("a", "Skill error", "Error: Environment variable VERCEL_TOKEN is not set (request id req_1a2b3c4d)"),
        ("b", "Skill error", "Error: Environment variable VERCEL_TOKEN is not set (request id req_9f8e7d6c)"),
        ("c", "Skill error", "Error: unknown or unexpected option: --preview (vercel CLI 42.1.0)"),
        ("d", "Skill error", "Error: unknown or unexpected option: --preview (vercel CLI 43.0.2)"),
    ]
    causes = cluster_failures("s", items)
    assert sorted(sorted(c.trace_ids) for c in causes) == [["a", "b"], ["c", "d"]]
    assert all(len(c.examples) <= 3 for c in causes)


def mining_causes():
    skills = load_skills()
    traces = load_traces()
    causes = []
    for name, skill in skills.items():
        items = []
        for t in traces:
            if t["skill"] == name and t["split"] == "mining":
                v = classify(t, skill.expected_output)
                if v.verdict not in (SUCCESS, UNKNOWN):
                    items.append((t["id"], v.verdict, error_line(t, v)))
        causes += cluster_failures(name, items)
    return causes, {t["id"]: t["injected_cause"] for t in traces}


def test_cluster_purity_against_injected_causes_is_at_least_85_percent():
    causes, truth = mining_causes()
    assert purity(causes, truth) >= 0.85
    # A small number of named causes, each with a label and examples.
    assert 3 <= len(causes) <= 15
    assert all(c.label and c.examples for c in causes)


def test_repeated_workflow_is_flagged_only_for_migration_skill():
    skills = load_skills()
    traces = load_traces()
    found = {}
    for name, skill in skills.items():
        ok = [t for t in traces if t["skill"] == name and t["split"] == "mining"
              and classify(t, skill.expected_output).verdict == SUCCESS]
        found[name] = find_repeated_workflows(name, skill.text, ok)
    assert not found["deploy-preview"] and not found["summarize-meeting"]
    [wf] = found["write-migration"]
    assert wf.commands[0].startswith("pg_dump") and wf.count >= 10
