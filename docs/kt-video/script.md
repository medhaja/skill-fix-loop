# Skill Fix Loop: KT video script

Narration is written the way it should be spoken (for example "L-L-M", "T-F I-D-F", "Jason" for JSON, "ver-sell" for Vercel). The
tts step reads only the text under **Narration**. Beats are keyed to phrases in the narration.

---

## Scene 1: The missing step
`01 / The problem`

**Narration:**
Nessie already measures skills. Its public changelog shows success analytics per skill. Its Skill ee-vals docs give
every run a verdict: Success, Skill error, Unexpected behavior, Other error, or Unknown. What the public docs don't
describe is the next step: turning those failures into fixes a person can review. Skill Fix Loop is a prototype of
that step. It runs locally, on synthetic data, and it isn't affiliated with Nessie.

**On screen:**
- Title "Skill Fix Loop" fades in, then moves to the top.
- At "already measures skills": a left panel labeled "Measure" appears, with a small source tag "changelog".
- At "a verdict": five verdict chips appear one by one, in their verdict colors, with the tag "Skill Evals docs".
- At "the next step": a right panel labeled "Fix" appears as a dashed outline with a question mark.
- At "Skill Fix Loop is a prototype": the dashed panel fills in with "failures → causes → reviewable edit".
- At "isn't affiliated": a footer appears: "Independent prototype built from public information and synthetic
  data. Not affiliated with Nessie."

**Sources:**
- Changelog success analytics; the five verdicts: `PRD.md:9`
- Public docs don't describe the failures-to-fixes step: `PRD.md:11`, `README.md:30-32`
- Local and synthetic data: `README.md:16-20`, `README.md:104`
- Not affiliated: `README.md:12`

---

## Scene 2: Architecture
`02 / Architecture`

**Narration:**
Here's the shape. Traces come in as Jason lines. Rules give every run a verdict. Failures are grouped into
causes, and each cause gets one drafted edit to the skill file. All of that runs once, at startup. Then a person
approves or rejects each edit, and replay reports success before and after, on held-out traces. An L-L-M can help
in just two places: judging runs the rules leave as Unknown, and wording the edit. Both stay off unless a model is
configured.

**On screen:**
- Boxes left to right: `traces.jsonl` → `classify()` → `cluster_failures()` → `draft()` → `ReviewLog` → `replay()`.
- Each arrow animates as its stage is named: "verdict" at "Rules", "cluster" at "grouped into causes", "draft"
  at "drafted edit".
- At "run once, when the app starts": a bracket labeled `build()` · `pipeline.py` spans the first four boxes.
- At "a person approves or rejects": the `ReviewLog` box lights up with a person icon; then the `replay()` box
  lights up and shows a small before/after bar.
- At "just two places": two dashed boxes labeled "optional LLM judge" (under `classify()`) and "optional LLM
  drafter" (under `draft()`) appear.
- At "stay off": both dashed boxes dim, with the label `LLM_MODEL unset → rules + templates`.

**Sources:**
- Load traces from JSONL: `loop/data.py:397-399`
- Verdicts, judge, clusters and drafts built at startup: `loop/pipeline.py:321-346`, `loop/app.py:59-60`
- Review and replay on held-out traces: `loop/app.py:126-139`, `loop/app.py:149-151`, `loop/replay.py:332-350`
- Plain code for verdicts, clustering and replay: `PRD.md:84`
- Judge only on ambiguous Unknown traces: `loop/pipeline.py:328-332`
- LLM drafter: `loop/drafter.py:209-224`
- Off unless `LLM_MODEL` is set and litellm is installed: `loop/llm.py:370-381`

---

## Scene 3: One run gets a verdict
`03 / Request flow: verdict`

**Narration:**
Let's follow one run, trace dep zero eight six. The agent checks the branch, installs, builds, then runs ver-sell
deploy with dash dash preview. That exits with code two, because the newer tool removed the flag. The agent still
reports success. Verdict rules run in order, and the first match wins. Rule four looks at the final tool call. A
non-zero exit is a Skill error, whatever the agent said, unless the error looks environmental. The verdict records
the rule, a reason, and the step where it fired.

**On screen:**
- A trace card titled `dep-086-3be2` with the steps: prompt, `git branch --show-current`, `npm ci`,
  `npm run build`, `vercel build`, `vercel deploy --prebuilt --preview`.
- At "checks the branch, installs, builds": a token moves down the steps, each with a green `exit 0`.
- At "exits with code two": the last step turns red, showing `exit 2` and the error line
  `Error: unknown or unexpected option: --preview … Use --target=preview instead.`
- At "still reports success": a feedback bubble "Deployed the preview as asked." appears and is then struck
  through.
- At "Verdict rules run in order": the card slides left and a code focus on `loop/verdict.py` (lines 79–88)
  appears.
- At "Rule four": lines 79–81 are highlighted. At "non-zero exit": lines 87–88. At "whatever the agent said":
  line 82. At "unless the error looks environmental": lines 83–86 (the Other error branch).
- At "records the rule": a verdict chip appears with `Skill error · rule: final_exit_code · step 5`.

**Sources:**
- Trace contents, exit 2, error text, feedback "success": `data/traces.jsonl:87`
- Rules in order, first match wins: `loop/verdict.py:3-5`, `loop/verdict.py:52-112`
- Rule 4, final tool call exit code, "the exit code wins": `loop/verdict.py:79-88`
- Environmental errors (lock timeout, connection refused, ...) become Other error instead: `loop/verdict.py:26-29`,
  `loop/verdict.py:83-86`
- Stores rule, reason and step: `loop/verdict.py:35-42`
- Actual result for this trace (`final_exit_code`, step_index 5): checked by running `loop.pipeline.build()`

---

## Scene 4: From failures to causes
`04 / Request flow: causes`

**Narration:**
Next, causes. Each error line is normalized. Paths, IDs and numbers are stripped, so runs that differ only in
details share one signature. Signatures become T-F I-D-F vectors, and agglomerative clustering groups them, one
skill at a time, using only failures from the mining split. For deploy-preview, that gives three causes: a missing
Ver-sell token in twenty-two runs, the removed flag in eighteen, and deploying from main in seven.

**On screen:**
- The red error line from scene 3 moves to the center.
- At "normalized": `42.4.6` morphs into `<n>`, and the line becomes lowercase, giving the signature
  `error: unknown or unexpected option: --preview (vercel cli <n>). use --target=preview instead.`
- At "share one signature": 18 small dots, each labeled with a short trace ID, slide into one group.
- At "T-F I-D-F vectors": a small code focus on `loop/cluster.py` lines 195–199, with `metric="cosine"`,
  `linkage="average"` and `distance_threshold` highlighted.
- At "mining split": a split bar `140 mining · 60 held-out` with the mining part highlighted.
- At "three causes": a ranked list appears:
  - `c1` · 22 · `Environment variable VERCEL_TOKEN is not set`
  - `c2` · 18 · `unknown or unexpected option: --preview` (highlighted, since it holds our trace)
  - `c3` · 7 · `refusing to deploy protected branch 'main'`

**Sources:**
- Error line taken from the step where the rule fired: `loop/verdict.py:115-127`
- Normalization (URLs, file names, paths, IDs, hex, numbers): `loop/cluster.py:148-165`
- TF-IDF plus agglomerative clustering (cosine, average linkage, threshold 0.6), per skill: `loop/cluster.py:145`,
  `loop/cluster.py:184-199`, `loop/pipeline.py:334-338`
- Only non-Success, non-Unknown mining traces are clustered: `loop/pipeline.py:335-337`
- 140 mining / 60 held-out per skill, and the 3 causes with counts 22 / 18 / 7: checked by running
  `loop.pipeline.build()`

---

## Scene 5: Draft, review, replay
`05 / Request flow: fix`

**Narration:**
Now the fix. The default drafter is a set of templates matched against the error text. This one recognizes a
renamed flag, so it rewrites step four of the skill file. You get a one-line diff, and a rationale citing five
trace IDs you can click. A reviewer approves, edits, or rejects. Each decision is appended to reviews dot Jason L
with a timestamp, and the latest one wins. Replay then checks the held-out traces. Approve only this edit, and
deploy-preview goes from forty to forty-four successes out of sixty. Approve all three, and it reaches
fifty-seven.

**On screen:**
- At "set of templates": a short list of template names (env var, renamed flag, protected branch, file name,
  missing output, rate limit, …), with "renamed flag" highlighted and its regex shown in monospace.
- At "rewrites step four": a diff panel titled `skills/deploy-preview/SKILL.md`:
  `- 4. Run \`vercel deploy --prebuilt --preview\` …` in red,
  `+ 4. Run \`vercel deploy --prebuilt --target=preview\` …` in green.
- At "rationale": the rationale text with the 5 cited IDs as chips (`dep-060-bf16`, `dep-062-c2d0`,
  `dep-071-8b79`, `dep-086-3be2`, `dep-094-e095`); `dep-086-3be2` glows.
- At "approves, edits the diff, or rejects it": three buttons; Approve is pressed.
- At "appended to reviews dot Jason L": a JSONL row slides into a log panel:
  `{"timestamp": "…", "draft_id": "deploy-preview-c2", "decision": "approved", …}`.
- At "checks the held-out traces": before/after bars for deploy-preview held-out: 40/60 → 44/60.
- At "Approve all three": a third bar grows to 57/60.

**Sources:**
- Template library matched on the raw error: `loop/drafter.py:164-173`, `loop/drafter.py:192-200`
- Renamed-flag template replaces the flag: `loop/drafter.py:108-115`
- Rationale text, up to 5 cited IDs: `loop/drafter.py:19`, `loop/drafter.py:184-189`
- "18 of 47 failed runs", the diff and the cited IDs: checked by running `loop.pipeline.build()`
- Approve / edit / reject: `loop/app.py:126-139`
- Appended with a timestamp, latest wins: `loop/review.py:249-279`
- Replay with fix markers: `loop/replay.py:301-350`
- 40 → 44 (only `deploy-preview-c2`) and 57 (all three): checked by calling `loop.replay.replay()`

---

## Scene 6: Run it
`06 / Run the demo`

**Narration:**
To run it, type make demo. It installs the pinned requirements and starts the app on port eight thousand, with
no API key. Five pages follow the loop: skills, skill detail, proposed edit, trace viewer, and results. For the
L-L-M path, set a model in a dot E-N-V file.

**On screen:**
- A terminal card: `$ make demo` → `Starting Skill Fix Loop at http://127.0.0.1:8000`.
- At "five pages": five screenshot thumbnails from `docs/screenshots/` appear in a row, each captioned: Skills ·
  Skill detail · Proposed edit · Trace · Results.
- At "dot E-N-V file": a small card with `LLM_MODEL=<provider/model>` and `<PROVIDER>_API_KEY=<API_KEY>`.

**Sources:**
- `make demo` = install + `python -m loop.app`: `Makefile:3-7`
- Pinned requirements: `requirements.txt`
- Port 8000 and the startup message: `loop/app.py:171-173`
- Five pages: `loop/app.py:95-157`, `README.md:37-61`
- Optional LLM via `.env`: `loop/app.py:28-36`, `.env.example:1-6`, `README.md:84-90`

---

## Scene 7: Gotchas and limitations
`07 / Gotchas`

**Narration:**
Some things to know before you trust the numbers. Agent feedback never decides on its own. A clean run where the
agent reports failure stays Unknown, under Needs triage. Replay is simulated. A held-out failure counts as fixed
if an approved diff adds that cause's fix marker, which overstates real gains. The data is synthetic and easy, so a
hundred percent cluster purity proves the plumbing, not real-world accuracy. Approved diffs are never written back
to the skill file. And repeated workflows, like P-G dump, P-G dump, diff, are flagged as new skill candidates, not
fixed.

**On screen:** one card per gotcha, each replacing the previous one:
1. At "agent feedback": a "with/without" card. Clean run plus feedback "failure" → `Unknown` (not
   `Skill error`), with the tag "Needs triage".
2. At "replay is simulated": `FIX_MARKERS` excerpt (`"wrong_cli_flag": "--target=preview"`) with a "Simulated"
   warning badge.
3. At "synthetic and easy": the metrics `purity 100%` and `verdict accuracy 57/60`, with the note "labels come
   from the generator".
4. At "never written back": `SKILL.md` with a lock icon and the label "decision logged, file unchanged".
5. At "repeated workflows": `pg_dump --schema-only → pg_dump --schema-only → diff -u` · 19 runs ·
   tag "candidate new skill".

**Sources:**
- Feedback contradicts a clean outcome → Unknown: `loop/verdict.py:101-105`, `tests/test_verdict.py:59`
- Unknown traces listed under "Needs triage": `loop/pipeline.py:339`, `loop/templates/skill.html:63-64`
- Simulated replay, fix markers, overstates gains: `loop/replay.py:1-8`, `loop/replay.py:301-311`,
  `README.md:127`
- Synthetic and easy, 100% purity: `README.md:124-126`; purity 1.0 and accuracy 57/60 checked by running
  `loop.metrics`
- Eval labels come from the generator: `README.md:104`
- Diffs not applied: `README.md:131`; `loop/review.py` only appends to the log
- Repeated workflow (19 runs) flagged as a candidate: `loop/cluster.py:261-283`, `loop/templates/skill.html:54`,
  checked by running `loop.pipeline.build()`

---

## Scene 8: Recap and next steps
`08 / Recap`

**Narration:**
To recap. Every verdict names its rule. Failures become a few named causes. Each cause gets one diff, backed by
trace IDs. A person decides, and every decision is logged. And success is measured on held-out runs. Next steps:
real agent reruns instead of simulated replay, checking the judge against human labels, normalizers for each
harness, and deciding who may approve edits to shared skills. Thank you.

**On screen:**
- Five takeaways appear one by one, each with its accent color:
  1. Every verdict names its rule
  2. Failures → a few named causes
  3. One diff per cause, with cited traces
  4. A person decides; decisions are logged
  5. Success measured on held-out runs
- At "Next steps": four chips: "Real reruns" · "Judge vs. human labels" · "Per-harness normalizers" ·
  "Approval permissions".
- At "Thank you": the recap fades out and a closing card appears: "Thank you" and "Made by Medhaja H L", with the
  not-affiliated line below. The last scene holds 3 s after the audio so the card can be read.

**Sources:**
- Credit: the author named in the project instructions (no code claim).
- Takeaways: `loop/verdict.py:35-42`, `loop/cluster.py:184-223`, `loop/drafter.py:184-206`, `loop/review.py:249-263`,
  `loop/replay.py:332-350`
- Next steps: `README.md:133-139`, `PRD.md:111`
