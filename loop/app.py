"""Demo web app. Run with `python -m loop.app` and open http://127.0.0.1:8000."""

from __future__ import annotations

import difflib
import os
import re
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from loop import llm, metrics
from loop.data import DATA_DIR, ROOT, load_eval_labels
from loop.pipeline import State, build
from loop.replay import replay
from loop.review import APPROVED, EDITED, REJECTED, ReviewLog
from loop.verdict import FINAL_OUTPUT, VERDICTS

HERE = Path(__file__).resolve().parent
VERDICT_CLASS = {v: v.lower().replace(" ", "-") for v in VERDICTS}


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader so the optional LLM settings work without another dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            if value.strip():
                os.environ.setdefault(key.strip(), value.strip())


def ticks(text: str) -> Markup:
    """Escape text and render `backtick` spans as inline code."""
    return Markup(re.sub(r"`([^`]+)`", r"<code>\1</code>", str(escape(text or ""))))


def side_by_side(old: str, new: str) -> list[dict]:
    """Rows for a two-column diff: {kind, left, right} with kind in equal/replace/delete/insert."""
    a, b = old.splitlines(), new.splitlines()
    rows = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            rows += [{"kind": "equal", "left": a[i], "right": b[j1 + k]} for k, i in enumerate(range(i1, i2))]
        else:
            left, right = a[i1:i2], b[j1:j2]
            for k in range(max(len(left), len(right))):
                rows.append({"kind": tag, "left": left[k] if k < len(left) else None,
                             "right": right[k] if k < len(right) else None})
    return rows


def create_app(data_dir: Path = DATA_DIR, reviews_path: Path | None = None, use_llm: bool | None = None) -> FastAPI:
    state: State = build(data_dir, use_llm=use_llm)
    labels = load_eval_labels(data_dir)
    log = ReviewLog(reviews_path or data_dir / "reviews.jsonl")

    app = FastAPI(title="Skill Fix Loop")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["ticks"] = ticks
    templates.env.globals.update(
        verdicts=VERDICTS, vclass=VERDICT_CLASS, llm_on=state.judge_enabled, llm_model=llm.model(),
        FINAL_OUTPUT=FINAL_OUTPUT,
    )

    def render(request: Request, name: str, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, ctx)

    def skill_row(name: str) -> dict:
        counts = state.verdict_counts(name)
        total = sum(counts.values())
        latest = log.latest()
        drafts = [d for d in state.drafts.values() if d.skill == name]
        return {
            "name": name,
            "description": state.skills[name].description,
            "total": total,
            "mining": len(state.traces_for(name, "mining")),
            "heldout": len(state.traces_for(name, "heldout")),
            "counts": counts,
            "bar": [(v, counts.get(v, 0), 100 * counts.get(v, 0) / total) for v in VERDICTS if counts.get(v)],
            "success_rate": counts.get("Success", 0) / total if total else 0,
            "causes": len(state.causes[name]),
            "pending": sum(1 for d in drafts if d.id not in latest),
            "workflows": len(state.workflows[name]),
        }

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        return render(request, "overview.html", rows=[skill_row(n) for n in state.skills])

    @app.get("/skills/{name}", response_class=HTMLResponse)
    def skill_detail(request: Request, name: str):
        if name not in state.skills:
            raise HTTPException(404, "Unknown skill")
        latest = log.latest()
        causes = [{
            "cause": c,
            "draft": state.drafts[c.id],
            "decision": latest.get(c.id, {}).get("decision"),
            "examples": [(tid, state.verdicts[tid], c.raw_errors[c.trace_ids.index(tid)]) for tid in c.examples],
        } for c in state.causes[name]]
        triage = [(tid, state.verdicts[tid]) for tid in state.triage[name]]
        return render(request, "skill.html", row=skill_row(name), causes=causes, triage=triage,
                      workflows=state.workflows[name])

    @app.get("/proposals/{draft_id}", response_class=HTMLResponse)
    def proposal(request: Request, draft_id: str, saved: str | None = None):
        d = state.drafts.get(draft_id)
        if not d:
            raise HTTPException(404, "Unknown proposal")
        cause = next(c for c in state.causes[d.skill] if c.id == d.cause_id)
        decision = log.latest().get(d.id)
        diff_text = decision["diff"] if decision and decision["decision"] == EDITED else d.diff
        return render(request, "proposal.html", d=d, cause=cause, rows=side_by_side(d.old_text, d.new_text),
                      cited=[(tid, state.verdicts[tid]) for tid in d.cited], decision=decision,
                      diff_text=diff_text, saved=saved)

    @app.post("/proposals/{draft_id}")
    def review(draft_id: str, action: str = Form(...), diff: str = Form("")):
        d = state.drafts.get(draft_id)
        if not d:
            raise HTTPException(404, "Unknown proposal")
        diff = diff.replace("\r\n", "\n")
        if action == "approve":
            decision = APPROVED if diff.strip() == d.diff.strip() or not diff.strip() else EDITED
            log.record(d.id, d.skill, decision, diff if decision == EDITED else d.diff)
        elif action == "reject":
            log.record(d.id, d.skill, REJECTED, d.diff)
        else:
            raise HTTPException(400, "action must be approve or reject")
        return RedirectResponse(f"/proposals/{draft_id}?saved=1", status_code=303)

    @app.get("/traces/{trace_id}", response_class=HTMLResponse)
    def trace_view(request: Request, trace_id: str):
        t = state.traces.get(trace_id)
        if not t:
            raise HTTPException(404, "Unknown trace")
        return render(request, "trace.html", t=t, v=state.verdicts[trace_id], cause=state.cause_of(trace_id),
                      label=labels.get(trace_id))

    @app.get("/results", response_class=HTMLResponse)
    def results(request: Request):
        res = replay(state, log.approved())
        correct, n = metrics.verdict_accuracy(state, labels)
        decisions = Counter(e["decision"] for e in log.latest().values())
        return render(request, "results.html", results=list(res.values()), entries=list(reversed(log.entries())),
                      accuracy=(correct, n), purity=metrics.cluster_purity(state),
                      judge=metrics.judge_eval(state, labels), decisions=decisions,
                      drafts=state.drafts, total_drafts=len(state.drafts))

    @app.post("/results/reset")
    def reset():
        log.clear()
        return RedirectResponse("/results", status_code=303)

    return app


def main() -> None:
    import uvicorn

    load_dotenv()
    host, port = "127.0.0.1", int(os.environ.get("PORT", "8000"))
    print(f"Starting Skill Fix Loop at http://{host}:{port} (set PORT to use another port)")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
