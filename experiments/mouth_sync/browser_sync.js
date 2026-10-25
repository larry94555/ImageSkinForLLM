// R127 in the browser: does a clip's picture show before its sound plays?
//
//   python experiments/mouth_sync/mouth_lead.py --media sync-media
//   node experiments/mouth_sync/browser_sync.js sync-media [chrome-channel]
//
// The media have a white frame and a beep at the same moments (MARKS_S in mouth_lead.py). The
// page plays them as the chat does (ClipPlayer in web/src/pages.tsx): the muted idle video
// first, then the clips one after another, each next one loaded in a hidden second player that
// takes over when the one before ends. For each mark it takes when the browser shows the white
// frame (requestVideoFrameCallback's expected display time) and when the beep is played (an
// AudioWorklet on the clip's sound, mapped to the page's clock with getOutputTimestamp), and
// prints the lead of the picture over the sound. The sound goes through Web Audio here, so its
// output delay is Web Audio's, which Chromium reports and is added in.

const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const MARKS_S = [0.6, 1.6, 2.6];
const CLIPS = ["marks-whole.mp4", "marks-progressive.mp4", "marks-progressive.mp4"];

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

const PAGE = `<!doctype html><meta charset="utf-8"><body style="background:#000">
<video id="idle" src="idle.mp4" muted loop autoplay playsinline></video>
<video id="a" playsinline></video><video id="b" playsinline preload="auto" hidden></video>
<script>
const MARKS = ${JSON.stringify(MARKS_S)}, CLIPS = ${JSON.stringify(CLIPS)}, FPS = 25;
window.result = null;
async function run() {
  const ctx = new AudioContext();
  await ctx.audioWorklet.addModule("onset.js");
  const players = [document.getElementById("a"), document.getElementById("b")];
  const pictures = [], sounds = [];
  let clip = 0;
  for (const p of players) {
    const node = new AudioWorkletNode(ctx, "onset");
    ctx.createMediaElementSource(p).connect(node);
    node.connect(ctx.destination);
    node.port.onmessage = (e) => {
      const ts = ctx.getOutputTimestamp();
      sounds.push({ clip, played: ts.performanceTime + (e.data - ts.contextTime) * 1000 });
    };
    const frame = (now, md) => {
      pictures.push({ clip, media: md.mediaTime, shown: md.expectedDisplayTime, now });
      p.requestVideoFrameCallback(frame);
    };
    p.requestVideoFrameCallback(frame);
  }
  await new Promise((r) => setTimeout(r, 1000)); // the idle video plays first
  const [a, b] = players;
  a.src = CLIPS[0];
  let active = a;
  const next = () => {
    clip += 1;
    if (clip >= CLIPS.length) {
      setTimeout(() => { window.result = { pictures, sounds, latency: (ctx.outputLatency || 0) + ctx.baseLatency }; }, 500);
      return;
    }
    const other = active === a ? b : a;
    other.hidden = false; active.hidden = true;
    active = other;
    active.play();
    const after = active === a ? b : a;
    if (clip + 1 < CLIPS.length) after.src = CLIPS[clip + 1];
  };
  a.onended = next; b.onended = next;
  b.src = CLIPS[1];
  await ctx.resume();
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
      const file = path.join(folder, decodeURIComponent(req.url.split("?")[0]).replace(/^\/+/, "") || "index.html");
      if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    })
    .listen(0);
  const port = server.address().port;
  const channel = process.argv[3];
  const browser = await chromium.launch({
    channel,
    args: ["--autoplay-policy=no-user-gesture-required"],
  });
  const page = await browser.newPage();
  page.on("console", (m) => console.error("page:", m.text()));
  await page.goto(`http://127.0.0.1:${port}/index.html`);
  await page.waitForFunction(() => window.result !== null, null, { timeout: 30000 });
  const r = await page.evaluate(() => window.result);
  const version = `Chromium ${browser.version()}${channel ? ` (${channel})` : ""}`;
  if (process.env.DUMP) fs.writeFileSync(process.env.DUMP, JSON.stringify(r));
  await browser.close();
  server.close();
  if (r.error) throw new Error(r.error);
  r.whites = JSON.parse(fs.readFileSync(path.join(folder, "marks.json"), "utf-8"));
  console.log(leadTable(r, version));
}

const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };

// The lead of the picture over the sound at each mark. Frames are shown on the screen's beat, so
// each clip's picture clock is the median of (shown - media time) over its frames; the white
// frame shows at its time in the file (marks.json, from ffprobe: in a progressive MP4 every frame
// after the first is a little later than frame / 25). Web Audio's own output delay, which a page that doesn't route the sound through it
// doesn't have, is given apart.
function leadTable(r, browser) {
  const lines = [
    `Browser: ${browser}; Web Audio's output delay ${(r.latency * 1000).toFixed(0)} ms (not in the leads)`,
    "",
    "| Clip | Mark | Picture ahead of sound |",
    "|---|---|---|",
  ];
  for (let c = 0; c < CLIPS.length; c++) {
    const frames = r.pictures.filter((p) => p.clip === c);
    const beeps = r.sounds.filter((s) => s.clip === c).map((s) => s.played);
    if (!frames.length) continue;
    const clock = median(frames.map((p) => p.shown - p.media * 1000));
    MARKS_S.forEach((m, i) => {
      const shown = clock + r.whites[CLIPS[c]][i] * 1000;
      const lead = beeps[i] === undefined ? "no beep" : `${(beeps[i] - shown).toFixed(0)} ms`;
      lines.push(`| ${c + 1} (${CLIPS[c]}) | ${m} s | ${lead} |`);
    });
  }
  return lines.join("\n");
}

if (require.main === module) {
  main().catch((e) => { console.error(e); process.exit(1); });
}
module.exports = { leadTable };
