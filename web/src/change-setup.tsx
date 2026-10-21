// Avatar Choice on the Settings page: the person in the video is either the user's own photo and
// voice or a ready-made avatar, side by side, so switching between them happens in one place
// (Larry's test of R32a). Under their own, each change opens setup at that part (roadmap R28);
// whatever is changed there needs a new sample video, accepted, before the chat opens again, and
// Prepare makes Goodbye and Welcome back again with it.

import { useEffect, useState } from "preact/hooks";

import { getReview, useOwnPerson } from "./api";
import type { SetupPart } from "./router";

const CHANGES: { part: SetupPart; label: string; about: string }[] = [
  { part: "photos", label: "Change photos", about: "Add, remove or choose the photo the video is made from." },
  { part: "sounds", label: "Change recordings", about: "Add or remove the recordings the voice is made from." },
  { part: "accent", label: "Change accent", about: "Keep the person's own accent or choose another one." },
];

// Whose avatar the chat uses now, once the server has said.
type InUse = "own" | "ready-made";

// Use your own photo and voice, from a ready-made avatar (Larry's test of PR #128): straight to
// the chat when their sample is already accepted, since nothing needs preparing; otherwise to
// setup, to accept one.
export async function switchToOwn(ownAccepted: boolean, from: string): Promise<void> {
  if (!ownAccepted) {
    window.location.hash = "#/setup";
    return;
  }
  const started = performance.now();
  await useOwnPerson();
  console.info(`Switched to your own photo and voice from ${from} (${Math.round(performance.now() - started)} ms)`);
  window.location.hash = "#/chat";
}

function InUseMark({ shown }: { shown: boolean }) {
  return shown ? <span className="in-use">In use</span> : null;
}

export function ChangeSetup() {
  // null until the server has answered, or if it couldn't (before consent, say).
  const [accepted, setAccepted] = useState<boolean | null>(null);
  const [inUse, setInUse] = useState<InUse | null>(null);
  const [ownAccepted, setOwnAccepted] = useState(false); // their own sample, with an avatar in use
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    const started = performance.now();
    getReview()
      .then((r) => {
        const avatar = r.default_person ? "ready-made" : "own";
        setAccepted(r.accepted);
        setInUse(avatar);
        setOwnAccepted(r.own_sample_accepted === true);
        const took = Math.round(performance.now() - started);
        console.info(`Sample accepted: ${r.accepted}, avatar in use: ${avatar} (${took} ms)`);
      })
      .catch((e: unknown) => console.error("Could not get the review", e));
  }, []);

  return (
    <section className="panel" aria-labelledby="settings-change">
      <h2 id="settings-change">Avatar Choice</h2>
      <p className="muted">
        The person in the video: your own photo and voice, or a ready-made avatar.
      </p>
      <div className="avatar-options">
        <div className={inUse === "own" ? "avatar-option chosen" : "avatar-option"}>
          <h3>
            Your own photo and voice <InUseMark shown={inUse === "own"} />
          </h3>
          {inUse === "ready-made" ? (
            <div className="switch">
              <a
                className="button secondary"
                href="#/setup"
                onClick={(e) => {
                  console.info("Switching to your own photo and voice from Settings");
                  e.preventDefault();
                  switchToOwn(ownAccepted, "Settings").catch((err: unknown) => {
                    console.error("Could not switch to your own photo and voice", err);
                    setFailed((err as Error).message);
                  });
                }}
              >
                Use your own photo and voice
              </a>
              <p className="muted">
                {ownAccepted
                  ? "Your sample video is already accepted: the chat switches to it at once."
                  : "Your photos and recordings are kept. Accept their sample video at the end of setup to switch."}
              </p>
              {failed && <p className="error">{failed}</p>}
            </div>
          ) : (
            <>
              <p className="muted">
                Changing any of them makes the sample video again, and the chat stays locked until
                you accept the new one at the end of setup.
              </p>
              {accepted === true && (
                <p className="muted">The chat is open with the sample you accepted.</p>
              )}
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
            </>
          )}
        </div>
        <div className={inUse === "ready-made" ? "avatar-option chosen" : "avatar-option"}>
          <h3>
            Ready-made avatar <InUseMark shown={inUse === "ready-made"} />
          </h3>
          <p className="muted">
            A made-up person in a ready-made voice, chosen by face, accent and look. Your own
            photos and recordings are kept.
          </p>
          <div className="switch">
            <a
              className="button secondary"
              href="#/start-now"
              onClick={() => console.info("Choosing a ready-made avatar from Settings")}
            >
              {inUse === "ready-made" ? "Choose another avatar" : "Use a ready-made avatar"}
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
