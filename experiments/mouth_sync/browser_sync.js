// R127 in the browser: does a clip's picture show before its sound plays, at the switch from
// the idle video to a reply, between clips, and within a clip?
//
//   python experiments/mouth_sync/mouth_lead.py --media sync-media
//   node experiments/mouth_sync/browser_sync.js sync-media [chrome-channel]
//   python experiments/mouth_sync/mouth_lead.py --browser sync-media
//
// The media have a white frame and a beep at the same moments (MARKS_S in mouth_lead.py), the
// first on the clip's first frame. The page plays them the way the chat's ClipPlayer
// (web/src/pages.tsx) plays a reply: the muted idle video underneath, the first clip (a
// progressive MP4, as reply clips are) faded in over it with the chat's own 0.25 s opacity
// transition once it plays, and each next clip loaded in a hidden second player that is shown,
// then played, when the one before ends. A whole MP4 (the sample and the fixed lines) is played
// last, the same way.
//
// It records, on the page's clock: each frame the browser shows (requestVideoFrameCallback's
// media time and expected display time), when each clip starts playing, when each hidden player
// is shown, when each clip's
// opacity first reaches half, and when each beep is played (an AudioWorklet on the clip's
// sound, mapped with getOutputTimestamp). The raw times go to browser-raw.json in the media
// folder, and `mouth_lead.py --browser` turns them into the table. The sound goes through Web
// Audio to be measured; its own output delay, which the chat page doesn't have, is saved apart.

const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const CLIPS = [
  "marks-progressive.mp4",
  "marks-progressive.mp4",
  "marks-progressive.mp4",
  "marks-whole.mp4",
];

const WORKLET = `
class Onset extends AudioWorkletProcessor {
  constructor() { super(); this.quiet = 1e9; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      const loud = Math.abs(ch[i]) > 0.05;
      if (loud && this.quiet > 0.2 * sampleRate) {
        this.port.postMessage(currentTime + i / sampleRate);
      }
      this.quiet = loud ? 0 : this.quiet + 1;
    }
    return true;
  }
}
registerProcessor("onset", Onset);`;

// The stage and the two players, styled as web/src/styles.css styles them.
const PAGE = `<!doctype html><meta charset="utf-8">
<style>
  body { margin: 0; background: #000; }
  .stage { position: relative; width: 256px; height: 256px; }
  .reply-video, .idle-video { position: absolute; inset: 0; width: 100%; height: 100%;
    transition: opacity 0.25s ease; }
  .reply-video.resting { opacity: 0; }
</style>
<div class="stage">
  <video class="idle-video" src="idle.mp4" muted loop autoplay playsinline></video>
  <video id="a" class="reply-video resting" playsinline></video>
  <video id="b" class="reply-video" playsinline preload="auto" hidden></video>
</div>
<script>
const CLIPS = ${JSON.stringify(CLIPS)};
window.result = null;
async function run() {
  const ctx = new AudioContext();
  await ctx.audioWorklet.addModule("onset.js");
  const [a, b] = [document.getElementById("a"), document.getElementById("b")];
  const frames = [], sounds = [], shown = [], visible = [], playing = [];
  let clip = 0, active = a;
  for (const p of [a, b]) {
    const node = new AudioWorkletNode(ctx, "onset");
    ctx.createMediaElementSource(p).connect(node);
    node.connect(ctx.destination);
    node.port.onmessage = (e) => {
      const ts = ctx.getOutputTimestamp();
      sounds.push({ clip, played: ts.performanceTime + (e.data - ts.contextTime) * 1000 });
    };
    const frame = (now, md) => {
      if (p === active) frames.push({ clip, media: md.mediaTime, shown: md.expectedDisplayTime });
      p.requestVideoFrameCallback(frame);
    };
    p.requestVideoFrameCallback(frame);
    p.addEventListener("playing", () => playing.push({ clip, at: performance.now() }));
  }
  // When each clip is first at least half visible, checked on every screen update.
  let seen = -1;
  const watch = (t) => {
    if (seen < clip && !active.hidden && parseFloat(getComputedStyle(active).opacity) >= 0.5) {
      seen = clip;
      visible.push({ clip, at: t });
    }
    if (window.result === null) requestAnimationFrame(watch);
  };
  requestAnimationFrame(watch);
  a.addEventListener("playing", () => a.classList.remove("resting"), { once: true });
  const ended = () => {
    clip += 1;
    if (clip >= CLIPS.length) {
      setTimeout(() => {
        window.result = { frames, sounds, shown, visible, playing, clips: CLIPS,
                          latency: (ctx.outputLatency || 0) + ctx.baseLatency };
      }, 500);
      return;
    }
    // As ClipPlayer: the loaded player takes over, shown at once, and is then played.
    const next = active === a ? b : a;
    next.hidden = false;
    shown.push({ clip, at: performance.now() });
    active.hidden = true;
    active = next;
    active.play();
    const after = active === a ? b : a;
    if (clip + 1 < CLIPS.length) after.src = CLIPS[clip + 1];
  };
  a.onended = ended;
  b.onended = ended;
  a.src = CLIPS[0];
  b.src = CLIPS[1];
  await ctx.resume();
  await new Promise((r) => setTimeout(r, 1000)); // the idle video plays first
  await a.play();
}
run().catch((e) => { window.result = { error: String(e) }; });
</script>`;

async function main() {
  const folder = path.resolve(process.argv[2] || "sync-media");
  fs.writeFileSync(path.join(folder, "onset.js"), WORKLET);
  fs.writeFileSync(path.join(folder, "index.html"), PAGE);
  const types = { ".html": "text/html", ".js": "text/javascript", ".mp4": "video/mp4" };
  const server = http
    .createServer((req, res) => {
      const name = decodeURIComponent(req.url.split("?")[0]).replace(/^\/+/, "") || "index.html";
      const file = path.join(folder, name);
      if (!fs.existsSync(file)) {
        res.writeHead(404);
        res.end();
        return;
      }
      res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    })
    .listen(0);
  const channel = process.argv[3];
  const browser = await chromium.launch({
    channel,
    args: ["--autoplay-policy=no-user-gesture-required"],
  });
  const page = await browser.newPage();
  page.on("console", (m) => console.error("page:", m.text()));
  await page.goto(`http://127.0.0.1:${server.address().port}/index.html`);
  await page.waitForFunction(() => window.result !== null, null, { timeout: 30000 });
  const r = await page.evaluate(() => window.result);
  r.browser = `Chromium ${browser.version()}${channel ? ` (${channel})` : ""}`;
  await browser.close();
  server.close();
  if (r.error) throw new Error(r.error);
  const out = path.join(folder, "browser-raw.json");
  fs.writeFileSync(out, JSON.stringify(r, null, 1));
  console.log(`${r.browser}: ${r.frames.length} frames, ${r.sounds.length} beeps; wrote ${out}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
