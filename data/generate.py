"""Seeded generator for the synthetic skills, traces and labeled eval set.

Everything here is invented. Run `python data/generate.py` to rebuild:

  data/skills/<name>/SKILL.md   3 skill files
  data/traces.jsonl             600 traces (200 per skill, 70/30 mining/held-out)
  data/eval_labels.jsonl        60 traces with a hand-assigned expected verdict

Each trace carries `injected_cause`, the ground truth the generator used. The
verdict and clustering code never read it; only the tests and the simulated
replay do.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 7
DATA_DIR = Path(__file__).resolve().parent
TRACES_PER_SKILL = 200
HELDOUT_SHARE = 0.3
EVAL_SIZE = 60

SKILLS = {
    "deploy-preview": """---
name: deploy-preview
description: Build the current web project and deploy it to a Vercel preview URL.
expected_output:
  - "Preview URL:"
---

# Deploy preview

## When to use
Use this when the user asks for a preview link for the current branch of a web project.

## Steps
1. Run `npm ci` to install dependencies.
2. Run `npm run build` and stop if the build fails.
3. Run `vercel build` to produce the prebuilt output.
4. Run `vercel deploy --prebuilt --preview` and capture the URL it prints.
5. Reply with the URL.

## Output
- One line: `Preview URL: <url>`
""",
    "write-migration": """---
name: write-migration
description: Write a SQL migration for a schema change the user describes.
expected_output:
  - "up()"
  - "down()"
---

# Write migration

## When to use
Use this when the user asks for a database schema change (new table, column or index).

## Steps
1. Read `db/migrations/` to find the latest migration.
2. Write a new migration file in `db/migrations/` with the change in `up()`.
3. Run `migrate check` to validate the file.
4. Run `migrate apply --dry-run` against the local database.
5. Summarize the migration for the user.

## Output
- The file name and a short summary of `up()` and `down()`.
""",
    "summarize-meeting": """---
name: summarize-meeting
description: Summarize a recorded meeting from its transcript and calendar entry.
expected_output:
  - "## Summary"
  - "## Action items"
---

# Summarize meeting

## When to use
Use this when the user asks for notes from a meeting that has a transcript.

## Steps
1. Call `calendar.fetch_events` to find the meeting and its attendees.
2. Call `transcripts.get` with the meeting id to load the transcript.
3. Write the summary.

## Output
- A `## Summary` section with 3 to 6 bullets.
""",
}

# Ground-truth verdict for each injected cause (None = normal successful run).
CAUSE_LABELS = {
    None: "Success",
    "recovered": "Success",
    "repeated_workflow": "Success",
    "missing_env_var": "Skill error",
    "wrong_cli_flag": "Skill error",
    "unspecified_branch": "Skill error",
    "invalid_migration_name": "Skill error",
    "missing_down_migration": "Unexpected behavior",
    "lock_timeout": "Other error",
    "transcript_too_long": "Skill error",
    "missing_action_items": "Unexpected behavior",
    "rate_limit_retry_loop": "Unexpected behavior",
    "empty_trace": "Unknown",
    "truncated_trace": "Unknown",
}

# How many traces of each kind per skill. Each list sums to 200.
MIX = {
    "deploy-preview": [
        (None, 118), ("recovered", 10), ("missing_env_var", 28), ("wrong_cli_flag", 22),
        ("unspecified_branch", 14), ("ambiguous_feedback", 4), ("empty_trace", 2), ("truncated_trace", 2),
    ],
    "write-migration": [
        (None, 110), ("repeated_workflow", 22), ("recovered", 6), ("invalid_migration_name", 26),
        ("missing_down_migration", 24), ("lock_timeout", 4), ("ambiguous_feedback", 4),
        ("empty_trace", 2), ("truncated_trace", 2),
    ],
    "summarize-meeting": [
        (None, 112), ("recovered", 8), ("transcript_too_long", 30), ("missing_action_items", 26),
        ("rate_limit_retry_loop", 16), ("ambiguous_feedback", 4), ("empty_trace", 2), ("truncated_trace", 2),
    ],
}

FEATURES = ["pricing-page", "onboarding-flow", "search-filters", "dark-mode", "billing-settings", "team-invites"]
TABLES = ["orders", "invoices", "users", "workspaces", "events", "api_keys"]
COLUMNS = ["archived_at", "external_ref", "plan_tier", "last_seen_at", "region", "owner_id"]
MEETINGS = ["Weekly sync", "Design review", "Sprint planning", "Customer call", "Incident retro", "Roadmap review"]
NAMES = ["Asha", "Ben", "Chen", "Dana", "Eli", "Farah", "Gus", "Hana"]


def hexid(rng: random.Random, n: int = 8) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def step(tool: str, input_: str, output: str | None, exit_code: int | None = 0) -> dict:
    return {"type": "tool_call", "tool": tool, "input": input_, "output": output, "exit_code": exit_code}


def prompt_step(text: str) -> dict:
    return {"type": "prompt", "tool": None, "input": text, "output": None, "exit_code": None}


# ---------------------------------------------------------------- deploy-preview

def deploy_trace(rng: random.Random, cause: str | None) -> tuple[list, str | None, dict | None]:
    feature = rng.choice(FEATURES)
    run = rng.randint(100, 999)
    url = f"https://{feature}-{hexid(rng, 6)}.vercel.app"
    workdir = f"/home/runner/work/app-{run}"
    steps = [prompt_step(f"Can you deploy a preview of the {feature} branch?")]
    steps.append(step("bash", "git branch --show-current", f"feat/{feature}"))
    if cause == "recovered":
        steps.append(step("bash", "npm ci", f"npm ERR! network ECONNRESET while fetching registry.npmjs.org (attempt 1)", 1))
    steps.append(step("bash", "npm ci", f"added {rng.randint(400, 1400)} packages in {rng.randint(8, 40)}s"))
    steps.append(step("bash", "npm run build", f"Compiled successfully in {rng.randint(10, 90)}s"))
    steps.append(step("bash", "vercel build", f"Build Completed in {workdir}/.vercel/output [{rng.randint(5, 40)}s]"))
    feedback = None
    final = f"Preview URL: {url}"

    if cause == "missing_env_var":
        steps.append(step(
            "bash", "vercel deploy --prebuilt --preview",
            f"Error: Environment variable VERCEL_TOKEN is not set (request id req_{hexid(rng)}).\n"
            f"Run `vercel login` or export VERCEL_TOKEN in {workdir}/.env",
            1,
        ))
        final = "The deploy failed because the Vercel token is missing."
    elif cause == "wrong_cli_flag":
        version = f"4{rng.randint(1, 3)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
        steps.append(step(
            "bash", "vercel deploy --prebuilt --preview",
            f"Error: unknown or unexpected option: --preview (vercel CLI {version}). Use --target=preview instead.",
            2,
        ))
        final = "I ran the deploy command. It printed an option warning; the preview should be available shortly."
        if rng.random() < 0.5:
            # Agent feedback that contradicts the exit code.
            feedback = {"rating": "success", "comment": "Deployed the preview as asked."}
    elif cause == "unspecified_branch":
        steps[1] = step("bash", "git branch --show-current", "main")
        steps.append(step(
            "bash", "vercel deploy --prebuilt --preview",
            f"Error: refusing to deploy protected branch 'main' to a preview (deployment dpl_{hexid(rng, 10)}).",
            1,
        ))
        final = "Deploy was refused because the current branch is main."
    else:
        steps.append(step("bash", "vercel deploy --prebuilt --preview", f"Preview: {url} [{rng.randint(3, 20)}s]"))
    return steps, final, feedback


# --------------------------------------------------------------- write-migration

def migration_trace(rng: random.Random, cause: str | None) -> tuple[list, str | None, dict | None]:
    table, column = rng.choice(TABLES), rng.choice(COLUMNS)
    version = rng.randint(10, 80)
    good_name = f"V{version + 1}__add_{column}_to_{table}.sql"
    steps = [prompt_step(f"Add a nullable {column} column to {table}.")]
    if cause == "repeated_workflow":
        # Same three manual steps in every run; the skill never mentions them.
        steps.append(step("bash", "pg_dump --schema-only --file schema_before.sql",
                          f"dumped {rng.randint(20, 60)} tables"))
    steps.append(step("read_file", "db/migrations/", f"V{version}__previous_change.sql (latest of {version})"))
    feedback = None
    final = f"Created {good_name}.\nup(): add column {column} to {table}.\ndown(): drop column {column}."

    if cause == "invalid_migration_name":
        bad = f"2026_{rng.randint(1, 12):02d}_{rng.randint(1, 28):02d}_add_{column}_to_{table}.sql"
        steps.append(step("write_file", f"db/migrations/{bad}", "written"))
        steps.append(step(
            "bash", "migrate check",
            f"ValueError: invalid migration filename '{bad}' in /srv/app-{rng.randint(100, 999)}/db/migrations: "
            f"expected V<n>__<name>.sql",
            1,
        ))
        final = "The migration check failed on the file name."
        return steps, final, feedback

    steps.append(step("write_file", f"db/migrations/{good_name}", "written"))
    steps.append(step("bash", "migrate check", "1 migration OK"))
    if cause == "lock_timeout":
        steps.append(step(
            "bash", "migrate apply --dry-run",
            f"psycopg.errors.LockNotAvailable: canceling statement due to lock timeout on table {table} "
            f"(pid {rng.randint(1000, 9999)})",
            1,
        ))
        final = "The dry run timed out waiting for a lock."
        return steps, final, feedback
    if cause == "recovered":
        steps.append(step("bash", "migrate apply --dry-run",
                          "connection refused: localhost:5432 (database still starting)", 1))
    steps.append(step("bash", "migrate apply --dry-run", f"dry run OK: 1 statement, {rng.randint(2, 90)}ms"))
    if cause == "repeated_workflow":
        steps.append(step("bash", "pg_dump --schema-only --file schema_after.sql",
                          f"dumped {rng.randint(20, 60)} tables"))
        steps.append(step("bash", "diff -u schema_before.sql schema_after.sql",
                          f"+    {column} text NULL"))
    if cause == "missing_down_migration":
        final = f"Created {good_name}.\nup(): add column {column} to {table}."
        if rng.random() < 0.3:
            feedback = {"rating": "success", "comment": "Migration written and checked."}
    return steps, final, feedback


# ------------------------------------------------------------- summarize-meeting

def meeting_trace(rng: random.Random, cause: str | None) -> tuple[list, str | None, dict | None]:
    meeting = rng.choice(MEETINGS)
    mid = f"mtg_{hexid(rng, 10)}"
    people = rng.sample(NAMES, 3)
    steps = [prompt_step(f"Summarize yesterday's {meeting}.")]
    feedback = None
    if cause == "rate_limit_retry_loop":
        for _ in range(rng.randint(4, 6)):
            steps.append(step("calendar.fetch_events", f"query='{meeting}'",
                              f"HTTP 429 Too Many Requests: rate limit exceeded, retry after {rng.randint(20, 60)}s "
                              f"(trace {hexid(rng, 12)})", 1))
        steps.append(step("calendar.fetch_events", f"query='{meeting}'", f"1 event: {mid}, attendees {', '.join(people)}"))
    else:
        if cause == "recovered":
            steps.append(step("calendar.fetch_events", f"query='{meeting}'", "HTTP 503 Service Unavailable", 1))
        steps.append(step("calendar.fetch_events", f"query='{meeting}'", f"1 event: {mid}, attendees {', '.join(people)}"))

    tokens = rng.randint(4000, 20000)
    if cause == "transcript_too_long":
        tokens = rng.randint(34000, 90000)
        steps.append(step(
            "transcripts.get", f"id={mid}",
            f"ContextLengthError: transcript has {tokens} tokens, limit 32000",
            1,
        ))
        return steps, "I couldn't load the transcript because it is too long.", feedback
    steps.append(step("transcripts.get", f"id={mid}", f"transcript loaded ({tokens} tokens, {len(people)} speakers)"))

    summary = (f"## Summary\n- {meeting} with {', '.join(people)}.\n- Agreed on next milestone.\n"
               f"- Open question on scope.")
    actions = f"\n\n## Action items\n- {people[0]}: draft the proposal by Friday."
    if cause == "missing_action_items":
        final = summary
        if rng.random() < 0.3:
            feedback = {"rating": "success", "comment": "Summary posted."}
    else:
        final = summary + actions
    return steps, final, feedback


BUILDERS = {"deploy-preview": deploy_trace, "write-migration": migration_trace, "summarize-meeting": meeting_trace}

AMBIGUOUS_COMMENTS = [
    # (comment, what a careful human reviewer concluded)
    ("I finished, but I'm not sure this was the environment the user wanted.", "Success"),
    ("Done, though I may have misread part of the request.", "Success"),
    ("The output covers only part of what was asked; I skipped some of it.", "Unexpected behavior"),
    ("I think I did the wrong thing here even though nothing errored.", "Unexpected behavior"),
]


def build_trace(rng: random.Random, skill: str, cause: str | None, n: int) -> tuple[dict, str]:
    tid = f"{skill.split('-')[0][:3]}-{n:03d}-{hexid(rng, 4)}"
    harness = rng.choice(["claude_code", "codex"])
    label = CAUSE_LABELS.get(cause)

    if cause == "empty_trace":
        steps, final, feedback = [], None, None
    elif cause == "truncated_trace":
        steps, _, _ = BUILDERS[skill](rng, None)
        steps = steps[: max(2, len(steps) // 2)]
        last = steps[-1]
        steps[-1] = {**last, "output": None, "exit_code": None}
        final, feedback = None, None
    elif cause == "ambiguous_feedback":
        steps, final, _ = BUILDERS[skill](rng, None)
        comment, label = AMBIGUOUS_COMMENTS[n % len(AMBIGUOUS_COMMENTS)]
        feedback = {"rating": "failure", "comment": comment}
    else:
        steps, final, feedback = BUILDERS[skill](rng, cause)
        if feedback is None and rng.random() < 0.25:
            ok = label == "Success"
            feedback = {"rating": "success" if ok else "failure",
                        "comment": "Completed as asked." if ok else "Something went wrong during the run."}

    trace = {
        "id": tid,
        "skill": skill,
        "harness": harness,
        "steps": steps,
        "final_output": final,
        "agent_feedback": feedback,
        "injected_cause": cause,
    }
    return trace, label


def main() -> None:
    rng = random.Random(SEED)

    for name, text in SKILLS.items():
        path = DATA_DIR / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    traces, labels = [], {}
    for skill, mix in MIX.items():
        causes = [c for c, k in mix for _ in range(k)]
        assert len(causes) == TRACES_PER_SKILL, skill
        rng.shuffle(causes)
        n_heldout = int(TRACES_PER_SKILL * HELDOUT_SHARE)
        for i, cause in enumerate(causes):
            trace, label = build_trace(rng, skill, cause, i)
            trace["split"] = "heldout" if i < n_heldout else "mining"
            traces.append(trace)
            labels[trace["id"]] = label

    with open(DATA_DIR / "traces.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for t in traces:
            f.write(json.dumps(t) + "\n")

    # Labeled eval set: stratified so every cause appears at least once.
    by_cause: dict = {}
    for t in traces:
        by_cause.setdefault((t["skill"], t["injected_cause"]), []).append(t["id"])
    picked = [rng.choice(ids) for _, ids in sorted(by_cause.items(), key=lambda kv: str(kv[0]))]
    rest = [t["id"] for t in traces if t["id"] not in set(picked)]
    picked += rng.sample(rest, EVAL_SIZE - len(picked))
    with open(DATA_DIR / "eval_labels.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for tid in picked:
            f.write(json.dumps({"id": tid, "label": labels[tid]}) + "\n")

    print(f"wrote {len(SKILLS)} skills, {len(traces)} traces, {len(picked)} eval labels to {DATA_DIR}")


if __name__ == "__main__":
    main()
