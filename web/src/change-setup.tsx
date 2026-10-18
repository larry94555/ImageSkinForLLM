// Change the photo, the voice or the accent, on the Settings page (roadmap R28). Each opens setup
// at that part; whatever is changed there needs a new sample video, accepted, before the chat
// opens again, and Prepare makes Goodbye and Welcome back again with it.

import { useEffect, useState } from "preact/hooks";

import { getReview } from "./api";
import type { SetupPart } from "./router";

const CHANGES: { part: SetupPart; label: string; about: string }[] = [
  { part: "photos", label: "Change photos", about: "Add, remove or choose the photo the video is made from." },
  { part: "sounds", label: "Change recordings", about: "Add or remove the recordings the voice is made from." },
  { part: "accent", label: "Change accent", about: "Keep the person's own accent or choose another one." },
];

export function ChangeSetup() {
  // null until the server has answered, or if it couldn't (before consent, say).
  const [accepted, setAccepted] = useState<boolean | null>(null);

  useEffect(() => {
    const started = performance.now();
    getReview()
      .then((r) => {
        setAccepted(r.accepted);
        const took = Math.round(performance.now() - started);
        console.info(`Sample accepted: ${r.accepted} (${took} ms)`);
      })
      .catch((e: unknown) => console.error("Could not get the review", e));
  }, []);

  return (
    <section className="panel" aria-labelledby="settings-change">
      <h2 id="settings-change">Photo, voice and accent</h2>
      <p className="muted">
        Changing any of them makes the sample video again, and the chat stays locked until you
        accept the new one at the end of setup.
      </p>
      {accepted === true && <p className="muted">The chat is open with the sample you accepted.</p>}
      {accepted === false && (
        <p className="notice">
          The chat is locked until you accept a sample video in <a href="#/setup">Setup</a>.
        </p>
      )}
      {CHANGES.map(({ part, label, about }) => (
        <div key={part} className="switch">
          <a
            className="button secondary"
            href={`#/setup/${part}`}
            onClick={() => console.info(`Changing the ${part} from Settings`)}
          >
            {label}
          </a>
          <p className="muted">{about}</p>
        </div>
      ))}
    </section>
  );
}
