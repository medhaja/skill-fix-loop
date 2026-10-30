# Walkthrough video

A 3:39 narrated walkthrough of Skill Fix Loop: the problem, the architecture, one trace (`dep-086-3be2`) followed
through verdict, clustering, drafting, review and replay, how to run the demo, and the limitations.

- `kt-video.mp4`: the rendered video (1920×1080, H.264 + AAC)
- `captions.vtt`, `chapters.txt`, `poster.jpg`: captions, YouTube-style chapters and a preview frame

## How it's built

| File | Role |
|---|---|
| `outline.md` | Scene plan |
| `script.md` | Narration, on-screen beats, and a `file:line` source for every claim |
| `tts.py` | Reads the **Narration** blocks and voices them locally with Kokoro (`af_heart`, 24 kHz). Writes `audio/scene_XX.wav`, `timing.json` / `timing.js` (scene, sentence and word timestamps) and `captions.srt` |
| `index.html` | The whole video as one HTML composition. `window.renderAt(t)` draws the exact frame for time `t`; beats are keyed to spoken phrases through the word timestamps. Open it in a browser for a play/scrub preview |
| `render.mjs` | Playwright Chromium screenshots every frame at 30 fps, pipes the PNGs into ffmpeg, and muxes in the padded scene audio |

Each scene lasts as long as its audio plus 0.6 s of padding. Fonts are local system fonts (Bahnschrift, Segoe UI,
Consolas, with fallbacks), so rendering needs no network.

## Setup (once)

Needs Python 3.10–3.12, Node 18+, ffmpeg and espeak-ng on the PATH.

```bash
cd docs/kt-video
python3.12 -m venv .venv                      # or: uv venv --python 3.12 .venv
.venv/Scripts/python.exe -m pip install "kokoro>=0.9" soundfile   # .venv/bin/python on macOS/Linux
npm install
npx playwright install chromium
```

The first `tts.py` run downloads the Kokoro model from Hugging Face; later runs use the local cache.

## Re-render

```bash
npm run kt-video     # voiceover + timing + captions, then render (about 20 minutes)
npm run render       # render only, reusing the existing audio and timing
```

Outputs go to `out/` (`kt-video.mp4`, `captions.srt`, `chapters.txt`), and the committed copies in this folder are
refreshed. Set `CRF=24` to shrink the file.

## Edit a scene

1. Change the scene's **Narration** in `script.md` (keep the sources in step with the code).
2. Re-voice just that scene: `.venv/Scripts/python.exe tts.py 4` (timing for all scenes is rebuilt).
3. If you changed a phrase that a beat is keyed to, update that scene's `beats` in `index.html`. Beats look up
   phrases with `b("phrase")`, and a missing phrase throws an error.
4. Check a frame: `node render.mjs --frame 100.5 out/check.png`, or open `index.html` and scrub.
5. `npm run render`.
