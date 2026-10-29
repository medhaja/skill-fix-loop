# Skill Fix Loop: from failed skill runs to reviewable edits

**One-liner:** A local tool that reads agent traces for one skill, assigns each run a verdict, groups the failures by cause, drafts a diff to the skill file with the supporting traces attached, and lets a human approve it and see the success rate before and after.

I built this on my own, using only public information and synthetic data. I have no access to Nessie's data, systems or users.

## Problem (outside-in)

From the outside, Nessie has shipped the measurement half of the skill loop quickly. The [changelog](https://nessielabs.com/changelog) shows skill usage and success analytics (Aug 31), agents editing installed skills with changes saved back (Sep 9), team skill sharing for Claude Code and Codex (Sep 10), and skill bundles (Oct 9). The [Skill Evals doc](https://nessielabs.com/docs/skills-evals) gives each run a verdict: Success, Skill error, Unexpected behavior, Other error or Unknown. Agents can also send feedback through a submit-skill-feedback skill.

The public docs don't explain how a verdict is reached. They also don't describe an automated step that turns failures into fixes. The [job post](https://www.workatastartup.com/jobs/94429) describes that step as core work: "mine traces for failures and repeated workflows, and propose reviewable edits back." The [Recursive Company essay](https://nessielabs.com/blog/the-recursive-company) says "nobody has mapped the full space" of what traces can be used for. Nessie may already have some of this internally. This prototype is my guess at the shape of the missing step.

## Users and the job to be done

- **Skill owner** (an engineer on a team that shares skills): "My `deploy-preview` skill fails about 30% of the time. Show me why, with evidence, and give me a fix I can review in two minutes."
- **Agent:** files feedback after a run. That feedback counts as one signal among several. It does not settle the verdict on its own.

## Goals / Non-goals

**Goals**
- Make verdicts explainable: every verdict shows which rule or judge decided it.
- Group failures into a small number of named causes.
- Produce one diff per cause, with links to the traces that support it.
- Keep a human in the loop: approve, edit or reject.
- Show the success rate before and after on held-out traces.

**Non-goals**
- Editing skills automatically without review.
- Matching Nessie's real trace format or verdict logic.

## Prototype scope

The repo will contain:
- `data/generate.py`: a seeded generator for synthetic skills and traces.
- `loop/`: the verdict, clustering, drafting and replay modules.
- A FastAPI app with server-rendered pages.
- `tests/`: pytest unit tests plus a small labeled eval set.
- A README with a 2-minute demo script.

## Functional requirements

1. FR1: Load 3 skills (Markdown, `SKILL.md` style) and about 600 traces from JSONL.
2. FR2: Assign each trace a verdict from the five-value set, plus a `reason` naming the rule that fired. Rules cover tool exit codes, error strings, missing expected output, retries above a threshold and agent feedback.
3. FR3: Traces no rule can decide get `Unknown`. If an LLM key is set, an LLM judge may reclassify them, and its output is stored separately as `judge_verdict`.
4. FR4: Group non-success traces into causes using a normalized error signature (strip paths, IDs and numbers), then TF-IDF and agglomerative clustering. Each cause gets a label, a count and 3 example traces.
5. FR5: For each cause, draft a unified diff to the skill file plus a rationale that cites trace IDs. The default is a mock drafter: a deterministic template keyed on the cause. LiteLLM is used only if a key is present.
6. FR6: A reviewer can approve, edit the diff text or reject. The decision is written to `reviews.jsonl` with a timestamp.
7. FR7: Replaying approved edits against held-out traces reports the success rate before and after, per skill.
8. FR8: Everything runs offline with `make demo` or `python -m loop.app`, with no API key.

## Demo UI

1. **Skills overview:** a table with each skill's run count, verdict breakdown bar and success rate.
2. **Skill detail:** failure causes ranked by count. Each shows its label, signature and 3 example traces, with the verdict reason visible.
3. **Proposed edit:** a side-by-side diff, the rationale with clickable trace IDs, and Approve / Edit / Reject buttons.
4. **Trace viewer:** the raw steps (prompt, tool calls, outputs, feedback) and the line where the verdict rule fired.
5. **Results:** before and after success rates on held-out traces, plus a review log.

## Data

The generator is seeded and reproducible. It creates:
- **3 skills:** `deploy-preview`, `write-migration` and `summarize-meeting`.
- **About 600 traces**, 200 per skill, split 70/30 into mining and held-out sets.
- **Trace shape:** `{id, skill, harness: claude_code|codex, steps[{type, tool, input, output, exit_code}], final_output, agent_feedback?, injected_cause}`.
- **Injected causes:** 3 to 4 per skill. Examples are a missing env var step, a wrong CLI flag after a version change, and a skill that never says which branch to use.
- **Edge cases:**
  - traces that succeed despite errors partway through
  - agent feedback that contradicts the exit code
  - empty or truncated traces
  - one cause with only 4 examples
  - near-duplicate error strings with different IDs
  - one "repeated workflow" pattern with no failure, which should be flagged as a candidate new skill but not fixed

Replay is simulated. Each injected cause has a fix marker. A held-out trace with that cause counts as fixed if the approved edit contains the marker. This is a stand-in for re-running real agents, and I'll label it that way in the UI.

## Architecture

```
traces.jsonl -> verdict (rules) -> [optional LLM judge on Unknown]
            -> signature + cluster -> drafter (mock | LiteLLM)
            -> review queue -> replay on held-out -> results
```

**Plain code** handles verdicts, signatures, clustering and replay. These steps need to be cheap, repeatable and easy to explain. If a verdict can't be traced back to a rule, nobody will trust it.

**An LLM** helps in two narrow places: judging traces that are truly ambiguous, and writing the wording of a skill edit. Both are optional and fall back to a mock, and both outputs are kept separate from the rule-based ones.

This follows the pattern I used at Bizmetric on an ADF-to-PySpark accelerator: deterministic translation, an LLM check on the output, then automated repair. The reported results there were a 90% cut in manual effort and 70% lower operating cost. The human approval step comes from Isocline, my open-source multi-agent workflow builder.

## Tech choices

- **Python and FastAPI with Jinja templates:** a single process and no frontend build. I've shipped FastAPI services several times.
- **scikit-learn** for TF-IDF and clustering: fast and predictable at this scale.
- **LiteLLM** for optional model calls: I've used it to route between Claude and OpenAI models, so either provider plugs in.
- **JSONL files instead of a database:** easy to inspect and diff.

I'm not using Nessie's real stack (desktop apps, daemon, MCP) here, because the point is the loop logic.

## How we'd know it works

- **Verdict accuracy:** at least 90% on a 60-trace labeled set, checked in tests.
- **Cluster purity:** at least 85% when causes are compared with the `injected_cause` labels.
- **Drafter coverage:** every cluster with 5 or more traces gets a diff that cites at least 3 trace IDs.
- **Held-out success rate:** goes up after approval, and only for traces whose cause was fixed. Rejected edits change nothing.
- **LLM judge eval:** on the Unknown subset, report agreement with the labels and the share of traces it moves out of Unknown. It must never overwrite rule-based verdicts.
- **Tests:** pytest covers each module and one end-to-end run using the mock drafter.

## Risks and open questions

- Simulated replay overstates real gains. How does Nessie measure a skill change today? Is it by comparing versions as they run in production?
- Real traces from different harnesses look very different. Signatures may need a per-harness normalizer.
- How much weight should agent feedback get compared with outcomes? Agents can be wrong about their own success.
- Edits to shared skills raise questions about who is allowed to approve them.
- On my side: I'm based in Bengaluru and would need H-1B sponsorship. I'm open to relocating to SF.

## Build plan

1. Write the data generator with fixed seeds and edge cases, plus the labeled eval subset.
2. Build the verdict rules, store `reason` on each trace, and add tests.
3. Build signature normalization and clustering, plus the purity test.
4. Write the mock drafter templates. Add the LiteLLM drafter and judge behind an env flag.
5. Add the review queue and `reviews.jsonl`.
6. Build replay and the before/after metrics.
7. Build the FastAPI pages for the 5 screens.
8. Add `make demo`, the README walkthrough and screenshots.

## Out of scope for the prototype

- Real connectors and real trace formats.
- Syncing skills across harnesses.
- Permissions and team sharing.
- Re-running real agents for replay.
- Turning repeated workflows into new skills, beyond flagging them.
- Deployment.
