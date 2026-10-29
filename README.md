# Skill Fix Loop

**Run the demo:**

```bash
make demo        # or: pip install -r requirements.txt && python -m loop.app
```

Then open http://127.0.0.1:8000. No API key needed. If port 8000 is taken, run `PORT=8001 python -m loop.app`
(PowerShell: `$env:PORT=8001; python -m loop.app`). Python 3.11+.

> Independent prototype built from public information and synthetic data. Not affiliated with Nessie.

## What it is

A local tool that reads agent traces for a skill, gives every run a verdict with the rule that decided it, groups
the failures into a few named causes, drafts one diff to the skill's `SKILL.md` per cause with the supporting
traces attached, and lets a person approve, edit or reject each diff. It then reports the success rate before and
after the approved edits on held-out traces. Everything runs offline on 600 synthetic traces for 3 made-up skills.

![Skills overview](docs/screenshots/1-overview.png)

## The problem it targets

From the outside, Nessie has shipped the measurement half of the skill loop: skill usage and success analytics,
agents editing installed skills, team skill sharing and skill bundles ([changelog](https://nessielabs.com/changelog)),
and per-run verdicts of Success, Skill error, Unexpected behavior, Other error or Unknown
([Skill Evals docs](https://nessielabs.com/docs/skills-evals)).

The public docs don't describe how a verdict is reached, or an automated step that turns failures into fixes. The
[job post](https://www.workatastartup.com/jobs/94429) describes that step as core work ("mine traces for failures
and repeated workflows, and propose reviewable edits back"), and the
[Recursive Company essay](https://nessielabs.com/blog/the-recursive-company) says nobody has mapped the full space
of what traces can be used for. Nessie may already have some of this internally. This is my guess at the shape of
that missing step, built only from public information.

## Two-minute demo

1. **Skills** (`/`): three skills with run counts, a verdict breakdown bar and success rate. `write-migration`
   carries a "candidate new skill" tag.
2. Open **deploy-preview**. Failures in the mining set are grouped into 3 causes (missing `VERCEL_TOKEN`, a CLI
   flag that a newer version removed, deploying from `main`), each with its signature, 3 example traces and the
   verdict reason. Unknown traces sit apart under "Needs triage".
3. Click **Review edit** on the `--preview` cause. You get a side-by-side diff of `SKILL.md`, a rationale with
   clickable trace IDs, and Approve / Reject. You can edit the unified diff in the text box before approving.
4. Click a trace ID (try `dep-086-3be2`). The trace viewer shows each step, highlights the step where the verdict
   rule fired, and shows that the agent said "success" while the exit code was 2. The exit code wins.
5. Approve a few edits and open **Results**. Held-out success rates go up only for the causes you approved;
   rejected edits change nothing. The review log lists each decision with a timestamp (`data/reviews.jsonl`).
6. Open **write-migration** to see the repeated `pg_dump → pg_dump → diff` workflow. It's flagged as a candidate
   for a new skill, not "fixed".

| Cause detail | Proposed edit | Trace viewer | Results |
|---|---|---|---|
| ![](docs/screenshots/2-skill.png) | ![](docs/screenshots/3-proposal.png) | ![](docs/screenshots/4-trace.png) | ![](docs/screenshots/5-results.png) |

## How it works

```
traces.jsonl -> verdict (rules) -> [optional LLM judge on Unknown]
            -> signature + cluster -> drafter (templates | LiteLLM)
            -> review queue -> simulated replay on held-out -> results
```

- **Verdicts** (`loop/verdict.py`): ordered rules, and the first match wins. Empty or truncated traces are
  Unknown. More than 3 identical calls is Unexpected behavior. If the final tool call has a non-zero exit, the
  verdict is Skill error, or Other error when the error looks environmental (lock timeout, connection refused).
  Error text in the final output is Skill error. A missing expected output (declared in the skill's frontmatter)
  is Unexpected behavior. A clean run with negative agent feedback is Unknown, because feedback alone never
  decides. Every verdict stores its rule, a reason and the step it fired on.
- **Causes** (`loop/cluster.py`): each failure's error line is normalized (paths, IDs, numbers and file names
  stripped), vectorized with TF-IDF and grouped per skill with agglomerative clustering (cosine distance, average
  linkage, fixed threshold).
- **Drafts** (`loop/drafter.py`): by default, a small library of templates matched against the error text (missing
  env var → pre-check, renamed flag → replace it, missing output → require it, 429 loop → backoff, and so on), with
  a generic "known failure" note as the fallback. Each draft is a unified diff plus a rationale citing up to 5
  trace IDs.
- **Review** (`loop/review.py`): decisions are appended to `data/reviews.jsonl`, and the latest one per draft wins.
  Nothing is written back to the skill files.
- **Replay** (`loop/replay.py`): *simulated*. Each injected cause in the synthetic data has a fix marker (e.g.
  `--target=preview`). A held-out failure counts as fixed if an approved diff for its skill adds that marker. This
  is a stand-in for re-running agents, and the UI labels it as such.

### Optional LLM

Copy `.env.example` to `.env`, set `LLM_MODEL` (any [LiteLLM](https://github.com/BerriAI/litellm) model string)
and the matching provider key, then `pip install -r requirements-llm.txt`. With that set:
- an LLM judge looks at the ambiguous Unknown traces and stores its answer as `judge_verdict`, next to the rule
  verdict and never replacing it;
- the drafter asks the model for the revised `SKILL.md`, and falls back to the template if the call fails.

## Data

`python data/generate.py` (seeded) rebuilds everything in `data/`: 3 skills (`deploy-preview`, `write-migration`,
`summarize-meeting`), 600 traces (200 per skill, split 70% mining / 30% held-out) and a 60-trace labeled eval set.
Each trace has 3 or 4 injected causes per skill, plus these edge cases:
- runs that succeed despite errors partway through;
- agent feedback that contradicts the exit code;
- empty and truncated traces;
- a cause with only 4 examples (lock timeout);
- near-duplicate errors with different IDs;
- one repeated workflow with no failure.

All of it is invented. The eval labels are the outcomes the generator intended, not independent human labels.

## Tests

```bash
make test        # or: python -m pytest -q
```

32 tests cover every module and one end-to-end run with the template drafter. Current numbers on the synthetic data:

| Check | Target | Result |
|---|---|---|
| Verdict accuracy on the 60-trace eval set | ≥ 90% | 57/60 (95%). The 3 misses are ambiguous-feedback runs the rules leave as Unknown |
| Cluster purity vs. injected causes | ≥ 85% | 100% |
| Every cause with ≥ 5 traces gets a diff citing ≥ 3 traces | all | all 8 |
| Held-out success goes up only for approved causes; rejected edits change nothing | yes | yes |
| LLM judge never overwrites rule verdicts | yes | yes (tested with a stubbed judge) |

## Limitations

- **The data is synthetic and easy.** The error strings were written to be separable, so 100% purity says the
  pipeline works, not that it would hold up on real traces from different harnesses. Real traces would likely need
  a normalizer per harness.
- **Replay is simulated.** Fix markers stand in for re-running agents and overstate real gains.
- **The template drafter only knows the failure shapes in this dataset.** Anything else gets a generic note. The
  LLM drafter is the general path, but I haven't evaluated it here.
- **The verdict rules are my guess.** They don't match Nessie's real verdict logic or trace format.
- **Approved diffs are not applied to the skill files.** There are no permissions or multi-reviewer approval either.

## Next steps

- Run the LLM judge on the Unknown subset and report agreement against independent human labels.
- Replace simulated replay with real reruns of a pinned agent on held-out tasks, comparing skill versions.
- Tune the clustering threshold per skill and merge near-identical causes across skills.
- Turn flagged repeated workflows into draft skills for review.
- Decide who may approve edits to a shared skill.
