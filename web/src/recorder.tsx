// Recording the voice with the microphone in the setup wizard (roadmap R133): what to say for
// each recording from the recording guide's script, a level meter, a timer and Stop, recorded
// with MediaRecorder, played back, and uploaded to be converted and checked like any recording,
// with Record again. The microphone is asked for when the first recording starts and is on only
// while recording. Without a microphone, or without access to it, the step says why and the
// recordings are picked as files instead.

import type { ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";

import { type MicrophoneReason, removeUpload, reportRecording, type Upload, uploadFile } from "./api";
import { Checks } from "./checks";
import { QUESTIONS_3, Questions, Script, SCRIPT_1, SCRIPT_2 } from "./guide";
import { useSettingGuard } from "./setting-guard";

// Recordings are limited to 10 minutes each on the server, so a longer one stops itself.
export const MAX_S = 10 * 60;

export const WHY_NOT: Record<MicrophoneReason, string> = {
  insecure:
    "The browser allows the microphone only on a secure page (HTTPS) or on this computer (localhost), and this page is neither.",
  unsupported: "This browser can't record sound.",
  refused: "The browser wasn't allowed to use the microphone.",
  "no-microphone": "No microphone was found on this computer.",
  failed: "The microphone could not be started. It may be in use by another app.",
};

// The voice as it is: the browser's clean-up for calls changes how it sounds.
export const MICROPHONE: MediaTrackConstraints = {
  echoCancellation: false,
  noiseSuppression: false,
  autoGainControl: false,
};

interface Passage {
  name: string;
  how: string;
  minutes: string;
  say: ComponentChildren;
}

// Recordings 1 to 3 of the recording guide: enough for the voice today.
export const PASSAGES: Passage[] = [
  {
    name: "Voice 1",
    how: "Read each line, then pause about 1 second (one breath) before the next line.",
    minutes: "1½ minutes",
    say: <Script first={1} lines={SCRIPT_1} />,
  },
  {
    name: "Voice 2",
    how: "Read each line, then pause about 1 second (one breath) before the next line.",
    minutes: "1½ minutes",
    say: <Script first={11} lines={SCRIPT_2} />,
  },
  {
    name: "Voice 3",
    how: "Choose two or three questions and answer them out loud in your own words, as if chatting with a friend, for about 20 to 30 seconds each.",
    minutes: "1 minute",
    say: <Questions items={QUESTIONS_3} />,
  },
];

// Why the microphone can't be asked for at all on this page, if it can't.
export function microphoneBlocked(): MicrophoneReason | null {
  if (window.isSecureContext === false) return "insecure";
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") return "unsupported";
  return null;
}

// What a refused getUserMedia means for the user.
export function reasonOf(error: unknown): MicrophoneReason {
  const name = (error as { name?: string } | null)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") return "refused";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "no-microphone";
  if (name === "NotSupportedError") return "unsupported";
  return "failed";
}

// The recording types the server reads, best first; "" leaves the choice to the browser.
const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export function recordingType(): string {
  return TYPES.find((t) => MediaRecorder.isTypeSupported?.(t)) ?? "";
}

// The file name's ending for a recording type.
export function extension(type: string): string {
  if (type.startsWith("audio/mp4")) return "m4a";
  if (type.startsWith("audio/ogg")) return "ogg";
  return "webm";
}

// "1:05" for 65 seconds.
export function clock(seconds: number): string {
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

type Phase = "ready" | "asking" | "recording" | "checking" | "made" | "off";

interface Made {
  url: string;
  upload: Upload | null;
  error: string | null;
  stayed?: boolean; // failed its checks but couldn't be removed, so it is still in the list
}

function stopTracks(stream: MediaStream | null) {
  stream?.getTracks().forEach((t) => t.stop());
}

function report(r: Parameters<typeof reportRecording>[0]) {
  reportRecording(r).catch((e: unknown) => console.error("Could not log the microphone's use", e));
}

export function VoiceRecorder(props: {
  // A recording made was kept, so the list of recordings is read again.
  onAdded: () => void;
  // True while recording, or while a recording is uploaded and checked; false once that is over.
  onChanging: (busy: boolean) => void;
}) {
  const [phase, setPhase] = useState<Phase>("ready");
  const [reason, setReason] = useState<MicrophoneReason | null>(null);
  const [passage, setPassage] = useState(0);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [made, setMade] = useState<Made | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const audio = useRef<AudioContext | null>(null);
  const ticking = useRef<number | undefined>(undefined);
  const frame = useRef<number | undefined>(undefined);
  const alive = useRef(true);
  const guard = useSettingGuard();

  // The microphone, the meter and the timer off.
  function stopListening() {
    window.clearInterval(ticking.current);
    if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    frame.current = undefined;
    audio.current?.close().catch(() => {});
    audio.current = null;
    stopTracks(stream.current);
    stream.current = null;
  }

  useEffect(() => {
    alive.current = true;
    return () => {
      // Leaving the step drops a recording not yet stopped.
      alive.current = false;
      if (recorder.current?.state === "recording") recorder.current.stop();
      stopListening();
    };
  }, []);

  // The recording played back, until Record again or until the step is left.
  const shown = useRef<string | null>(null);
  function show(url: string | null) {
    if (shown.current && shown.current !== url) URL.revokeObjectURL(shown.current);
    shown.current = url;
  }
  useEffect(() => () => show(null), []);

  function notUsed(why: MicrophoneReason, error?: unknown) {
    if (error) console.error(`Microphone not used (${why})`, error);
    else console.info(`Microphone not used (${why})`);
    report({ made: false, reason: why });
    setReason(why);
    setPhase("off");
  }

  // How loud the voice is, 0 to 1, from the loudest sample of each frame. Without Web Audio
  // there is no meter; the recording still works.
  function meter(media: MediaStream) {
    if (typeof AudioContext === "undefined") return;
    try {
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      context.createMediaStreamSource(media).connect(analyser);
      audio.current = context;
      const samples = new Float32Array(analyser.fftSize);
      const draw = () => {
        analyser.getFloatTimeDomainData(samples);
        let peak = 0;
        for (const v of samples) peak = Math.max(peak, Math.abs(v));
        setLevel(peak);
        frame.current = requestAnimationFrame(draw);
      };
      draw();
    } catch (e) {
      console.warn("No level meter", e);
    }
  }

  async function record() {
    const blocked = microphoneBlocked();
    if (blocked) {
      notUsed(blocked);
      return;
    }
    show(null);
    setMade(null);
    setPhase("asking");
    const asked = performance.now();
    let media: MediaStream;
    try {
      media = await navigator.mediaDevices.getUserMedia({ audio: MICROPHONE, video: false });
    } catch (e) {
      if (alive.current) notUsed(reasonOf(e), e);
      return;
    }
    if (!alive.current) {
      stopTracks(media); // the step was left while the browser asked
      return;
    }
    stream.current = media;
    const type = recordingType();
    let rec: MediaRecorder;
    try {
      rec = new MediaRecorder(media, type ? { mimeType: type } : undefined);
    } catch (e) {
      stopListening();
      notUsed("unsupported", e);
      return;
    }
    const microphone = media.getAudioTracks?.()[0]?.label || "unnamed";
    console.info(`Microphone on in ${Math.round(performance.now() - asked)} ms: ${microphone}`);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };
    const started = performance.now();
    rec.onstop = () => {
      const length = (performance.now() - started) / 1000;
      stopListening();
      if (alive.current) void finish(new Blob(chunks, { type: rec.mimeType || type }), length);
    };
    recorder.current = rec;
    meter(media);
    setSeconds(0);
    ticking.current = window.setInterval(() => {
      const now = (performance.now() - started) / 1000;
      setSeconds(now);
      if (now >= MAX_S && rec.state === "recording") {
        console.info(`Recording stopped at the ${MAX_S / 60}-minute limit`);
        rec.stop();
      }
    }, 250);
    rec.start(1000);
    props.onChanging(true);
    console.info(`Recording ${PASSAGES[passage].name} (${rec.mimeType || type || "browser's type"})`);
    setPhase("recording");
  }

  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  async function finish(blob: Blob, length: number) {
    const format = blob.type || "unknown";
    report({ made: true, seconds: Math.round(length * 10) / 10, format });
    console.info(`Recording made: ${length.toFixed(1)} s, ${format}`);
    const url = URL.createObjectURL(blob);
    show(url);
    setMade({ url, upload: null, error: null });
    if (!(await guard.confirm("Add the recording you made?"))) {
      props.onChanging(false);
      setPhase("made");
      return;
    }
    setPhase("checking");
    const checking = performance.now();
    const n = passage + 1;
    const name = `voice-${n}-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension(format)}`;
    try {
      const upload = await uploadFile("sounds", new File([blob], name, { type: format }));
      console.info(`Recording checked in ${Math.round(performance.now() - checking)} ms`);
      if (alive.current) setMade({ url, upload, error: null });
      if (upload.problems?.length) {
        if (!(await dropFailed(upload)) && alive.current) setMade({ url, upload, error: null, stayed: true });
      } else {
        props.onAdded();
      }
    } catch (e) {
      console.error("Recording refused", e);
      if (alive.current) setMade({ url, upload: null, error: (e as Error).message });
    }
    props.onChanging(false);
    if (alive.current) setPhase("made");
  }

  // A recording that fails its checks isn't kept, as a photo taken isn't (Larry's test of PR
  // #227). If it can't be removed, the list shows it, so it can be removed there. Answers whether
  // it was removed.
  async function dropFailed(upload: Upload): Promise<boolean> {
    try {
      await removeUpload("sounds", upload.id);
      console.info(`Recording failed its checks and was not kept: ${upload.problems?.join(" ")}`);
      return true;
    } catch (e) {
      console.error("Could not remove the recording that failed its checks", e);
      props.onAdded();
      return false;
    }
  }

  function next() {
    show(null);
    setMade(null);
    setPassage((p) => p + 1);
    setPhase("ready");
  }

  if (phase === "off") {
    return (
      <div className="recorder off" role="note">
        <strong>The microphone can&apos;t be used.</strong> {reason && WHY_NOT[reason]} Add recordings
        you already made below instead.
        {reason !== "insecure" && reason !== "unsupported" && (
          <button type="button" className="secondary" onClick={() => void record()}>
            Try the microphone again
          </button>
        )}
      </div>
    );
  }

  const current = PASSAGES[passage];
  const kept = made?.upload?.problems?.length === 0;
  const failed = Boolean(made?.upload?.problems?.length);
  return (
    <div className="recorder">
      <h3>
        Recording {passage + 1} of {PASSAGES.length}: {current.name}
      </h3>
      <p className="muted">
        {current.how} About {current.minutes}.
      </p>
      {current.say}
      {phase === "recording" && (
        <div className="recording" role="status">
          <span className="rec-dot" aria-hidden="true" />
          <span className="timer">{clock(seconds)}</span>
          <span className="level" aria-label="Sound level">
            <span style={{ width: `${Math.min(100, Math.round(level * 100))}%` }} />
          </span>
        </div>
      )}
      {phase === "asking" && <p className="muted busy">Asking for the microphone…</p>}
      {phase === "checking" && <p className="muted busy">Checking the recording…</p>}
      {made && (phase === "made" || phase === "checking") && (
        <audio controls src={made.url} aria-label="The recording you made" />
      )}
      {made?.upload && <Checks item={made.upload} queue={-1} />}
      {kept && (
        <p className="done">
          Kept.{" "}
          {passage + 1 < PASSAGES.length
            ? "Go on to the next recording, or click Next if you have enough."
            : "That's all three: click Next."}
        </p>
      )}
      {failed &&
        (made?.stayed ? (
          <p className="error">
            This recording could not be removed. It is still in Your recordings below: remove it there,
            then Record again.
          </p>
        ) : (
          <p className="muted">Not kept. Record again to try again.</p>
        ))}
      {made?.error && <p className="error">{made.error}</p>}
      <div className="choices">
        {phase === "ready" && (
          <button type="button" onClick={() => void record()}>
            Start recording
          </button>
        )}
        {phase === "recording" && (
          <button type="button" onClick={stop}>
            Stop
          </button>
        )}
        {phase === "made" && (
          <button type="button" className={kept ? "secondary" : undefined} onClick={() => void record()}>
            Record again
          </button>
        )}
        {phase === "made" && kept && passage + 1 < PASSAGES.length && (
          <button type="button" onClick={next}>
            Next recording: {PASSAGES[passage + 1].name}
          </button>
        )}
      </div>
    </div>
  );
}
