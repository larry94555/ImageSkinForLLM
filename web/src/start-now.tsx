// Start now with a default person (roadmap R24c, features.md items 56 to 58): pick a gender, an
// accent, photoreal or animated, and a face, and chat at once with a made-up person in a
// ready-made voice. Only that person is downloaded, the first time they are chosen.

import { useEffect, useRef, useState } from "preact/hooks";

import {
  type Face,
  type PersonChoice,
  type StartNowStatus,
  faceUrl,
  getFaces,
  getStartNow,
  startNow,
} from "./api";

const OPTIONS = {
  gender: [
    { value: "female", label: "Female" },
    { value: "male", label: "Male" },
  ],
  accent: [
    { value: "American", label: "American" },
    { value: "British", label: "British" },
  ],
  realism: [
    { value: "photoreal", label: "Photorealistic" },
    { value: "animated", label: "Animated" },
  ],
} as const;
const LEGENDS = { gender: "Gender", accent: "Accent", realism: "Look" };

const FIRST: PersonChoice = {
  gender: "female",
  accent: "American",
  realism: "photoreal",
  role: "Professor",
};

// How often the page asks how the download is going.
export const POLL_MS = 500;

const WORKING = ["downloading", "unpacking", "getting-ready"];

// Ready, but the chat would still show the person before: their idle video is being made
// (Larry's test of R32a). A server that doesn't say counts as done.
function finishing(status: StartNowStatus | null): boolean {
  return status?.state === "ready" && status.chat_ready === false;
}

// Where getting the person ready has got to, as one of three steps.
export function progressText(status: StartNowStatus): string {
  if (status.state === "downloading") {
    return `Step 1 of 3: Downloading the avatar… ${status.percent}%`;
  }
  if (status.state === "unpacking") return "Step 2 of 3: Unpacking the avatar…";
  if (status.state === "getting-ready") return "Step 2 of 3: Getting the avatar's voice ready…";
  return "Step 3 of 3: Making the avatar's video for the chat…";
}

// Seconds since `from` (performance.now()), counted up once a second while `on`.
function useSeconds(on: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!on) return;
    const from = performance.now();
    setSeconds(0);
    const timer = setInterval(() => setSeconds(Math.round((performance.now() - from) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [on]);
  return seconds;
}

// The faces to pick from (R24c2): all 15 people of the chosen gender and look, with the range of
// heritages, ages, glasses and wheelchairs R24b2 made, in the server's order, which stays the
// same. Each person was made for a role, but the page doesn't offer roles: each role has only
// one or two people, so a role would tie it to a look (Larry's test of PR #124).
export function facesOf(faces: Face[], choice: PersonChoice): Face[] {
  return faces.filter((f) => f.gender === choice.gender && f.realism === choice.realism);
}

export function StartNowPage() {
  const [choice, setChoice] = useState<PersonChoice>(FIRST);
  // null until the faces are read; the choices wait for them, since changing gender or look
  // picks the new group's first face (Codex's review of PR #124).
  const [faces, setFaces] = useState<Face[] | null>(null);
  const [facesFailed, setFacesFailed] = useState(false);
  // Changing gender or look starts at its first face; the accent keeps the face. The person
  // picked goes to the server as their role and face number, which name them.
  const change = (changes: Partial<PersonChoice>) => {
    const next = { ...choice, ...changes };
    const first = facesOf(faces ?? [], next)[0];
    const sameFaces = next.gender === choice.gender && next.realism === choice.realism;
    setChoice(sameFaces || !first ? next : { ...next, role: first.role, face: first.face });
  };
  const [status, setStatus] = useState<StartNowStatus | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const started = useRef(0); // when Start was clicked, for the log

  // The person chosen before, if any, is where the choices start.
  useEffect(() => {
    const asked = performance.now();
    getFaces()
      .then((f) => {
        setFaces(f);
        console.info(`${f.length} faces to pick from (${Math.round(performance.now() - asked)} ms)`);
      })
      .catch((e: unknown) => {
        console.error("Could not read the faces", e);
        setFacesFailed(true);
      });
    getStartNow()
      .then((s) => {
        if (s.chosen) setChoice(s.chosen);
        if (WORKING.includes(s.state) || finishing(s)) setStatus(s);
      })
      .catch((e: unknown) => console.error("Could not read the default person", e));
  }, []);

  const working = status !== null && (WORKING.includes(status.state) || finishing(status));
  const seconds = useSeconds(finishing(status));
  useEffect(() => {
    if (finishing(status)) console.info("Avatar ready; waiting for its idle video for the chat");
  }, [finishing(status)]);
  useEffect(() => {
    if (status?.state === "ready" && !finishing(status)) {
      const ms = Math.round(performance.now() - started.current);
      console.info(`Default person ${status.person} ready in ${ms} ms; opening the chat`);
      window.location.hash = "#/chat";
      return;
    }
    if (!working) return;
    const timer = setTimeout(() => {
      getStartNow()
        .then(setStatus)
        .catch((e: unknown) => {
          console.error("Could not read how the download is going", e);
          setStatus((s) => s && { ...s, state: "failed", error: "Could not reach the app. Try again." });
        });
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [status]);

  async function start() {
    setRefused(null);
    started.current = performance.now();
    console.info("Start now with a default person", choice);
    try {
      setStatus(await startNow(choice));
    } catch (e) {
      console.error("Could not start with a default person", e);
      setRefused((e as Error).message);
    }
  }

  const shown = facesOf(faces ?? [], choice);
  const locked = working || faces === null;
  const face = choice.face ?? 1;
  return (
    <section className="start-now panel">
      <h1>Avatar Choice: a ready-made avatar</h1>
      <p className="muted">
        Chat at once with a made-up person who speaks in a ready-made voice. You can switch to
        your own photo and voice at any time in Settings, under Avatar Choice.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void start();
        }}
      >
        {(["gender", "accent", "realism"] as const).map((key) => (
          <fieldset key={key} disabled={locked}>
            <legend>{LEGENDS[key]}</legend>
            {OPTIONS[key].map(({ value, label }) => (
              <label key={value}>
                <input
                  type="radio"
                  name={key}
                  value={value}
                  checked={choice[key] === value}
                  onChange={() => change({ [key]: value })}
                />{" "}
                {label}
              </label>
            ))}
          </fieldset>
        ))}
        {faces === null && !facesFailed && <p className="muted">Loading the faces…</p>}
        {facesFailed && (
          <p className="error" role="alert">
            Couldn't load the faces to pick from. Reload the page to try again.
          </p>
        )}
        {shown.length > 0 && (
          <fieldset className="faces" disabled={working}>
            <legend>Face</legend>
            {shown.map((f, i) => {
              const picked = f.role === choice.role && f.face === face;
              const name = `Face ${i + 1} of ${shown.length}`;
              return (
                <label key={f.name} className={picked ? "face picked" : "face"}>
                  <input
                    type="radio"
                    name="face"
                    value={f.name}
                    checked={picked}
                    onChange={() => {
                      console.info(`${name} picked: ${f.name}`);
                      setChoice({ ...choice, role: f.role, face: f.face });
                    }}
                  />
                  <img src={faceUrl(f.name)} alt={name} />
                </label>
              );
            })}
          </fieldset>
        )}
        <button type="submit" disabled={locked} className={working ? "busy" : undefined}>
          {status?.state === "failed" ? "Try again" : "Start now"}
        </button>
      </form>
      {working && (
        <>
          <p className="busy">
            {progressText(status)}
            {finishing(status) && seconds > 0 && ` ${seconds} s`}
          </p>
          {status.state === "downloading" ? (
            <progress max={100} value={status.percent} aria-label="Downloading">
              {status.percent}%
            </progress>
          ) : (
            <progress aria-label="Getting the avatar ready" />
          )}
        </>
      )}
      {status?.state === "failed" && (
        <p className="error" role="alert">
          {status.error}
        </p>
      )}
      {refused && (
        <p className="error" role="alert">
          {refused}
        </p>
      )}
      <p className="muted">
        Or <a href="#/consent">use your own photos and voice</a>.
      </p>
    </section>
  );
}
