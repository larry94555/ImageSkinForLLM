// Start now with a default person (roadmap R24c, features.md items 56 to 58): pick a gender, an
// accent, photoreal or animated, and a role, and chat at once with a made-up person in a
// ready-made voice. Only that person is downloaded, the first time they are chosen. A choice with
// a second face shows both as small pictures, with no label, to pick one (R24c2, item 60).

import { useEffect, useRef, useState } from "preact/hooks";

import {
  type Face,
  type Gender,
  type PersonChoice,
  type StartNowStatus,
  getFaces,
  getStartNow,
  startNow,
} from "./api";

// The roles, as the server names them. They don't carry a gender; where a role has a word for
// each gender, the list shows that word (item 56).
export const ROLES = [
  "Professor",
  "Teaching Assistant",
  "Student",
  "Parent",
  "Teenager",
  "Boss",
  "Office Manager",
  "High School Teacher",
  "Business Consultant",
];
const GENDERED: Record<string, Record<Gender, string>> = {
  Parent: { female: "Mother", male: "Father" },
  Teenager: { female: "Daughter", male: "Son" },
};

export function roleLabel(role: string, gender: Gender): string {
  return GENDERED[role]?.[gender] ?? role;
}

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
  face: 1,
};

// The faces of the choice, first face first.
export function facesOf(faces: Face[], choice: PersonChoice): Face[] {
  return faces
    .filter((f) => f.gender === choice.gender && f.realism === choice.realism && f.role === choice.role)
    .sort((a, b) => a.face - b.face);
}

// How often the page asks how the download is going.
export const POLL_MS = 500;

const WORKING = ["downloading", "unpacking", "getting-ready"];

export function progressText(status: StartNowStatus): string {
  if (status.state === "downloading") return `Downloading the person… ${status.percent}%`;
  return "Getting the person ready…";
}

export function StartNowPage() {
  const [choice, setChoice] = useState<PersonChoice>(FIRST);
  const [faces, setFaces] = useState<Face[]>([]);
  const [status, setStatus] = useState<StartNowStatus | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const started = useRef(0); // when Start was clicked, for the log

  // The person chosen before, if any, is where the choices start.
  useEffect(() => {
    getStartNow()
      .then((s) => {
        if (s.chosen) setChoice({ face: 1, ...s.chosen });
        if (WORKING.includes(s.state)) setStatus(s);
      })
      .catch((e: unknown) => console.error("Could not read the default person", e));
    getFaces()
      .then(setFaces)
      .catch((e: unknown) => console.error("Could not read the default people's faces", e));
  }, []);

  // Changing a choice shows the new choice's faces, with the first picked. The accent changes only
  // the voice, so the face stays.
  function change(part: Partial<PersonChoice>) {
    setChoice({ ...choice, ...part, face: "accent" in part ? choice.face : 1 });
  }
  const shown = facesOf(faces, choice);

  const working = status !== null && WORKING.includes(status.state);
  useEffect(() => {
    if (status?.state === "ready") {
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

  return (
    <section className="start-now panel">
      <h1>Start now with a default person</h1>
      <p className="muted">
        Chat at once with a made-up person who speaks in a ready-made voice. You can use your own
        photos and voice instead later.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void start();
        }}
      >
        {(["gender", "accent", "realism"] as const).map((key) => (
          <fieldset key={key} disabled={working}>
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
        <label className="role">
          Role{" "}
          <select
            value={choice.role}
            disabled={working}
            onChange={(e) => change({ role: (e.target as HTMLSelectElement).value })}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {roleLabel(role, choice.gender)}
              </option>
            ))}
          </select>
        </label>
        {shown.length > 0 && (
          <fieldset className="faces" disabled={working}>
            <legend>{shown.length > 1 ? "Pick a face" : "Face"}</legend>
            {shown.map((f) => (
              <label key={f.name} className={choice.face === f.face ? "picked" : undefined}>
                <input
                  type="radio"
                  name="face"
                  value={f.face}
                  aria-label={`Face ${f.face}`}
                  checked={choice.face === f.face}
                  onChange={() => setChoice({ ...choice, face: f.face })}
                />
                <img src={`/default-people/${f.name}.jpg`} alt="" width={128} height={128} />
              </label>
            ))}
          </fieldset>
        )}
        <button type="submit" disabled={working} className={working ? "busy" : undefined}>
          {status?.state === "failed" ? "Try again" : "Start now"}
        </button>
      </form>
      {working && (
        <>
          <p className="busy">{progressText(status)}</p>
          <progress max={100} value={status.percent} aria-label="Downloading">
            {status.percent}%
          </progress>
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
