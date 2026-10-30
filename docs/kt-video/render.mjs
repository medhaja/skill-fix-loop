// Render the walkthrough: Playwright Chromium draws every frame with window.renderAt(t), PNG frames are piped
// straight into ffmpeg, and the scene WAVs (each followed by its padding) are muxed in as AAC.
//
//   node render.mjs              render out/kt-video.mp4 from the existing audio + timing.json
//   node render.mjs --tts        regenerate the voiceover first (Kokoro, local), then render
//   node render.mjs --frame 42.5 [out.png]   write a single frame, for checking a scene
//   CRF=24 node render.mjs       raise the CRF if the file is too big

import { spawn, spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out");
const FPS = 30;
const CRF = process.env.CRF || "20";
const args = process.argv.slice(2);

function run(cmd, argv) {
  const r = spawnSync(cmd, argv, { stdio: "inherit", cwd: HERE });
  if (r.status !== 0) throw new Error(`${cmd} exited ${r.status}`);
}

if (args.includes("--tts")) {
  const py = [".venv/Scripts/python.exe", ".venv/bin/python"].map(p => join(HERE, p)).find(existsSync);
  if (!py) throw new Error("No venv found in docs/kt-video/.venv (see README.md)");
  run(py, ["tts.py"]);
}

const timing = JSON.parse(readFileSync(join(HERE, "timing.json"), "utf8"));
mkdirSync(OUT, { recursive: true });

async function openPage() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on("pageerror", e => { console.error("page error:", e.message); process.exitCode = 1; });
  await page.goto(pathToFileURL(join(HERE, "index.html")).href + "?render=1");
  await page.evaluate(() => window.kvReady);
  return { browser, page };
}

async function frame(t, file) {
  const { browser, page } = await openPage();
  await page.evaluate(x => window.renderAt(x), t);
  await page.screenshot({ path: file, type: file.endsWith(".jpg") ? "jpeg" : "png", quality: file.endsWith(".jpg") ? 92 : undefined });
  await browser.close();
}

function srtToVtt(srt) {
  return "WEBVTT\n\n" + srt.replace(/\r/g, "").replace(/(\d\d:\d\d:\d\d),(\d\d\d)/g, "$1.$2");
}

function chapters() {
  const fmt = s => { s = Math.floor(s); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  return timing.scenes.map(sc => `${fmt(sc.start)} ${sc.title}`).join("\n") + "\n";
}

function narration() {
  // Concatenate scene WAVs in order, each padded with timing.pad seconds of silence.
  const inputs = timing.scenes.flatMap(sc => ["-i", join(HERE, "audio", `scene_${String(sc.n).padStart(2, "0")}.wav`)]);
  const pads = timing.scenes.map((sc, i) => `[${i}:a]apad=pad_dur=${timing.pad}[a${i}]`).join(";");
  const concat = timing.scenes.map((_, i) => `[a${i}]`).join("") + `concat=n=${timing.scenes.length}:v=0:a=1[out]`;
  const file = join(OUT, "narration.wav");
  run("ffmpeg", ["-y", "-loglevel", "error", ...inputs, "-filter_complex", `${pads};${concat}`, "-map", "[out]", "-ar", "24000", file]);
  return file;
}

async function renderVideo() {
  const audio = narration();
  const file = join(OUT, "kt-video.mp4");
  const ff = spawn("ffmpeg", [
    "-y", "-loglevel", "error",
    "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-",
    "-i", audio,
    "-map", "0:v", "-map", "1:a",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", CRF, "-preset", "veryfast",
    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest",
    file,
  ], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => ff.on("close", c => (c === 0 ? res() : rej(new Error(`ffmpeg exited ${c}`)))));

  const { browser, page } = await openPage();
  const frames = Math.round(timing.total * FPS);
  const started = Date.now();
  for (let i = 0; i < frames; i++) {
    let png;
    for (let attempt = 1; !png; attempt++) {  // retry: a stalled capture (e.g. after the machine sleeps) times out
      try {
        await page.evaluate(x => window.renderAt(x), i / FPS);
        png = await page.screenshot({ type: "png" });
      } catch (e) {
        if (attempt >= 3) throw e;
        console.warn(`frame ${i}: ${e.message.split("\n")[0]}; retrying`);
      }
    }
    if (!ff.stdin.write(png)) await new Promise(r => ff.stdin.once("drain", r));
    if (i % 300 === 0) console.log(`frame ${i}/${frames} (${((Date.now() - started) / 1000).toFixed(0)}s)`);
  }
  ff.stdin.end();
  await done;
  await browser.close();
  return file;
}

if (args.includes("--frame")) {
  const t = Number(args[args.indexOf("--frame") + 1]);
  const file = args[args.indexOf("--frame") + 2] || join(OUT, `frame_${t.toFixed(2)}.png`);
  await frame(t, file);
  console.log(file);
} else {
  const video = await renderVideo();
  copyFileSync(join(HERE, "captions.srt"), join(OUT, "captions.srt"));
  writeFileSync(join(OUT, "chapters.txt"), chapters());
  // Committed copies: the video, a poster frame from scene 1, WebVTT captions and the chapter list.
  copyFileSync(video, join(HERE, "kt-video.mp4"));
  writeFileSync(join(HERE, "captions.vtt"), srtToVtt(readFileSync(join(HERE, "captions.srt"), "utf8")));
  copyFileSync(join(OUT, "chapters.txt"), join(HERE, "chapters.txt"));
  const posterPng = join(OUT, "poster.png");
  await frame(timing.scenes[0].duration - 1.0, posterPng);
  run("ffmpeg", ["-y", "-loglevel", "error", "-i", posterPng, "-vf", "scale=1280:-2", "-q:v", "3", join(HERE, "poster.jpg")]);
  console.log(`done: ${video}`);
}
