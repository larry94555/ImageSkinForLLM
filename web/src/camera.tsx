// Taking the photo with the laptop's camera in the setup wizard (roadmap R132): the live picture
// with a head-and-shoulders outline, a 3-second countdown, then the picture at the camera's full
// size, uploaded and checked like any photo, with Retake. The camera is on only while the live
// picture shows. Without a camera, or without access to it, the step says why and the photo is
// picked as a file instead.

import { useEffect, useRef, useState } from "preact/hooks";

import { type CameraReason, reportCamera, type Upload, uploadFile } from "./api";
import { Checks } from "./checks";
import { useSettingGuard } from "./setting-guard";

export const COUNTDOWN_S = 3;

export const WHY_NOT: Record<CameraReason, string> = {
  insecure:
    "The browser allows the camera only on a secure page (HTTPS) or on this computer (localhost), and this page is neither.",
  unsupported: "This browser can't use a camera.",
  refused: "The browser wasn't allowed to use the camera.",
  "no-camera": "No camera was found on this computer.",
  failed: "The camera could not be started. It may be in use by another app.",
};

// Why the camera can't be asked for at all on this page, if it can't.
export function cameraBlocked(): CameraReason | null {
  if (window.isSecureContext === false) return "insecure";
  if (!navigator.mediaDevices?.getUserMedia) return "unsupported";
  return null;
}

// What a refused getUserMedia means for the user.
export function reasonOf(error: unknown): CameraReason {
  const name = (error as { name?: string } | null)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") return "refused";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "no-camera";
  if (name === "NotSupportedError") return "unsupported";
  return "failed";
}

export interface Grabbed {
  blob: Blob;
  width: number;
  height: number;
}

export const NO_PICTURE =
  "The camera isn't sending a picture. Wait a moment and try again, or choose another camera.";

// The live picture as a JPEG at the camera's full size.
export function grabFrame(video: HTMLVideoElement): Promise<Grabbed> {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) return Promise.reject(new Error(NO_PICTURE));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return Promise.reject(new Error("The picture could not be taken."));
  context.drawImage(video, 0, 0, width, height);
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve({ blob, width, height }) : reject(new Error("The picture could not be taken."))),
      "image/jpeg",
      0.92,
    ),
  );
}

// The camera chosen last time, so the same one opens next time (Larry's test of PR #227: a
// virtual camera was opened instead of the laptop's own).
const CAMERA_KEY = "imageskin.camera";

function savedCamera(): string | null {
  try {
    return localStorage.getItem(CAMERA_KEY);
  } catch {
    return null;
  }
}

function saveCamera(id: string) {
  try {
    localStorage.setItem(CAMERA_KEY, id);
  } catch (e) {
    console.warn("Could not remember the camera chosen", e);
  }
}

export interface CameraChoice {
  id: string;
  label: string;
}

type Phase = "starting" | "live" | "counting" | "checking" | "taken" | "off";

interface Shot {
  url: string;
  upload: Upload | null;
  error: string | null;
}

function stopTracks(stream: MediaStream | null) {
  stream?.getTracks().forEach((t) => t.stop());
}

function report(r: Parameters<typeof reportCamera>[0]) {
  reportCamera(r).catch((e: unknown) => console.error("Could not log the camera's use", e));
}

export function CameraPhoto(props: {
  // A photo taken was stored, passed its checks or not, so the list of photos is read again.
  onAdded: () => void;
  // True while a photo taken is uploaded and checked, false once that is over.
  onChanging: (busy: boolean) => void;
  grab?: (video: HTMLVideoElement) => Promise<Grabbed>; // for tests
}) {
  const grab = props.grab ?? grabFrame;
  const [phase, setPhase] = useState<Phase>("starting");
  const [reason, setReason] = useState<CameraReason | null>(null);
  const [count, setCount] = useState(COUNTDOWN_S);
  const [shot, setShot] = useState<Shot | null>(null);
  const [grabFailed, setGrabFailed] = useState<string | null>(null);
  // The cameras on this computer, once the browser lets their names be read, and the one in use.
  const [cameras, setCameras] = useState<CameraChoice[]>([]);
  const [cameraId, setCameraId] = useState<string | null>(null);
  const label = useRef("");
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const timers = useRef<number[]>([]);
  const alive = useRef(true);
  const guard = useSettingGuard();

  function stopCamera() {
    if (stream.current) console.info("Camera turned off");
    stopTracks(stream.current);
    stream.current = null;
  }

  function notUsed(why: CameraReason, error?: unknown) {
    if (error) console.error(`Camera not used (${why})`, error);
    else console.info(`Camera not used (${why})`);
    report({ taken: false, reason: why });
    setReason(why);
    setPhase("off");
  }

  async function start(chosen: string | null = savedCamera()) {
    setPhase("starting");
    setGrabFailed(null);
    const blocked = cameraBlocked();
    if (blocked) {
      notUsed(blocked);
      return;
    }
    const started = performance.now();
    try {
      // No size asked for here: the browser would open whichever camera fits the size best, a
      // virtual one over the laptop's own (Larry's test of PR #227). The size is raised after.
      const media = await navigator.mediaDevices.getUserMedia({
        video: chosen ? { deviceId: { ideal: chosen } } : true,
        audio: false,
      });
      if (!alive.current) {
        stopTracks(media); // the step was left while the browser asked
        return;
      }
      stream.current = media;
      const track = media.getVideoTracks?.()[0];
      label.current = track?.label ?? "";
      setCameraId(track?.getSettings?.().deviceId ?? null);
      try {
        await track?.applyConstraints?.({ width: { ideal: 1920 }, height: { ideal: 1080 } });
      } catch (e) {
        console.warn("The camera kept its own size", e);
      }
      console.info(`Camera on in ${Math.round(performance.now() - started)} ms: ${label.current || "unnamed"}`);
      void listCameras();
      setPhase("live");
    } catch (e) {
      if (alive.current) notUsed(reasonOf(e), e);
    }
  }

  async function listCameras() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const found = devices
        .filter((d) => d.kind === "videoinput")
        .map((d, i) => ({ id: d.deviceId, label: d.label || `Camera ${i + 1}` }));
      console.info(`Cameras: ${found.map((c) => c.label).join(", ") || "none listed"}`);
      if (alive.current) setCameras(found);
    } catch (e) {
      console.error("Could not list the cameras", e);
    }
  }

  function switchCamera(id: string) {
    console.info(`Camera chosen: ${cameras.find((c) => c.id === id)?.label ?? id}`);
    saveCamera(id);
    stopCamera();
    void start(id);
  }

  // The live picture goes in the video once it shows.
  useEffect(() => {
    const element = video.current;
    if (phase !== "live" || !element || !stream.current) return;
    element.srcObject = stream.current;
    element.play().catch((e: unknown) => console.error("Could not play the live picture", e));
  }, [phase]);

  useEffect(() => {
    alive.current = true;
    void start();
    // Leaving the step turns the camera off.
    return () => {
      alive.current = false;
      timers.current.forEach((t) => window.clearTimeout(t));
      stopCamera();
    };
  }, []);

  // The picture taken, shown until Retake or until the step is left.
  const shown = useRef<string | null>(null);
  function show(url: string | null) {
    if (shown.current && shown.current !== url) URL.revokeObjectURL(shown.current);
    shown.current = url;
  }
  useEffect(() => () => show(null), []);

  function takePhoto() {
    setGrabFailed(null);
    setPhase("counting");
    setCount(COUNTDOWN_S);
    for (let s = 1; s <= COUNTDOWN_S; s++) {
      timers.current.push(
        window.setTimeout(() => (s < COUNTDOWN_S ? setCount(COUNTDOWN_S - s) : void capture()), s * 1000),
      );
    }
  }

  async function capture() {
    timers.current = [];
    const element = video.current;
    if (!element) return;
    let grabbed: Grabbed;
    try {
      grabbed = await grab(element);
    } catch (e) {
      console.error("Could not take the picture", e);
      setShot(null);
      setGrabFailed((e as Error).message);
      setPhase("live");
      return;
    }
    // The picture is kept: the camera goes off until Retake.
    stopCamera();
    report({ taken: true, width: grabbed.width, height: grabbed.height, camera: label.current });
    console.info(`Camera photo taken: ${grabbed.width}×${grabbed.height}`);
    const url = URL.createObjectURL(grabbed.blob);
    show(url);
    setShot({ url, upload: null, error: null });
    if (!(await guard.confirm("Add the photo you took?"))) {
      setPhase("taken");
      return;
    }
    setPhase("checking");
    props.onChanging(true);
    const started = performance.now();
    const name = `camera-${new Date().toISOString().replace(/[:.]/g, "-")}.jpg`;
    try {
      const upload = await uploadFile("photos", new File([grabbed.blob], name, { type: "image/jpeg" }));
      console.info(`Camera photo checked in ${Math.round(performance.now() - started)} ms`);
      if (alive.current) setShot({ url, upload, error: null });
      props.onAdded();
    } catch (e) {
      console.error("Camera photo refused", e);
      if (alive.current) setShot({ url, upload: null, error: (e as Error).message });
    }
    props.onChanging(false);
    if (alive.current) setPhase("taken");
  }

  function retake() {
    console.info("Retaking the photo");
    show(null);
    setShot(null);
    void start();
  }

  if (phase === "off") {
    return (
      <div className="camera off" role="note">
        <strong>The camera can&apos;t be used.</strong> {reason && WHY_NOT[reason]} Add a photo you
        already have below instead.
        {reason !== "insecure" && reason !== "unsupported" && (
          <button type="button" className="secondary" onClick={retake}>
            Try the camera again
          </button>
        )}
      </div>
    );
  }

  const passed = shot?.upload?.problems?.length === 0;
  return (
    <div className="camera">
      {shot ? (
        <img className="camera-view" src={shot.url} alt="The photo you took" />
      ) : (
        <div className="camera-view">
          <video ref={video} muted playsInline aria-label="The camera's live picture" />
          <svg className="outline" viewBox="0 0 160 120" aria-hidden="true">
            <ellipse cx="80" cy="48" rx="25" ry="33" />
            <path d="M30 120c4-24 22-34 50-34s46 10 50 34" />
          </svg>
          {phase === "counting" && <span className="countdown">{count}</span>}
          {phase === "starting" && <p className="muted busy camera-note">Asking for the camera…</p>}
        </div>
      )}
      {!shot && cameras.length > 1 && (
        <label className="camera-choice">
          Camera{" "}
          <select
            value={cameraId ?? ""}
            disabled={phase !== "live"}
            onChange={(e) => switchCamera(e.currentTarget.value)}
          >
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {grabFailed && phase === "live" && <p className="error">{grabFailed}</p>}
      {phase === "checking" && <p className="muted busy">Checking the photo…</p>}
      {shot?.upload && <Checks item={shot.upload} queue={-1} />}
      {shot?.upload && passed && <p className="done">Kept. Click Next, or Retake to try again.</p>}
      {shot?.error && <p className="error">{shot.error}</p>}
      <div className="choices">
        {(phase === "live" || phase === "counting") && (
          <button type="button" disabled={phase === "counting"} onClick={takePhoto}>
            {phase === "counting" ? `Taking in ${count}…` : "Take photo"}
          </button>
        )}
        {phase === "taken" && (
          <button type="button" className="secondary" onClick={retake}>
            Retake
          </button>
        )}
      </div>
    </div>
  );
}
