// A ready-made avatar in your own voice (roadmap R24d): the avatar's picture stays, and its
// ready-made voice is replaced by one made from the user's recordings, through consent for the
// person in them, the sound checks, the accent, Prepare and review, as in setup. Until that
// sample is accepted, the avatar keeps speaking in its ready-made voice.

import { useEffect, useState } from "preact/hooks";

import { DEFAULT_PICTURE, getReview, type Review, useAvatarOwnVoice, useAvatarReadyVoice } from "./api";
import { useLeaveGuard } from "./leave-guard";
import { AccentSection, PrepareSection, StepOf, UploadSection } from "./pages";
import type { SetupPart } from "./router";

const BACK_NOTICE: Partial<Record<SetupPart, string>> = {
  sounds: "You rejected the voice. Add new recordings and remove the ones you don't want, then Prepare again.",
  accent: "Choose another accent. The sample video is then made again.",
};

export function AvatarVoicePage() {
  // null until the server has answered.
  const [current, setCurrent] = useState<Review | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [changes, setChanges] = useState(0);
  const changed = () => setChanges((n) => n + 1);
  const [preparing, setPreparing] = useState(false);
  const [back, setBack] = useState<SetupPart | null>(null);
  const [pending, setPending] = useState(false);
  const leaveDialog = useLeaveGuard(pending, "The avatar keeps the voice it has now.");

  useEffect(() => {
    const started = performance.now();
    getReview()
      .then((r) => {
        setCurrent(r);
        const took = Math.round(performance.now() - started);
        console.info(`Avatar in your own voice: ${r.own_voice === true}, accepted: ${r.voice_accepted === true} (${took} ms)`);
      })
      .catch((e: unknown) => {
        console.error("Could not get the review", e);
        setFailed("Could not load the page. Reload it to try again.");
      });
  }, []);

  if (current === null) {
    return failed ? <p className="error">{failed}</p> : <p className="muted busy">Loading…</p>;
  }
  if (!current.default_person) {
    return (
      <>
        <h1>Your voice for an avatar</h1>
        <p>Choose a ready-made avatar first, then give it your voice.</p>
        <a className="button" href="#/start-now">
          Choose an avatar
        </a>
      </>
    );
  }
  if (!current.own_voice) return <VoiceConsent onAgreed={setCurrent} />;

  async function readyVoice() {
    const started = performance.now();
    setFailed(null);
    try {
      await useAvatarReadyVoice();
      console.info(`Avatar's ready-made voice used again (${Math.round(performance.now() - started)} ms)`);
      window.location.hash = "#/chat";
    } catch (e) {
      console.error("Could not use the avatar's ready-made voice again", e);
      setFailed((e as Error).message);
    }
  }

  const notice = (part: SetupPart) => (back === part ? (BACK_NOTICE[part] ?? null) : null);
  return (
    <div className="host-page">
      <h1>Your voice for the avatar</h1>
      <p className="lead">
        The avatar keeps its picture and speaks in a voice made from your recordings. Add them,
        choose an accent, then prepare a sample video and check it. Until you accept it, the
        avatar speaks in its ready-made voice.
      </p>
      <p className="avatar-instead">
        Rather keep its ready-made voice?{" "}
        <button type="button" className="link" onClick={() => void readyVoice()}>
          Use the avatar&apos;s ready-made voice
        </button>
        . Your recordings are kept.
      </p>
      {failed && <p className="error">{failed}</p>}
      <section className="panel" id="photos">
        <StepOf n={1} />
        <h2>Picture</h2>
        <p className="muted">The ready-made avatar&apos;s picture, already prepared.</p>
        <img className="avatar-picture" src={DEFAULT_PICTURE} alt="The ready-made avatar" />
      </section>
      <UploadSection
        kind="sounds"
        step={2}
        title="Voice recordings"
        button="Add recordings"
        hint="Add the voice recordings from the recording guide (WAV, M4A or MP3, up to 10 minutes each)."
        accept="audio/*,.m4a,.wav,.mp3"
        notice={notice("sounds")}
        onChange={changed}
      />
      <AccentSection onChange={changed} preparing={preparing} notice={notice("accent")} />
      <PrepareSection
        changes={changes}
        onRunning={setPreparing}
        onPending={setPending}
        avatarVoice
        onBack={(to) => {
          setBack(to);
          window.setTimeout(() => document.getElementById(to)?.scrollIntoView?.({ behavior: "smooth" }));
        }}
      />
      {leaveDialog}
    </div>
  );
}

// Consent for the person in the recordings (feature item 59): that they agreed to have their
// voice copied. The avatar's picture is of a made-up person, so it needs none.
function VoiceConsent({ onAgreed }: { onAgreed: (review: Review) => void }) {
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  async function submit(event: Event) {
    event.preventDefault();
    const started = performance.now();
    setSaving(true);
    setFailed(null);
    try {
      const review = await useAvatarOwnVoice();
      console.info(`Avatar to speak in your own voice (${Math.round(performance.now() - started)} ms)`);
      onAgreed(review);
    } catch (e) {
      console.error("Could not give the avatar your voice", e);
      setFailed((e as Error).message);
      setSaving(false);
    }
  }

  return (
    <>
      <h1>Your voice for the avatar</h1>
      <p>
        The avatar keeps its picture and speaks in a voice made from recordings you add. Only use
        recordings of someone who has agreed to this, or of yourself.
      </p>
      <form onSubmit={submit}>
        <label className="check">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.currentTarget.checked)}
          />{" "}
          The person in the recordings I will upload agreed to have their voice copied by this app.
        </label>
        <button type="submit" disabled={!checked || saving}>
          Continue
        </button>
        <a className="button secondary" href="#/settings">
          Cancel
        </a>
        {failed && <p className="error">{failed}</p>}
      </form>
    </>
  );
}
