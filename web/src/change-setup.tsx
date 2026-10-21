// Avatar Choice on the Settings page: the person in the video is either the user's own photo and
// voice or a ready-made avatar, side by side, so switching between them happens in one place
// (Larry's test of R32a). Under their own, each change opens setup at that part (roadmap R28);
// whatever is changed there needs a new sample video, accepted, before the chat opens again, and
// Prepare makes Goodbye and Welcome back again with it. With a ready-made avatar, Use my own photo
// (R24d) keeps its voice and replaces its picture with the user's own photo.

import { useEffect, useState } from "preact/hooks";

import { getConsent, getReview, setOwnPhoto } from "./api";
import type { SetupPart } from "./router";

const CHANGES: { part: SetupPart; label: string; about: string }[] = [
  { part: "photos", label: "Change photos", about: "Add, remove or choose the photo the video is made from." },
  { part: "sounds", label: "Change recordings", about: "Add or remove the recordings the voice is made from." },
  { part: "accent", label: "Change accent", about: "Keep the person's own accent or choose another one." },
];

// Whose avatar the chat uses now, once the server has said: with "own-photo", the user's own
// photo with the ready-made avatar's voice (R24d).
type InUse = "own" | "ready-made" | "own-photo";

// Use my own photo (R24d): keep the avatar's voice, and open setup at the photos, after asking
// for consent for the photos if none was given. Throws an Error saying why when refused.
export async function chooseOwnPhoto(from: string): Promise<void> {
  const started = performance.now();
  await setOwnPhoto(true);
  const consent = await getConsent();
  const took = Math.round(performance.now() - started);
  console.info(`Using your own photo with the avatar's voice, from ${from} (${took} ms)`);
  window.location.hash = consent.agreed ? "#/setup/photos" : "#/consent";
}

// Your own photo and voice, from Use my own photo (R24d): setup then asks for both.
export async function ownPhotoAndVoice(): Promise<void> {
  await setOwnPhoto(false);
  window.location.hash = "#/setup";
}

// Back to the avatar's own picture, keeping its voice (R24d).
async function useAvatarPicture(): Promise<void> {
  await setOwnPhoto(false);
  console.info("Using the avatar's picture again from Settings");
}

function InUseMark({ shown }: { shown: boolean }) {
  return shown ? <span className="in-use">In use</span> : null;
}

export function ChangeSetup() {
  // null until the server has answered, or if it couldn't (before consent, say).
  const [accepted, setAccepted] = useState<boolean | null>(null);
  const [inUse, setInUse] = useState<InUse | null>(null);
  // Use my own photo is set up, but its sample isn't accepted yet (R24d).
  const [ownPhotoPending, setOwnPhotoPending] = useState(false);
  const [ownPhotoMode, setOwnPhotoMode] = useState(false); // Use my own photo was chosen
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [reads, setReads] = useState(0);

  useEffect(() => {
    const started = performance.now();
    getReview()
      .then((r) => {
        const ownPhoto = r.own_photo === true && r.sample_accepted === true;
        const avatar = !r.default_person ? "own" : ownPhoto ? "own-photo" : "ready-made";
        setAccepted(r.accepted);
        setInUse(avatar);
        setOwnPhotoPending(r.own_photo === true && !ownPhoto);
        setOwnPhotoMode(r.own_photo === true);
        const took = Math.round(performance.now() - started);
        console.info(`Sample accepted: ${r.accepted}, avatar in use: ${avatar} (${took} ms)`);
      })
      .catch((e: unknown) => console.error("Could not get the review", e));
  }, [reads]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setFailed(null);
    try {
      await action();
      setReads((n) => n + 1);
    } catch (e) {
      console.error("Could not change the avatar", e);
      setFailed((e as Error).message);
    }
    setBusy(false);
  }
  const readyMade = inUse === "ready-made" || inUse === "own-photo";

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
          {readyMade ? (
            <div className="switch">
              <a
                className="button secondary"
                href="#/setup"
                onClick={(e) => {
                  console.info("Switching to your own photo and voice from Settings");
                  if (!ownPhotoMode) return;
                  e.preventDefault(); // setup would otherwise ask for the photo only
                  void run(ownPhotoAndVoice);
                }}
              >
                Use your own photo and voice
              </a>
              <p className="muted">
                Your photos and recordings are kept. Accept their sample video at the end of setup
                to switch.
              </p>
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
        <div className={readyMade ? "avatar-option chosen" : "avatar-option"}>
          <h3>
            Ready-made avatar <InUseMark shown={readyMade} />
          </h3>
          <p className="muted">
            {inUse === "own-photo"
              ? "Your own photo, speaking in the ready-made avatar's voice."
              : "A made-up person in a ready-made voice, chosen by gender, accent and look. Your own photos and recordings are kept."}
          </p>
          <div className="switch">
            <a
              className="button secondary"
              href="#/start-now"
              onClick={() => console.info("Choosing a ready-made avatar from Settings")}
            >
              {readyMade ? "Choose another avatar" : "Use a ready-made avatar"}
            </a>
          </div>
          {inUse === "ready-made" && (
            <div className="switch">
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => void run(() => chooseOwnPhoto("Settings"))}
              >
                Use my own photo
              </button>
              <p className="muted">
                {ownPhotoPending
                  ? "Your photo's sample video isn't accepted yet. Accept it at the end of setup to see your photo in the chat."
                  : "Keep this voice and replace the picture with your own photo."}
              </p>
            </div>
          )}
          {inUse === "own-photo" && (
            <>
              <div className="switch">
                <a
                  className="button secondary"
                  href="#/setup/photos"
                  onClick={() => console.info("Changing your own photo from Settings")}
                >
                  Change your photo
                </a>
              </div>
              <div className="switch">
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => void run(useAvatarPicture)}
                >
                  Use the avatar's picture again
                </button>
              </div>
            </>
          )}
          {failed && <p className="error">{failed}</p>}
        </div>
      </div>
    </section>
  );
}
