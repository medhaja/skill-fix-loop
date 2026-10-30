"""Generate the voiceover with Kokoro (runs locally) and derive timing.json and captions.srt.

Usage:
    .venv/Scripts/python.exe tts.py            # all scenes
    .venv/Scripts/python.exe tts.py 3 5        # only scenes 3 and 5 (timing.json is rebuilt from all WAVs)
    .venv/Scripts/python.exe tts.py --timing   # no synthesis; rebuild timing.json, timing.js, captions.srt

Reads the **Narration:** block of each scene in script.md. Each sentence is synthesized as its own chunk,
so timing.json gets sentence-level and word-level timestamps (seconds from the start of the video).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "audio"
SR = 24000
VOICE = "af_heart"
PAD = 0.6  # seconds of silence after each scene
SPEED = 1.08  # slightly faster than default to keep the video under four minutes

# Narration is respelled for the voice; captions show the written form.
CAPTION_FORMS = [
    ("dep zero eight six", "dep-086"),
    ("dash dash preview", "--preview"),
    ("reviews dot Jason L", "reviews.jsonl"),
    ("Jason lines", "JSON lines"),
    ("a dot E-N-V file", "a .env file"),
    ("Skill ee-vals", "Skill Evals"),
    ("Ver-sell", "Vercel"),
    ("ver-sell", "vercel"),
    ("T-F I-D-F", "TF-IDF"),
    ("P-G dump", "pg_dump"),
    ("L-L-M", "LLM"),
]


def parse_script(path: Path = HERE / "script.md") -> list[dict]:
    text = path.read_text(encoding="utf-8")
    scenes = []
    for block in re.split(r"(?m)^(?=## Scene )", text)[1:]:
        head = re.match(r"## Scene (\d+): (.+)\n`([^`]+)`", block)
        narr = re.search(r"\*\*Narration:\*\*\n(.*?)\n\n", block, re.S).group(1)
        narr = " ".join(narr.split())
        scenes.append({"n": int(head.group(1)), "title": head.group(2).strip(), "chapter": head.group(3),
                       "narration": narr})
    return scenes


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


def caption_text(s: str) -> str:
    for spoken, written in CAPTION_FORMS:
        s = s.replace(spoken, written)
    return s


def trim(a: np.ndarray, lead: float = 0.08, tail: float = 0.22, threshold: float = 0.01) -> tuple[np.ndarray, int]:
    """Trim a sentence's silence down to a natural pause. Returns (audio, samples cut from the front)."""
    loud = np.flatnonzero(np.abs(a) > threshold)
    if not len(loud):
        return a, 0
    cut = max(0, loud[0] - int(lead * SR))
    return a[cut: min(len(a), loud[-1] + int(tail * SR))], cut


def synthesize(scene: dict, pipeline) -> list[dict]:
    """Write audio/scene_XX.wav; return sentence timings relative to the scene start."""
    chunks, out, t = [], [], 0.0
    for sent in sentences(scene["narration"]):
        raw_words, audio = [], []
        for r in pipeline(sent, voice=VOICE, speed=SPEED, split_pattern=None):
            a = r.audio.numpy() if hasattr(r.audio, "numpy") else np.asarray(r.audio)
            base = sum(len(x) for x in audio) / SR
            for tok in r.tokens or []:
                if tok.start_ts is not None and tok.text.strip():
                    raw_words.append((tok.text, base + tok.start_ts, base + (tok.end_ts or tok.start_ts)))
            audio.append(a)
        a, cut = trim(np.concatenate(audio))
        shift = t - cut / SR
        words = [{"w": w, "start": round(max(t, s + shift), 3), "end": round(max(t, e + shift), 3)}
                 for w, s, e in raw_words]
        out.append({"text": sent, "caption": caption_text(sent), "start": round(t, 3),
                    "end": round(t + len(a) / SR, 3), "words": words})
        chunks.append(a)
        t += len(a) / SR
    AUDIO.mkdir(exist_ok=True)
    sf.write(AUDIO / f"scene_{scene['n']:02d}.wav", np.concatenate(chunks), SR)
    (AUDIO / f"scene_{scene['n']:02d}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build_timing(scenes: list[dict]) -> dict:
    timing, start = {"fps": 30, "pad": PAD, "scenes": []}, 0.0
    for sc in scenes:
        wav = AUDIO / f"scene_{sc['n']:02d}.wav"
        dur = sf.info(wav).frames / SR
        sents = json.loads((AUDIO / f"scene_{sc['n']:02d}.json").read_text(encoding="utf-8"))
        timing["scenes"].append({
            "n": sc["n"], "title": sc["title"], "chapter": sc["chapter"],
            "start": round(start, 3), "audio": round(dur, 3), "duration": round(dur + PAD, 3),
            "sentences": sents,
        })
        start += dur + PAD
    timing["total"] = round(start, 3)
    return timing


def write_srt(timing: dict, path: Path) -> None:
    lines, i = [], 1
    for sc in timing["scenes"]:
        for s in sc["sentences"]:
            lines += [str(i), f"{srt_time(sc['start'] + s['start'])} --> {srt_time(sc['start'] + s['end'])}",
                      s["caption"], ""]
            i += 1
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> None:
    scenes = parse_script()
    timing_only = "--timing" in argv
    only = {int(a) for a in argv if a.isdigit()}
    todo = [] if timing_only else [s for s in scenes if not only or s["n"] in only]
    if todo:
        # Once the model is cached, skip the hub's network check (it can hang); the first run downloads it.
        if (Path.home() / ".cache/huggingface/hub/models--hexgrad--Kokoro-82M").exists():
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from kokoro import KPipeline

        pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
        for sc in todo:
            synthesize(sc, pipeline)
            print(f"scene {sc['n']:02d} done")
    timing = build_timing(scenes)
    (HERE / "timing.json").write_text(json.dumps(timing, indent=1), encoding="utf-8")
    # Same data as a script, so index.html also works when opened straight from disk.
    (HERE / "timing.js").write_text("window.TIMING = " + json.dumps(timing) + ";\n", encoding="utf-8")
    write_srt(timing, HERE / "captions.srt")
    for sc in timing["scenes"]:
        print(f"{sc['n']:02d} {sc['start']:7.2f}s  {sc['duration']:6.2f}s  {sc['title']}")
    print(f"total {timing['total']:.2f}s")


if __name__ == "__main__":
    main(sys.argv[1:])
