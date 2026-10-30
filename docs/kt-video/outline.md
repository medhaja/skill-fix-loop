# Skill Fix Loop: KT video outline

**Target length:** 3–4 minutes · **Audience:** Nessie founders and engineers seeing the code for the first time
· **Voice:** Kokoro `af_heart`

## Summary

Skill Fix Loop is a local, offline prototype of the step that comes after skill analytics: it reads agent traces
for one skill, gives every run one of five verdicts along with the rule that decided it, groups the failures
into a few named causes, drafts one diff per cause to the skill's `SKILL.md` with the supporting trace IDs, and
lets a person approve, edit or reject that diff. It then reports the success rate on held-out traces before and
after the approved edits. It's meant for a skill owner who wants to know why a shared skill fails and get a fix
they can review in two minutes. Everything runs on 600 synthetic traces for 3 made-up skills. The verdict rules,
template drafter and replay are deterministic, and an LLM judge and drafter are optional, used only when
`LLM_MODEL` is set.

## Scenes

### 1. The missing step (≈30 s)
- **Idea:** Nessie publicly shows verdicts and success rates per skill, but nothing public turns failures into
  reviewed fixes. This prototype is one guess at that step.
- **Visual:** two halves. On the left, "measure" (skill analytics and the five verdict chips: Success, Skill error,
  Unexpected behavior, Other error, Unknown). On the right, "fix", drawn as a dashed empty box that fills in with
  "failures → causes → reviewable edit". A small disclaimer line: synthetic data, not affiliated with Nessie.
- **Files:** `PRD.md` (Problem, Goals), `README.md` (The problem it targets)

### 2. Architecture: one pipeline, two optional LLM spots (≈35 s)
- **Idea:** plain code does verdicts, signatures, clustering and replay. An LLM is optional in exactly two places
  (judge on Unknown, edit wording), and its output is kept separate.
- **Visual:** architecture diagram: `traces.jsonl` → `classify` → `cluster_failures` → `draft` → `ReviewLog` →
  `replay` → Results. Arrows animate in the order data moves. Two dashed "optional LLM" boxes attach to verdict
  and drafter. `build()` in `pipeline.py` is outlined as the box that runs the first three stages once at startup.
- **Files:** `loop/pipeline.py:321-346`, `loop/llm.py:370-381`, `loop/app.py:59-62`

### 3. Trace one run: dep-086-3be2 gets a verdict (≈35 s)
- **Idea:** rules run in order and the first match wins. In this run the agent said "success", but the final
  `vercel deploy --prebuilt --preview` exited 2, so the exit code wins and the verdict is Skill error, recorded
  with its rule, reason and step.
- **Visual:** a trace card with the steps (git branch, npm ci, npm run build, vercel build, vercel deploy). The token
  moves down the steps, the last one turns red (exit 2), and the feedback bubble "Deployed the preview as asked"
  gets crossed out. Then a code focus on `verdict.py` rule 4 (≈12 lines) with the `said_success` note highlighted.
- **Files:** `data/traces.jsonl:87`, `loop/verdict.py:52-112` (rule 4 at 79-88)

### 4. From one failure to a cause (≈35 s)
- **Idea:** the error line is normalized (version numbers, IDs and paths stripped), so 18 different-looking errors
  become one signature. TF-IDF and agglomerative clustering group them per skill. For deploy-preview this gives 3
  causes: 22 for the missing VERCEL_TOKEN, 18 for the `--preview` flag and 7 for deploying from main.
- **Visual:** a raw error line morphs into its signature (`42.4.6` → `<n>`). Then 18 dots collapse into one
  cluster, and a ranked list of 3 causes with counts appears.
- **Files:** `loop/verdict.py:115-127`, `loop/cluster.py:145-223`

### 5. Draft, review, replay (≈45 s)
- **Idea:** a template matches the error text ("unknown option --preview … use --target=preview instead") and
  rewrites step 4 of SKILL.md. The rationale cites 5 trace IDs. A reviewer approves, edits or rejects, and the
  decision is appended to `reviews.jsonl`. Replay then counts a held-out failure as fixed if an approved diff adds
  that cause's fix marker.
- **Visual:** the real one-line diff (`- --preview` / `+ --target=preview`) with the rationale and cited IDs; an
  Approve button press appends a JSONL row; then before/after bars for held-out deploy-preview (40/60 → 44/60 when
  only this edit is approved, 57/60 with all three).
- **Files:** `loop/drafter.py:108-115,164-173,184-206`, `loop/app.py:126-139`, `loop/review.py:249-279`,
  `loop/replay.py:301-350`

### 6. Run it (≈20 s)
- **Idea:** one command, no key. Five pages map to the loop.
- **Visual:** terminal card with `make demo` → `http://127.0.0.1:8000`, then a strip of the 5 pages (Skills, Skill
  detail, Proposed edit, Trace, Results) using the existing screenshots, plus a note on the optional
  `LLM_MODEL` in `.env`.
- **Files:** `Makefile`, `loop/app.py:167-173`, `README.md`, `.env.example`, `docs/screenshots/*`

### 7. Gotchas and limitations (≈35 s)
- **Idea:** what to distrust and what's surprising:
  - Agent feedback never decides on its own: a clean run with negative feedback is left as Unknown ("Needs
    triage"), and the judge never overwrites a rule verdict.
  - Replay is simulated with fix markers, so it overstates real gains.
  - The data is synthetic and easy to separate, so 100% cluster purity and 57/60 verdict accuracy prove the plumbing
    works, not real-world quality. The eval labels come from the generator.
  - Approved diffs are never written back to `SKILL.md`, and there are no permissions.
  - Every cause gets a draft, even small ones (the lock-timeout cause has only 3 mining traces).
  - Repeated workflows (`pg_dump`, `pg_dump`, `diff` in write-migration) are flagged as new-skill candidates, not
    fixed.
- **Visual:** with/without cards, one gotcha at a time.
- **Files:** `loop/verdict.py:101-105`, `loop/pipeline.py:328-332`, `loop/replay.py:1-8`,
  `loop/review.py`, `loop/cluster.py:261-283`, `README.md` (Limitations)

### 8. Recap and next steps (≈20 s)
- **Idea:** 5 takeaways, plus next steps: real reruns instead of simulated replay, an LLM judge evaluated against
  human labels, per-harness normalizers, and approval permissions.
- **Visual:** recap list, then three next-step chips.
- **Files:** `README.md` (Next steps), `PRD.md` (Risks and open questions)

## Open questions

1. **Hero example:** I plan to trace `dep-086-3be2` (the wrong `--preview` flag, where agent feedback contradicts
   the exit code) end to end. Is that OK, or would you prefer the `VERCEL_TOKEN` cause (the largest one)?
2. **Mentioning Nessie's public sources:** should scene 1 name the changelog, the Skill Evals docs and the job post
   on screen (as small source labels), or only say "Nessie's public docs"?
3. **Screenshots:** OK to reuse `docs/screenshots/*.png` in scene 6? They contain only synthetic data.
4. **Replay numbers:** I'll show 40 → 44 of 60 (only the `--preview` edit approved) and mention 57 of 60 with all
   three deploy-preview edits. Should I keep both, or just one?
5. **Personal notes in PRD.md** (location and visa, past employers): I'll leave these out of the video. Confirm?
