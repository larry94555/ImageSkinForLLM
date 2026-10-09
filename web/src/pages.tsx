// The app's pages. Each one is a function that returns what the page shows.

import { useEffect, useRef, useState } from "preact/hooks";

import {
  type Accent,
  type AccentChoice,
  checkUpload,
  chooseAccent,
  choosePhoto,
  confirmConsent,
  type Decision,
  getAccent,
  getPhotoChoice,
  clipUrl,
  getPrepare,
  getReview,
  getVoiceSample,
  type Kind,
  listUploads,
  type PhotoChoice,
  type PrepareStatus,
  type PrepareStep,
  removeUpload,
  type Review,
  review,
  startPrepare,
  type Upload,
  uploadFile,
  uploadUrl,
  type VoiceSample,
  voiceSampleAudioUrl,
} from "./api";

export function HomePage({ consented }: { consented: boolean }) {
  return (
    <>
      <h1>Welcome</h1>
      <p>
        Set up a talking video of a person from a few photos and voice recordings. The person then
        speaks the chatbot&apos;s replies.
      </p>
      <a className="button" href={consented ? "#/setup" : "#/consent"}>
        Start setup
      </a>
    </>
  );
}

export function ConsentPage({ onConfirmed }: { onConfirmed: () => void }) {
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  async function submit(event: Event) {
    event.preventDefault();
    setSaving(true);
    setError(false);
    try {
      await confirmConsent();
      onConfirmed();
    } catch (e) {
      console.error("Could not save consent", e);
      setError(true);
      setSaving(false);
    }
  }

  return (
    <>
      <h1>Before you start</h1>
      <p>Only use photos and recordings of someone who has agreed to this, or of yourself.</p>
      <form onSubmit={submit}>
        <label className="check">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.currentTarget.checked)}
          />{" "}
          The person in the photos and recordings I will upload agreed to have their face and voice
          copied by this app.
        </label>
        <button type="submit" disabled={!checked || saving}>
          Continue
        </button>
        {error && <p className="error">Could not save your answer. Please try again.</p>}
      </form>
    </>
  );
}

// Where a choice under the sample video sends the user back to (roadmap R14).
type Back = "photos" | "sounds" | "accent";

const BACK_NOTICE: Record<Back, string> = {
  photos: "You rejected the image. Add new photos and remove the ones you don't want, then Prepare again.",
  sounds: "You rejected the voice. Add new recordings and remove the ones you don't want, then Prepare again.",
  accent: "Choose another accent. The sample video is then made again.",
};

// Setup: upload photos and recordings, see them and play them back (roadmap R7), choose the
// accent (R26), prepare the voice and the face (R12), then review the sample video (R14).
export function SetupPage() {
  // Counts changes to the photos, the chosen photo and the recordings, so Prepare asks again
  // whether what it prepared is still current.
  const [changes, setChanges] = useState(0);
  const changed = () => setChanges((n) => n + 1);
  // While Prepare runs, the accent can't change: the running job would finish in the old one.
  const [preparing, setPreparing] = useState(false);
  // Set when the user rejected the sample: the section to go back to shows what to do there.
  const [back, setBack] = useState<Back | null>(null);
  function goBack(to: Back) {
    setBack(to);
    // After the notice shows, so the page scrolls to where it ends up.
    window.setTimeout(() => document.getElementById(to)?.scrollIntoView?.({ behavior: "smooth" }));
  }
  const notice = (to: Back) => (back === to ? BACK_NOTICE[to] : null);
  return (
    <>
      <h1>Setup</h1>
      <p className="done">Thank you, consent is confirmed.</p>
      <UploadSection
        kind="photos"
        title="Photos"
        hint="Add the five photos from the recording guide (JPG, PNG or HEIC). At least one is needed; the app will pick the best."
        accept="image/jpeg,image/png,image/heic,.heic"
        notice={notice("photos")}
        onChange={changed}
      />
      <UploadSection
        kind="sounds"
        title="Recordings"
        hint="Add the voice recordings from the recording guide (WAV, M4A or MP3, up to 10 minutes each)."
        accept="audio/*,.m4a,.wav,.mp3"
        notice={notice("sounds")}
        onChange={changed}
      />
      <AccentSection onChange={changed} preparing={preparing} notice={notice("accent")} />
      <PrepareSection changes={changes} onRunning={setPreparing} onBack={goBack} />
    </>
  );
}

interface Refused {
  name: string;
  reason: string;
}

function UploadSection(props: {
  kind: Kind;
  title: string;
  hint: string;
  accept: string;
  notice: string | null; // what to do after rejecting the sample (roadmap R14)
  onChange: () => void; // a file was added, passed its checks or removed, or a photo chosen
}) {
  const { kind } = props;
  // null until the list has loaded.
  const [items, setItems] = useState<Upload[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [sending, setSending] = useState<string | null>(null);
  const [refused, setRefused] = useState<Refused[]>([]);
  // Uploads still to be checked, in order; the first one is being checked now.
  const [toCheck, setToCheck] = useState<string[]>([]);
  // Sounds only (roadmap R10): counts changes to the recordings, so the voice sample is read again.
  const [soundChanges, setSoundChanges] = useState(0);
  // Photos only (roadmap R9): the one the video will be made from.
  const [choice, setChoice] = useState<PhotoChoice | null>(null);
  const [choosing, setChoosing] = useState<string | null>(null);

  // Each read or change of the choice gets the next number. Only the newest request's answer is
  // shown, so a slow read can't put back an older choice: neither the one from before the user's
  // click, nor an older best photo after a newer read has answered.
  const choiceRequests = useRef(0);

  // Asked again whenever the photos or their checks change, since the best one may change.
  async function refreshChoice() {
    if (kind !== "photos") return;
    const request = ++choiceRequests.current;
    try {
      const current = await getPhotoChoice();
      if (request === choiceRequests.current) setChoice(current);
    } catch (e) {
      console.error("Could not get the chosen photo", e);
    }
  }

  async function choose(item: Upload) {
    if (choosing !== null) return; // one at a time
    const sent = ++choiceRequests.current; // reads sent before this click are now out of date
    setChoosing(item.id);
    setRefused([]);
    try {
      const chosen = await choosePhoto(item.id);
      // Reads sent while this change was on its way may have seen the old choice: drop them too,
      // and ask again if there were any, since something else changed meanwhile.
      const readWhileSaving = choiceRequests.current > sent;
      ++choiceRequests.current;
      setChoice(chosen);
      props.onChange();
      if (readWhileSaving) void refreshChoice();
    } catch (e) {
      console.error(`Could not choose ${item.name}`, e);
      setRefused([{ name: item.name, reason: (e as Error).message }]);
    }
    setChoosing(null);
  }

  useEffect(() => {
    listUploads(kind)
      .then((list) => {
        setItems(list);
        void checkOld(list);
        void refreshChoice();
      })
      .catch((e: unknown) => {
        console.error(`Could not list ${kind}`, e);
        setLoadFailed(true);
      });
  }, [kind]);

  // Something about the uploads changed: read the voice sample again, and tell the page.
  function uploadsChanged() {
    if (kind === "sounds") setSoundChanges((n) => n + 1);
    props.onChange();
  }

  // Uploads stored before the checks were on are checked one at a time after the list shows,
  // so the page doesn't wait for them.
  async function checkOld(list: Upload[]) {
    const unchecked = list.filter((u) => u.problems === null);
    setToCheck(unchecked.map((u) => u.id));
    for (const upload of unchecked) {
      try {
        const checked = await checkUpload(kind, upload.id);
        setItems((current) => (current ?? []).map((i) => (i.id === checked.id ? checked : i)));
        if (checked.problems === null) break; // checks are off; the rest would be the same
        if (checked.problems.length === 0) {
          await refreshChoice();
          uploadsChanged();
        }
      } catch (e) {
        console.error(`Could not check ${upload.name}`, e); // removed meanwhile, or server down
      }
      setToCheck((ids) => ids.slice(1));
    }
    setToCheck([]);
  }

  // One file at a time, so each refusal is shown next to the file's name.
  async function add(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = "";
    setRefused([]);
    for (const file of files) {
      setSending(file.name);
      try {
        const upload = await uploadFile(kind, file);
        setItems((current) => [...(current ?? []), upload]);
        if (upload.problems?.length === 0) {
          await refreshChoice();
          uploadsChanged();
        }
      } catch (e) {
        console.error(`Upload of ${file.name} refused`, e);
        setRefused((current) => [...current, { name: file.name, reason: (e as Error).message }]);
      }
    }
    setSending(null);
  }

  async function remove(item: Upload) {
    if (!window.confirm(`Remove ${item.name}?`)) return;
    try {
      await removeUpload(kind, item.id);
      setItems((current) => (current ?? []).filter((i) => i.id !== item.id));
      // Always asked, not only when it was the chosen one: it may be the one being chosen now.
      await refreshChoice();
      uploadsChanged();
    } catch (e) {
      console.error(`Could not remove ${item.name}`, e);
      setRefused([{ name: item.name, reason: "Could not remove it. Please try again." }]);
    }
  }

  // Adding waits for the first list, so a late list can't hide a file uploaded meanwhile.
  const ready = sending === null && (items !== null || loadFailed);
  const loading = items === null && !loadFailed;

  return (
    <section id={kind}>
      <h2>{props.title}</h2>
      {props.notice && <p className="notice">{props.notice}</p>}
      <p className="muted">{props.hint}</p>
      <label className={ready ? "button" : "button busy"}>
        {sending
          ? `Uploading and checking ${sending}…`
          : loading
            ? "Loading…"
            : `Add ${props.title.toLowerCase()}`}
        <input
          type="file"
          multiple
          accept={props.accept}
          disabled={!ready}
          onChange={add}
          className="file"
        />
      </label>
      {refused.map((r) => (
        <p key={r.name} className="error">
          {r.name}: {r.reason}
        </p>
      ))}
      {loadFailed && <p className="error">Could not load the list. Reload the page to try again.</p>}
      {loading && <p className="muted busy">Loading your {props.title.toLowerCase()}…</p>}
      {items?.length === 0 && <p className="muted">None yet.</p>}
      <ul className={kind}>
        {items?.map((item) => (
          <li key={item.id} className={item.id === choice?.id ? "chosen" : undefined}>
            {kind === "photos" ? (
              <a href={uploadUrl(kind, item.id)} target="_blank" rel="noreferrer">
                <img src={uploadUrl(kind, item.id)} alt={item.name} />
              </a>
            ) : (
              <audio controls preload="none" src={uploadUrl(kind, item.id)} />
            )}
            <span className="name">
              {item.name}
              {item.seconds !== null && ` (${minutes(item.seconds)})`}
            </span>
            <Checks item={item} queue={toCheck.indexOf(item.id)} />
            {kind === "photos" && item.id === choice?.id && (
              <span className="chosen-note">
                Used for the video
                {choice.chosen_by === "app" ? " (best score)" : " (your choice)"}
              </span>
            )}
            {kind === "photos" && item.problems?.length === 0 && item.id !== choice?.id && (
              <button
                type="button"
                className={choosing === item.id ? "use busy" : "use"}
                onClick={() => choose(item)}
              >
                {choosing === item.id ? "Saving…" : "Use this photo"}
              </button>
            )}
            <button type="button" className="remove" onClick={() => remove(item)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      {kind === "sounds" && <VoiceSampleView changes={soundChanges} />}
    </section>
  );
}

// Under each photo or recording (roadmap R8 to R10): what to fix, or that it passed the checks,
// with a photo's score or a recording's length of speech.
// queue: 0 while it is being checked, above 0 while it waits its turn, -1 otherwise.
function Checks({ item, queue }: { item: Upload; queue: number }) {
  const { problems, score, speech } = item;
  const what = item.kind === "photos" ? "photo" : "recording";
  if (queue === 0) return <span className="muted check busy">Checking {what}…</span>;
  if (queue > 0) return <span className="muted check">Waiting to check</span>;
  if (problems == null) return <span className="muted check">Not checked</span>;
  if (problems.length === 0) {
    return (
      <span className="done check">
        Looks good
        {score !== null && ` · score ${score} of 100`}
        {speech !== null && ` · ${minutes(speech)} of speech`}
      </span>
    );
  }
  return (
    <ul className="problems">
      {problems.map((p) => (
        <li key={p} className="error">
          {p}
        </li>
      ))}
    </ul>
  );
}

// Under the recordings (roadmap R10): the ones that passed the checks, joined into the voice
// sample the person's voice will be made from.
function VoiceSampleView({ changes }: { changes: number }) {
  const [sample, setSample] = useState<VoiceSample | null>(null);

  useEffect(() => {
    let newest = true; // set to false once a later read is sent, so an old answer isn't shown
    getVoiceSample()
      .then((s) => {
        if (newest) setSample(s);
      })
      .catch((e: unknown) => console.error("Could not get the voice sample", e));
    return () => {
      newest = false;
    };
  }, [changes]);

  if (sample === null) return null;
  return (
    <div className="voice-sample">
      <h3>Voice sample</h3>
      {sample.recordings > 0 && (
        <>
          {/* changes in the address, so the player loads the new sample after each change */}
          <audio controls preload="none" src={`${voiceSampleAudioUrl}?v=${changes}`} />
          <p className="name">
            {sample.recordings === 1
              ? "Made from the recording that passed the checks"
              : `Made from the ${sample.recordings} recordings that passed the checks, in order`}
            : {minutes(sample.speech)} of speech.
          </p>
        </>
      )}
      {sample.problem === null ? (
        <p className="done">Enough speech to make the voice.</p>
      ) : (
        <p className={sample.recordings > 0 ? "error" : "muted"}>{sample.problem}</p>
      )}
    </div>
  );
}

const ACCENTS: { accent: Accent; label: string }[] = [
  { accent: "own", label: "Their own accent, as in the recordings" },
  { accent: "american", label: "American" },
  { accent: "british", label: "British" },
];

// Setup (roadmap R26): the person's voice keeps their own accent or speaks with another one.
// Changing it after the sample is ready makes the sample again in the new accent.
function AccentSection(props: {
  onChange: () => void;
  preparing: boolean;
  notice: string | null;
}) {
  const { onChange, preparing } = props;
  // null until the server has answered.
  const [choice, setChoice] = useState<AccentChoice | null>(null);
  const [saving, setSaving] = useState<Accent | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    getAccent()
      .then(setChoice)
      .catch((e: unknown) => {
        console.error("Could not get the accent", e);
        setFailed("Could not load the accent. Reload the page to try again.");
      });
  }, []);

  async function choose(accent: Accent) {
    setSaving(accent);
    setFailed(null);
    try {
      setChoice(await chooseAccent(accent));
      onChange();
    } catch (e) {
      console.error(`Could not choose the ${accent} accent`, e);
      setFailed(`Could not save the accent: ${(e as Error).message}`);
    }
    setSaving(null);
  }

  return (
    <section className="accent" id="accent">
      <h2>Accent</h2>
      {props.notice && <p className="notice">{props.notice}</p>}
      <p className="muted">
        The person&apos;s voice can keep their own accent or speak with another one. Changing it
        makes the sample video again.
      </p>
      <fieldset disabled={choice === null || saving !== null || preparing}>
        <legend>Speak with</legend>
        {ACCENTS.map(({ accent, label }) => (
          <label key={accent} className={saving === accent ? "busy" : undefined}>
            <input
              type="radio"
              name="accent"
              value={accent}
              checked={(saving ?? choice?.accent) === accent}
              // Another accent needs the person's own voice installed.
              disabled={accent !== "own" && choice?.available === false}
              onChange={() => void choose(accent)}
            />{" "}
            {label}
          </label>
        ))}
      </fieldset>
      {preparing && (
        <p className="muted">You can change the accent once Prepare has finished.</p>
      )}
      {choice?.available === false && (
        <p className="muted">
          Another accent needs the person&apos;s own voice installed (see &quot;Your own
          voice&quot; in the README). Until then a ready-made voice speaks, with its own accent.
        </p>
      )}
      {failed && <p className="error">{failed}</p>}
    </section>
  );
}

// How often the page asks how far the prepare job has got, while it runs.
export const PREPARE_POLL_MS = 1000;

// Setup step 2 (roadmap R12): get the voice and the face ready for the video, with a progress
// bar, then play the sample video it renders (R13). The job runs on the server, so the page can
// be closed or reloaded meanwhile.
function PrepareSection(props: {
  changes: number;
  onRunning: (running: boolean) => void;
  onBack: (to: Back) => void;
}) {
  const { changes, onRunning } = props;
  // null until the server has answered.
  const [status, setStatus] = useState<PrepareStatus | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [starting, setStarting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  // Only the newest request's answer is shown, so a slow read can't undo a click on Prepare.
  const requests = useRef(0);

  async function read() {
    const request = ++requests.current;
    try {
      const current = await getPrepare();
      if (request === requests.current) setStatus(current);
      setLoadFailed(false);
    } catch (e) {
      console.error("Could not read the prepare job", e);
      setLoadFailed(true);
    }
  }

  async function start() {
    const request = ++requests.current;
    setStarting(true);
    setRefused(null);
    try {
      const started = await startPrepare();
      if (request === requests.current) setStatus(started);
    } catch (e) {
      console.error("Could not start preparing", e);
      setRefused((e as Error).message);
    }
    setStarting(false);
  }

  // Read when the page opens, and again after the uploads change: a finished job for another
  // photo, or with too little speech left, then shows Prepare again.
  useEffect(() => {
    void read();
  }, [changes]);

  // While it runs, ask every second how far it has got.
  const running = status?.state === "running";
  useEffect(() => onRunning(running), [running]);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void read(), PREPARE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [running]);

  const label: Record<PrepareStatus["state"], string> = {
    idle: "Prepare",
    running: "Preparing…",
    done: "Prepare again",
    failed: "Try again",
  };
  return (
    <section className="prepare">
      <h2>Prepare</h2>
      <p className="muted">
        Gets the voice and the face ready for the video, then makes a short sample video of the
        person talking. The first time takes 20 minutes or more.
        You can leave this page meanwhile; if the app is stopped, it carries on where it left off
        when the app starts again.
      </p>
      {status === null && !loadFailed && <p className="muted busy">Loading…</p>}
      {loadFailed && (
        <p className="error">
          Could not read how far preparing has got. Reload the page to try again.
        </p>
      )}
      {status !== null && !running && (
        <button
          type="button"
          className={starting ? "busy" : undefined}
          onClick={start}
          disabled={starting}
        >
          {starting ? "Starting…" : label[status.state]}
        </button>
      )}
      {refused && <p className="error">{refused}</p>}
      {running && <p className="busy">Preparing… {status.percent}% done</p>}
      {status?.steps && status.state !== "idle" && (
        <>
          <progress max={100} value={status.percent} aria-label="Preparing">
            {status.percent}%
          </progress>
          <ol className="steps">
            {status.steps.map((step, i) => (
              <li key={step.key}>
                <span>{step.label}</span> <StepState step={step} status={status} index={i} />
              </li>
            ))}
          </ol>
        </>
      )}
      {status?.state === "done" && (
        <div className="sample-video">
          <p className="done">Ready. Here is the sample video:</p>
          <video
            controls
            preload="metadata"
            src={clipUrl("sample", status)}
            aria-label="Sample video"
          />
          <ReviewChoices sample={status.finished_at} onBack={props.onBack} />
        </div>
      )}
      {status?.state === "failed" && <p className="error">{status.error}</p>}
    </section>
  );
}

const REJECTS: { decision: Decision; label: string; back: Back }[] = [
  { decision: "reject-image", label: "Reject image", back: "photos" },
  { decision: "reject-voice", label: "Reject voice", back: "sounds" },
  { decision: "change-accent", label: "Change accent", back: "accent" },
];

// Under the sample video (roadmap R14): accept it and go to the chat, or go back to the photos,
// the recordings or the accent. sample tells samples apart, so a new one is read afresh.
function ReviewChoices(props: { sample: string | null; onBack: (to: Back) => void }) {
  // null until the server has answered.
  const [current, setCurrent] = useState<Review | null>(null);
  const [saving, setSaving] = useState<Decision | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    getReview()
      .then(setCurrent)
      .catch((e: unknown) => console.error("Could not get the review", e));
  }, [props.sample]);

  async function decide(decision: Decision, back?: Back) {
    setSaving(decision);
    setFailed(null);
    try {
      setCurrent(await review(decision));
      if (back) props.onBack(back);
      else window.location.hash = "#/chat";
    } catch (e) {
      console.error(`Could not save the review (${decision})`, e);
      setFailed(`Could not save your choice: ${(e as Error).message}`);
    }
    setSaving(null);
  }

  return (
    <div className="review">
      <h3>Is this right?</h3>
      {current?.accepted ? (
        <p className="done">
          You accepted this sample. <a href="#/chat">Go to the chat</a>
        </p>
      ) : (
        <p className="muted">Accept it to unlock the chat, or go back and change what is wrong.</p>
      )}
      <div className="choices">
        {!current?.accepted && (
          <button
            type="button"
            className={saving === "accept" ? "busy" : undefined}
            disabled={saving !== null}
            onClick={() => void decide("accept")}
          >
            Accept
          </button>
        )}
        {REJECTS.map(({ decision, label, back }) => (
          <button
            key={decision}
            type="button"
            className={saving === decision ? "secondary busy" : "secondary"}
            disabled={saving !== null}
            onClick={() => void decide(decision, back)}
          >
            {label}
          </button>
        ))}
      </div>
      {failed && <p className="error">{failed}</p>}
    </div>
  );
}

// Chat (roadmap R14): locked until a sample video is accepted. The chat itself comes in R15.
export function ChatPage() {
  // null until the server has answered.
  const [accepted, setAccepted] = useState<boolean | null>(null);
  useEffect(() => {
    getReview()
      .then((r) => setAccepted(r.accepted))
      .catch((e: unknown) => {
        console.error("Could not get the review", e);
        setAccepted(false);
      });
  }, []);

  if (accepted === null) return <p className="muted busy">Loading…</p>;
  if (!accepted) {
    return (
      <>
        <h1>Chat</h1>
        <p>The chat is locked until you accept a sample video at the end of setup.</p>
        <a className="button" href="#/setup">
          Go to setup
        </a>
      </>
    );
  }
  return (
    <>
      <h1>Chat</h1>
      <p className="done">The sample video is accepted, so the chat is unlocked.</p>
      <p className="muted">Typing to the person is the next part to be built.</p>
    </>
  );
}

// Next to each step: done (and how long it took), how far it has got, or waiting its turn.
function StepState(props: { step: PrepareStep; status: PrepareStatus; index: number }) {
  const { step, status } = props;
  if (step.done >= step.total) {
    const took = step.seconds !== null ? ` in ${duration(step.seconds)}` : "";
    return <span className="done">Done{took}</span>;
  }
  const current = status.steps?.findIndex((s) => s.done < s.total) === props.index;
  if (!current) return <span className="muted">Waiting</span>;
  if (status.state === "failed") return <span className="error">Stopped</span>;
  return (
    <span className="busy">
      {step.total > 1 ? `${step.done} of ${step.total}` : "Working…"}
      {step.left_s !== null && ` · about ${duration(step.left_s)} left`}
    </span>
  );
}

// 42 -> "42 s", 1034 -> "17 min"
export function duration(seconds: number): string {
  return seconds < 90 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
}

// 75.4 -> "1:15"
export function minutes(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function NotFoundPage() {
  return (
    <>
      <h1>Page not found</h1>
      <a className="button" href="#/">
        Go to the start page
      </a>
    </>
  );
}
