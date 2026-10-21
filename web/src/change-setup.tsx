// Avatar Choice on the Settings page: the person in the video is either the user's own photo and
// voice or a ready-made avatar, side by side, so switching between them happens in one place
// (Larry's test of R32a). Under their own, each change opens setup at that part (roadmap R28);
// whatever is changed there needs a new sample video, accepted, before the chat opens again, and
// Prepare makes Goodbye and Welcome back again with it.

import { useEffect, useState } from "preact/hooks";

import { getReview, useAvatarReadyVoice, useOwnPerson } from "./api";
import { OWN_CONSENT, type SetupPart } from "./router";

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

// After Before you start, shown again when choosing your own image and voice over a ready-made
// avatar (Larry's test of PR #131).
export async function ownAfterConsent(): Promise<void> {
  const review = await getReview();
  await switchToOwn(review.default_person === true && review.own_sample_accepted === true, "Before you start");
}

function InUseMark({ shown }: { shown: boolean }) {
  return shown ? <span className="in-use">In use</span> : null;
}

export function ChangeSetup() {
  // null until the server has answered, or if it couldn't (before consent, say).
  const [accepted, setAccepted] = useState<boolean | null>(null);
  const [inUse, setInUse] = useState<InUse | null>(null);
  const [ownAccepted, setOwnAccepted] = useState(false); // their own sample, with an avatar in use
  // The avatar is to speak in the user's voice (R24d), and does once its sample is accepted.
  const [readyVoiceBusy, setReadyVoiceBusy] = useState(false);
  const [readyVoiceDone, setReadyVoiceDone] = useState(false);
  const [readyVoiceFailed, setReadyVoiceFailed] = useState<string | null>(null);
  const [avatarVoice, setAvatarVoice] = useState<{ chosen: boolean; accepted: boolean }>({
    chosen: false,
    accepted: false,
  });

  useEffect(() => {
    const started = performance.now();
    getReview()
      .then((r) => {
        const avatar = r.default_person ? "ready-made" : "own";
        setAccepted(r.accepted);
        setInUse(avatar);
        setOwnAccepted(r.own_sample_accepted === true);
        setAvatarVoice({ chosen: r.own_voice === true, accepted: r.voice_accepted === true });
        const took = Math.round(performance.now() - started);
        console.info(`Sample accepted: ${r.accepted}, avatar in use: ${avatar} (${took} ms)`);
      })
      .catch((e: unknown) => console.error("Could not get the review", e));
  }, []);

  async function readyVoice() {
    const started = performance.now();
    setReadyVoiceBusy(true);
    setReadyVoiceFailed(null);
    try {
      await useAvatarReadyVoice();
      setAvatarVoice({ chosen: false, accepted: false });
      setReadyVoiceDone(true);
      console.info(`Avatar's default voice used again from Settings (${Math.round(performance.now() - started)} ms)`);
    } catch (e) {
      console.error("Could not use the avatar's ready-made voice again", e);
      setReadyVoiceFailed((e as Error).message);
    }
    setReadyVoiceBusy(false);
  }

  // The avatar speaks in its ready-made voice: chosen, and not (yet) in the user's own.
  const defaultVoice = inUse === "ready-made" && !avatarVoice.accepted;
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
                href={OWN_CONSENT}
                onClick={() => console.info("Switching to your own photo and voice from Settings")}
              >
                Use your own photo and voice
              </a>
              <p className="muted">
                {ownAccepted
                  ? "Your sample video is already accepted: the chat switches to it at once."
                  : "Your photos and recordings are kept. Accept their sample video at the end of setup to switch."}
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
          {inUse === "ready-made" && (
            <div className="switch">
              <a
                className="button secondary"
                href="#/avatar-voice"
                onClick={() => console.info("Giving the avatar your own voice from Settings")}
              >
                {avatarVoice.chosen ? "Change your voice for the avatar" : "Use my own voice"}
              </a>
              <p className="muted">
                {avatarVoice.accepted
                  ? "The avatar speaks in your voice, made from your recordings."
                  : avatarVoice.chosen
                    ? "The avatar speaks in its ready-made voice until you accept the sample video in your voice."
                    : "Keep the avatar's picture and replace its voice with one made from your recordings."}
              </p>
            </div>
          )}
        </div>
        {/* The third choice (Larry's test of PR #131): the avatar in its own ready-made voice,
            back in one click with nothing to accept. Your recordings are kept. */}
        <div className={defaultVoice ? "avatar-option chosen" : "avatar-option"}>
          <h3>
            Default voice for the avatar <InUseMark shown={defaultVoice} />
          </h3>
          <p className="muted">
            The ready-made avatar speaks in its own ready-made voice. There is nothing to accept,
            and your recordings are kept.
          </p>
          {inUse === "ready-made" && avatarVoice.chosen && (
            <div className="switch">
              <button
                type="button"
                className={readyVoiceBusy ? "secondary busy" : "secondary"}
                disabled={readyVoiceBusy}
                onClick={() => void readyVoice()}
              >
                Use the Default Voice for the Avatar
              </button>
              <p className="muted">Switches back at once.</p>
            </div>
          )}
          {inUse === "own" && (
            <div className="switch">
              <a
                className="button secondary"
                href="#/start-now"
                onClick={() => console.info("Choosing an avatar in its default voice from Settings")}
              >
                Use the Default Voice for the Avatar
              </a>
              <p className="muted">Choose an avatar: it starts in its default voice.</p>
            </div>
          )}
          {readyVoiceDone && <p className="done">The avatar speaks in its default voice again.</p>}
          {readyVoiceFailed && <p className="error">{readyVoiceFailed}</p>}
        </div>
      </div>
    </section>
  );
}
