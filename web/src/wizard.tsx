// The setup wizard (roadmap R131): setting up with your own photo and voice one step at a time,
// one step per screen with Back and Next. It uses the same pieces as the Setup page. The photo is
// taken with the camera (R132) and the voice recorded in the browser (R133), or either picked as
// files.

import { useEffect, useRef, useState } from "preact/hooks";

import {
  clipUrl,
  confirmConsent,
  getPhotoChoice,
  getPrepare,
  getWizardStep,
  type PrepareStatus,
  saveWizardStep,
  WIZARD_STEPS,
  type WizardStep,
} from "./api";
import { useLeaveGuard } from "./leave-guard";
import { CameraPhoto } from "./camera";
import { VoiceRecorder } from "./recorder";
import { AccentSection, PrepareSection, ReviewChoices, UploadSection } from "./pages";
import { type SetupPart } from "./router";
import { SettingGuard, usePrepareStopGuard } from "./setting-guard";

export const STEP_TITLES: Record<WizardStep, string> = {
  start: "Before you start",
  photo: "Your photo",
  voice: "Your voice",
  accent: "Accent",
  prepare: "Prepare the video",
  review: "Watch the sample video",
};

// A choice under the sample video that sends the user back (R14) opens that step.
const BACK_STEP: Record<SetupPart, WizardStep> = {
  photos: "photo",
  sounds: "voice",
  accent: "accent",
};

// The step after `step`, or before it, in order.
export function nextStep(step: WizardStep, by: 1 | -1): WizardStep {
  const i = WIZARD_STEPS.indexOf(step) + by;
  return WIZARD_STEPS[Math.min(Math.max(i, 0), WIZARD_STEPS.length - 1)];
}

export function WizardPage(props: { consented: boolean; onConsented: () => void }) {
  // null until the server has said which step was reached.
  const [step, setStep] = useState<WizardStep | null>(null);
  const opened = useRef(performance.now());
  // Whether Next can be clicked yet: each step's checks have to be known first.
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  // Counts changes to the photo, the recordings and the accent, so Prepare reads its job again.
  const [changes, setChanges] = useState(0);
  const changed = () => setChanges((n) => n + 1);
  const [preparing, setPreparing] = useState(false);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  // Set while a step change is being saved: Back and Next wait for it, so a double click can't
  // send two changes from the same step whose answers could arrive out of order (Codex's review
  // of PR #224).
  const [moving, setMoving] = useState(false);
  const movingNow = useRef(false);
  const leaveDialog = useLeaveGuard(pending, "The chat keeps the person and voice it has now.");
  const stopGuard = usePrepareStopGuard(changed);

  useEffect(() => {
    const started = performance.now();
    getWizardStep()
      .then((saved) => {
        // Before consent, the wizard always starts at the beginning.
        const first = props.consented ? saved : "start";
        console.info(
          `Wizard opened at ${first} (read in ${Math.round(performance.now() - started)} ms)`,
        );
        opened.current = performance.now();
        setStep(first);
      })
      .catch((e: unknown) => {
        console.error("Could not read the wizard's step; starting at the beginning", e);
        setStep("start");
      });
  }, []);

  async function go(to: WizardStep, why: string | null = null) {
    if (step === null || movingNow.current) return;
    movingNow.current = true;
    setMoving(true);
    console.info(
      `Wizard step: ${to} (${Math.round((performance.now() - opened.current) / 1000)} s on ${step})`,
    );
    setFailed(null);
    try {
      await saveWizardStep(to);
    } catch (e) {
      // The step still opens; only coming back to it later is lost.
      console.error(`Could not save the wizard's step (${to})`, e);
    }
    opened.current = performance.now();
    setReady(false);
    setNotice(why);
    setStep(to);
    movingNow.current = false;
    setMoving(false);
    window.scrollTo?.({ top: 0 });
  }

  if (step === null) return <p className="muted busy">Loading…</p>;
  const index = WIZARD_STEPS.indexOf(step);
  const last = index === WIZARD_STEPS.length - 1;

  let body;
  switch (step) {
    case "start":
      body = (
        <StartStep
          consented={props.consented}
          onReady={setReady}
          onConsented={props.onConsented}
          onFailed={setFailed}
        />
      );
      break;
    case "photo":
      body = <PhotoStep notice={notice} onReady={setReady} onChange={changed} />;
      break;
    case "voice":
      body = <VoiceStep notice={notice} onReady={setReady} onChange={changed} />;
      break;
    case "accent":
      body = (
        <AccentStep notice={notice} preparing={preparing} onReady={setReady} onChange={changed} />
      );
      break;
    case "prepare":
      body = (
        <PrepareSection
          changes={changes}
          onRunning={setPreparing}
          onBack={(to) => void go(BACK_STEP[to])}
          onStopped={stopGuard.onStopped}
          wizard={{ onDone: setReady }}
        />
      );
      break;
    case "review":
      body = (
        <ReviewStep
          onBack={(to, why) => void go(BACK_STEP[to], why)}
          onPending={setPending}
        />
      );
      break;
  }

  return (
    <SettingGuard.Provider value={stopGuard.guard}>
      <div className="host-page wizard">
        <h1>Set up with your own photo and voice</h1>
        <ol className="wizard-steps" aria-label="Steps">
          {WIZARD_STEPS.map((s, i) => (
            <li
              key={s}
              className={i === index ? "current" : i < index ? "done" : undefined}
              aria-current={i === index ? "step" : undefined}
            >
              {STEP_TITLES[s]}
            </li>
          ))}
        </ol>
        <p className="step-of">
          Step {index + 1} of {WIZARD_STEPS.length}
        </p>
        {body}
        {failed && <p className="error">{failed}</p>}
        <div className="wizard-nav">
          <button
            type="button"
            className="secondary"
            disabled={index === 0 || moving}
            onClick={() => void go(nextStep(step, -1))}
          >
            Back
          </button>
          {!last && (
            <button type="button" disabled={!ready || moving} onClick={() => void go(nextStep(step, 1))}>
              Next
            </button>
          )}
        </div>
        <p className="muted">
          Prefer everything on one page? <a href="#/setup">Open the Setup page</a>.
        </p>
        {leaveDialog}
        {stopGuard.dialog}
      </div>
    </SettingGuard.Provider>
  );
}

// What is needed, and the consent (R5). Next saves the consent when it was just ticked.
function StartStep(props: {
  consented: boolean;
  onReady: (ready: boolean) => void;
  onConsented: () => void;
  onFailed: (why: string | null) => void;
}) {
  const [checked, setChecked] = useState(props.consented);
  const [saving, setSaving] = useState(false);
  useEffect(() => props.onReady(props.consented), [props.consented]);

  async function agree(yes: boolean) {
    setChecked(yes);
    if (!yes || props.consented) return;
    setSaving(true);
    props.onFailed(null);
    try {
      await confirmConsent();
      console.info("Consent confirmed in the wizard");
      props.onConsented();
    } catch (e) {
      console.error("Could not save consent from the wizard", e);
      props.onFailed("Could not save your answer. Please try again.");
      setChecked(false);
    }
    setSaving(false);
  }

  return (
    <section className="panel">
      <h2>{STEP_TITLES.start}</h2>
      <p>You will need:</p>
      <ul className="needs">
        <li>A clear photo of your face, head and shoulders, looking at the camera.</li>
        <li>A few minutes of your voice, reading aloud in a quiet room. This is optional: without it, a ready-made voice speaks.</li>
        <li>About 20 minutes the first time, while the app prepares the video.</li>
      </ul>
      <p>Only use images you have the right to use. Ideally, use your own picture.</p>
      <label className="check">
        <input
          type="checkbox"
          checked={checked}
          disabled={props.consented || saving}
          onChange={(e) => void agree(e.currentTarget.checked)}
        />{" "}
        I have the right to use the photos and recording that will be used by the app.
      </label>
    </section>
  );
}

// The photo: Next waits for one that passed its checks (R8).
function PhotoStep(props: {
  notice: string | null;
  onReady: (ready: boolean) => void;
  onChange: () => void;
}) {
  const [changes, setChanges] = useState(0);
  // Read again after a photo is taken with the camera, so the list shows it.
  const [taken, setTaken] = useState(0);
  // Next waits until the new choice is read, so a photo just removed can't be used to go on
  // (Codex's review of PR #224).
  function changing(busy: boolean) {
    props.onReady(false);
    if (!busy) setChanges((n) => n + 1); // over: read the choice again
  }
  useEffect(() => {
    let newest = true;
    getPhotoChoice()
      .then((c) => {
        if (newest) props.onReady(Boolean(c.id));
      })
      .catch((e: unknown) => console.error("Could not read the chosen photo", e));
    return () => {
      newest = false;
    };
  }, [changes]);
  return (
    <>
      <section className="panel">
        <h2>{STEP_TITLES.photo}</h2>
        {props.notice && <p className="notice">{props.notice}</p>}
        <ul className="tips">
          <li>Face the camera, with your head and shoulders inside the outline.</li>
          <li>Use soft, even light from the front, with a plain background.</li>
          <li>Keep a neutral face with your mouth closed.</li>
        </ul>
        <CameraPhoto
          onChanging={changing}
          onAdded={() => {
            setTaken((n) => n + 1);
            props.onChange();
          }}
        />
      </section>
      <UploadSection
        key={taken}
        kind="photos"
        step={null}
        title="Your photos"
        button="Add a photo file"
        hint="The photos you took, and any you add as files (JPG, PNG or HEIC). Next is ready once one passes the checks."
        accept="image/jpeg,image/png,image/heic,.heic"
        notice={null}
        onChanging={changing}
        onChange={() => {
          props.onReady(false);
          setChanges((n) => n + 1);
          props.onChange();
        }}
      />
    </>
  );
}

// The recordings are optional (a ready-made voice speaks without them), so Next is always ready.
function VoiceStep(props: {
  notice: string | null;
  onReady: (ready: boolean) => void;
  onChange: () => void;
}) {
  // Optional: Next is ready except while recording, or while a recording is checked.
  useEffect(() => props.onReady(true), []);
  // Read again after a recording is made, so the list shows it.
  const [made, setMade] = useState(0);
  return (
    <>
      <section className="panel">
        <h2>Record your voice</h2>
        {props.notice && <p className="notice">{props.notice}</p>}
        <ul className="tips">
          <li>Record in a quiet room, about a hand&apos;s width from the microphone.</li>
          <li>Read aloud in your normal voice.</li>
          <li>Only your voice: no music, television or other people.</li>
        </ul>
        <VoiceRecorder
          onChanging={(busy) => props.onReady(!busy)}
          onAdded={() => {
            setMade((n) => n + 1);
            props.onChange();
          }}
        />
      </section>
      <UploadSection
        key={made}
        kind="sounds"
        step={null}
        title="Your recordings"
        button="Add a recording file"
        hint="The recordings you made, and any you add as files (WAV, M4A or MP3, up to 10 minutes each). Optional: without them, a ready-made voice speaks."
        accept="audio/*,.m4a,.wav,.mp3"
        notice={null}
        onChange={props.onChange}
      />
    </>
  );
}

function AccentStep(props: {
  notice: string | null;
  preparing: boolean;
  onReady: (ready: boolean) => void;
  onChange: () => void;
}) {
  useEffect(() => props.onReady(true), []);
  return (
    <AccentSection
      onChange={props.onChange}
      preparing={props.preparing}
      notice={props.notice}
      numbered={false}
    />
  );
}

const BACK_NOTICE: Record<SetupPart, string> = {
  photos: "You rejected the image. Add a new photo and remove the ones you don't want.",
  sounds: "You rejected the voice. Add new recordings and remove the ones you don't want.",
  accent: "Choose another accent.",
};

// The sample video (R13) and the review (R14): Accept opens the chat; a reject goes back to its
// step.
function ReviewStep(props: {
  onBack: (to: SetupPart, why: string) => void;
  onPending: (pending: boolean) => void;
}) {
  // null until the server has answered.
  const [status, setStatus] = useState<PrepareStatus | null>(null);
  useEffect(() => {
    getPrepare()
      .then(setStatus)
      .catch((e: unknown) => console.error("Could not read the sample video", e));
  }, []);
  if (status === null) return <p className="muted busy">Loading…</p>;
  if (status.state !== "done") {
    return (
      <section className="panel">
        <h2>{STEP_TITLES.review}</h2>
        <p className="notice">The sample video isn&apos;t ready. Go Back to prepare it.</p>
      </section>
    );
  }
  return (
    <section className="panel sample-video">
      <h2>{STEP_TITLES.review}</h2>
      <video controls preload="metadata" src={clipUrl("sample", status)} aria-label="Sample video" />
      <ReviewChoices
        sample={status.finished_at}
        onBack={(to) => props.onBack(to, BACK_NOTICE[to])}
        onPending={props.onPending}
      />
    </section>
  );
}
