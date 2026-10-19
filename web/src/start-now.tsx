// Start now with a default person (roadmap R24c, features.md items 56 to 58): pick a gender, an
// accent, photoreal or animated, and a role, and chat at once with a made-up person in a
// ready-made voice. Only that person is downloaded, the first time they are chosen.

import { useEffect, useRef, useState } from "preact/hooks";

import { type Gender, type PersonChoice, type StartNowStatus, getStartNow, startNow } from "./api";

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
};

// How often the page asks how the download is going.
export const POLL_MS = 500;

const WORKING = ["downloading", "unpacking", "getting-ready"];

export function progressText(status: StartNowStatus): string {
  if (status.state === "downloading") return `Downloading the person… ${status.percent}%`;
  return "Getting the person ready…";
}

export function StartNowPage() {
  const [choice, setChoice] = useState<PersonChoice>(FIRST);
  const [status, setStatus] = useState<StartNowStatus | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const started = useRef(0); // when Start was clicked, for the log

  // The person chosen before, if any, is where the choices start.
  useEffect(() => {
    getStartNow()
      .then((s) => {
        if (s.chosen) setChoice(s.chosen);
        if (WORKING.includes(s.state)) setStatus(s);
      })
      .catch((e: unknown) => console.error("Could not read the default person", e));
  }, []);

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
                  onChange={() => setChoice({ ...choice, [key]: value })}
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
            onChange={(e) => setChoice({ ...choice, role: (e.target as HTMLSelectElement).value })}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {roleLabel(role, choice.gender)}
              </option>
            ))}
          </select>
        </label>
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
