// The app's pages. Each one is a function that returns what the page shows.

import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";

import {
  type Accent,
  type AccentChoice,
  checkUpload,
  chooseAccent,
  choosePhoto,
  confirmConsent,
  type Decision,
  getAccent,
  getChat,
  getClips,
  IDLE_VIDEO_URL,
  type ChatHints,
  type Choice,
  type Lesson,
  type Quiz,
  type Assessment,
  getChatHints,
  getChatPhoto,
  getChatReady,
  getPhotoChoice,
  clipUrl,
  getPrepare,
  getReview,
  getReadyVoice,
  chooseReadyVoice,
  type ReadyVoice,
  useAvatarReadyVoice,
  lineUrl,
  getVoiceSample,
  type Kind,
  listUploads,
  type PhotoChoice,
  type PrepareFailure,
  type PrepareStatus,
  type PrepareStep,
  type Reply,
  removeUpload,
  repeatReply,
  type Review,
  review,
  ServerRefusal,
  readAhead,
  checkSimpler,
  sendPrompt,
  speakReply,
  startPrepare,
  cancelPrepare,
  stopReply,
  type Turn,
  type Upload,
  uploadFile,
  uploadUrl,
  type VoiceSample,
  voiceSampleAudioUrl,
} from "./api";
import { switchToOwn } from "./change-setup";
import { Checks, minutes } from "./checks";
import { useConfirm } from "./confirm-dialog";
import { RESTART_WARNING, SettingGuard, usePrepareStopGuard, useSettingGuard } from "./setting-guard";
import { ExitScreen } from "./exit";
import { FaceMovementChoice } from "./face-movement";
import { goWithoutAsking, useLeaveGuard } from "./leave-guard";
import { ASSESSMENT_KEY, LESSON_KEY, QUIZ_KEY } from "./progress";
import { OWN_CONSENT, type SetupPart } from "./router";
import { useSettings } from "./settings";
import { TalkButton } from "./talk";

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
      <p>Only use images you have the right to use. Ideally, use your own picture.</p>
      <form onSubmit={submit}>
        <label className="check">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.currentTarget.checked)}
          />{" "}
          I have the right to use the photos and recording that will be used by the app.
        </label>
        <button type="submit" disabled={!checked || saving}>
          Continue
        </button>
        {error && <p className="error">Could not save your answer. Please try again.</p>}
      </form>
    </>
  );
}

// Where a choice under the sample video sends the user back to (roadmap R14), or what Settings
// opens setup at to change (R28).
type Back = SetupPart;

const BACK_NOTICE: Record<Back, string> = {
  photos: "You rejected the image. Add new photos and remove the ones you don't want, then Prepare again.",
  sounds: "You rejected the voice. Add new recordings and remove the ones you don't want, then Prepare again.",
  accent: "Choose another accent. The sample video is then made again.",
};

// Changing one from Settings (R28): any change needs a new sample, accepted, before the chat opens.
const AFTER_CHANGE = " Accept the new sample video at the end of setup to go back to the chat.";
export const CHANGE_NOTICE: Record<Back, string> = {
  photos:
    "Add a new photo, or choose another one, and remove the ones you don't want. Then Prepare again." +
    AFTER_CHANGE,
  sounds:
    "Add new recordings and remove the ones you don't want. Then Prepare again." + AFTER_CHANGE,
  accent: "Choose another accent. The sample video is then made again." + AFTER_CHANGE,
};

// Setup: upload photos and recordings, see them and play them back (roadmap R7), choose the
// accent (R26), prepare the voice and the face (R12), then review the sample video (R14).
// `change` is the part Settings opened it at (R28).
export function SetupPage({ change }: { change?: SetupPart }) {
  // Counts changes to the photos, the chosen photo and the recordings, so Prepare asks again
  // whether what it prepared is still current.
  const [changes, setChanges] = useState(0);
  const changed = () => setChanges((n) => n + 1);
  // While Prepare runs, the accent can't change: the running job would finish in the old one.
  const [preparing, setPreparing] = useState(false);
  // Set when the user rejected the sample, or came to change one part: the section to go back
  // to shows what to do there.
  const [back, setBack] = useState<{ to: Back; notice: string } | null>(null);
  function goBack(to: Back, notice = BACK_NOTICE[to]) {
    setBack({ to, notice });
    // After the notice shows, so the page scrolls to where it ends up.
    window.setTimeout(() => document.getElementById(to)?.scrollIntoView?.({ behavior: "smooth" }));
  }
  useEffect(() => {
    if (!change) return;
    console.info(`Setup opened to change the ${change}`);
    goBack(change, CHANGE_NOTICE[change]);
  }, [change]);
  // While a ready-made avatar is to speak in the user's voice (R24d), Prepare makes the avatar's
  // video, so setting up their own photo starts by undoing that.
  const [avatarVoice, setAvatarVoice] = useState(false);
  const [undoFailed, setUndoFailed] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const leaveDialog = useLeaveGuard(pending, "The chat keeps the person and voice it has now.");
  const stopGuard = usePrepareStopGuard(changed);
  useEffect(() => {
    getReview()
      .then((r) => setAvatarVoice(r.own_voice === true))
      .catch((e: unknown) => console.error("Could not get the review", e));
  }, []);
  async function ownPhotoInstead() {
    const started = performance.now();
    setUndoFailed(null);
    try {
      await useAvatarReadyVoice();
      console.info(`Setting up your own photo instead of the avatar's voice (${Math.round(performance.now() - started)} ms)`);
      setAvatarVoice(false);
      changed();
    } catch (e) {
      console.error("Could not set up your own photo instead", e);
      setUndoFailed((e as Error).message);
    }
  }
  const notice = (to: Back) => (back?.to === to ? back.notice : null);
  if (avatarVoice) {
    return (
      <div className="host-page">
        <h1>Setup</h1>
        <p className="notice">
          The ready-made avatar is set to speak in your voice, so Prepare makes the avatar&apos;s
          video. <a href="#/avatar-voice">Go to your voice for the avatar</a>, or set up your own
          photo instead: the avatar then speaks in its ready-made voice until you accept your own
          sample video.
        </p>
        <button type="button" onClick={() => void ownPhotoInstead()}>
          Set up my own photo instead
        </button>
        {undoFailed && <p className="error">{undoFailed}</p>}
      </div>
    );
  }
  return (
    <SettingGuard.Provider value={stopGuard.guard}>
      <div className="host-page">
        <h1>Setup</h1>
        <p className="lead">
          Make the talking person in four steps: add photos, add voice recordings, choose an
          accent, then prepare a sample video and check it. Without recordings, the person speaks
          in a ready-made voice.
        </p>
        {/* Avatar Choice (Larry's test of R32a): the ready-made avatars are a click away. */}
        <p className="avatar-instead">
          Rather not use your own photo and voice?{" "}
          <a
            href="#/start-now"
            onClick={() => console.info("Choosing a ready-made avatar from Setup")}
          >
            Use a ready-made avatar instead
          </a>
          . Your photos and recordings are kept.
        </p>
        <p className="notice">
          New to this? The <a href="#/guide">recording guide</a> walks you step by step through
          taking the photos and making the voice recordings on a Windows or Mac laptop.
        </p>
        <UploadSection
          kind="photos"
          step={1}
          title="Photos"
          button="Add photos"
          hint="Add the five photos from the recording guide (JPG, PNG or HEIC). At least one is needed; the app will pick the best."
          accept="image/jpeg,image/png,image/heic,.heic"
          notice={notice("photos")}
          onChange={changed}
        />
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
        <ReadyVoiceChoice changes={changes} onChange={changed} />
        <AccentSection onChange={changed} preparing={preparing} notice={notice("accent")} />
        <PrepareSection
          changes={changes}
          onRunning={setPreparing}
          onBack={goBack}
          onPending={setPending}
          onStopped={stopGuard.onStopped}
        />
        {leaveDialog}
        {stopGuard.dialog}
      </div>
    </SettingGuard.Provider>
  );
}

// Under the recordings (item 59): without any that pass the checks (none added, or all rejected
// or removed), the person speaks in a ready-made voice, which can be chosen here.
function ReadyVoiceChoice(props: { changes: number; onChange: () => void }) {
  const [ready, setReady] = useState<ReadyVoice | null>(null);
  const guard = useSettingGuard();
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    getReadyVoice()
      .then((r) => {
        setReady(r);
        console.info(`Ready-made voice: ${r.voice}, in use: ${r.in_use}`);
      })
      .catch((e: unknown) => console.error("Could not read the ready-made voice", e));
  }, [props.changes]);
  if (ready === null || !Array.isArray(ready.voices)) return null; // not answered, or not understood

  async function choose(voice: string) {
    if (!(await guard.confirm())) {
      setReady((r) => r && { ...r }); // shows the voice it has again
      return;
    }
    const started = performance.now();
    setFailed(null);
    try {
      setReady(await chooseReadyVoice(voice));
      console.info(`Ready-made voice chosen: ${voice} (${Math.round(performance.now() - started)} ms)`);
      props.onChange(); // a sample made in the other voice needs preparing again
    } catch (e) {
      console.error("Could not choose the ready-made voice", e);
      setFailed((e as Error).message);
    }
  }

  return (
    <section className="panel ready-voice" aria-labelledby="ready-voice">
      <h3 id="ready-voice">No recordings?</h3>
      <p className="muted">
        Recordings are optional. Until one passes the checks, or if they are all removed, the person
        speaks in a ready-made voice instead of their own.
      </p>
      <label>
        Ready-made voice{" "}
        <select value={ready.voice} onChange={(e) => void choose(e.currentTarget.value)}>
          {ready.voices.map(({ voice, label }) => (
            <option key={voice} value={voice}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <p className={ready.in_use ? "notice" : "muted"}>
        {ready.in_use
          ? "In use now: no recording has passed the checks."
          : "Not in use: the voice is made from your recordings."}
      </p>
      {failed && <p className="error">{failed}</p>}
    </section>
  );
}

interface Refused {
  name: string;
  reason: string;
}

// "Step 2 of 4" over a Setup section's heading.
export function StepOf({ n }: { n: number }) {
  return <p className="step-of">Step {n} of 4</p>;
}

export function UploadSection(props: {
  kind: Kind;
  step: number;
  title: string;
  button: string; // the add button's words
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
  const { ask, dialog } = useConfirm();
  const guard = useSettingGuard();
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
    if (!(await guard.confirm(`Use ${item.name} instead?`))) return;
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
        if (e instanceof ServerRefusal && e.status === 503) break; // the rest can't run either
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
    if (files.length && !(await guard.confirm(`Add ${files.length === 1 ? files[0].name : `${files.length} files`}?`))) return;
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
    const title = `Remove ${item.name}?`;
    // While a prepare is stopped part-way (R159), one box asks and warns.
    const yes = guard.needed()
      ? await guard.confirm(title)
      : await ask({ title, keepLabel: "No, keep it", confirmLabel: "Yes, remove it" });
    if (!yes) return;
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
    <section id={kind} className="panel">
      <StepOf n={props.step} />
      <h2>{props.title}</h2>
      {props.notice && <p className="notice">{props.notice}</p>}
      <p className="muted">{props.hint}</p>
      <label className={ready ? "button" : "button busy"}>
        {sending
          ? `Uploading and checking ${sending}…`
          : loading
            ? "Loading…"
            : props.button}
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
      {dialog}
    </section>
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
export function AccentSection(props: {
  onChange: () => void;
  preparing: boolean;
  notice: string | null;
}) {
  const { onChange, preparing } = props;
  // null until the server has answered.
  const [choice, setChoice] = useState<AccentChoice | null>(null);
  const [saving, setSaving] = useState<Accent | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const guard = useSettingGuard();

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
    if (!(await guard.confirm())) {
      setSaving(null); // shows the accent it has again
      return;
    }
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
    <section className="accent panel" id="accent">
      <StepOf n={3} />
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
          Another accent needs the voice add-on, which isn&apos;t installed on this computer yet.
          Until then a ready-made voice speaks, with its own accent.
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
export function PrepareSection(props: {
  changes: number;
  onRunning: (running: boolean) => void;
  onBack: (to: Back) => void;
  avatarVoice?: boolean; // a ready-made avatar's picture in the user's voice (R24d)
  onPending?: (pending: boolean) => void; // a sample is neither accepted nor rejected
  onStopped?: (stopped: boolean) => void; // stopped part-way with Cancel, to resume (R159)
}) {
  const { changes, onRunning } = props;
  // null until the server has answered.
  const [status, setStatus] = useState<PrepareStatus | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [starting, setStarting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const { choose, dialog } = useConfirm();
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

  // Cancel (R159): asks first, in the app's own box, whether to stop now, stop once the part
  // it is on is finished (usually within 10 seconds), or keep preparing.
  async function cancel() {
    const left = status?.left_s != null ? ` About ${countdown(status.left_s)} is left.` : "";
    const answer = await choose({
      title: "Stop preparing the video?",
      children: (
        <p>
          Preparing is {status?.percent ?? 0}% done.{left} You can stop now, or once the part it
          is working on is finished (usually within 10 seconds). Either way, Resume Preparation carries
          on from where it stopped.
        </p>
      ),
      keepLabel: "Keep preparing",
      otherLabel: "Stop after this part",
      confirmLabel: "Stop now",
    });
    if (answer === "cancel") return;
    const request = ++requests.current;
    setRefused(null);
    try {
      const stopping = await cancelPrepare(answer === "confirm");
      if (request === requests.current) setStatus(stopping);
    } catch (e) {
      console.error("Could not stop preparing", e);
      setRefused((e as Error).message);
    }
  }

  // Read when the page opens, and again after the uploads change: a finished job for another
  // photo, or with too little speech left, then shows Prepare again.
  useEffect(() => {
    void read();
  }, [changes]);

  // While it runs, ask every second how far it has got. A job the app is no longer working on
  // (R134b) isn't followed: Try again carries it on.
  const stopped = status?.state === "running" && status.stopped === true;
  const running = status?.state === "running" && !stopped;
  const cancelling = running && status.cancelling === true;
  const slow =
    running && !cancelling && status.steps?.find((s) => s.done < s.total)?.slow === true;
  const cancelled = status?.state === "cancelled";
  useEffect(() => onRunning(running), [running]);
  // Before the browser paints, so a setting changed at once after is guarded.
  useLayoutEffect(() => props.onStopped?.(cancelled), [cancelled]);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void read(), PREPARE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [running]);

  // Prepared already: nothing to do until a setting changes, which shows it as idle again
  // (Larry, 2026-10-26).
  const label: Record<PrepareStatus["state"], string> = {
    idle: "Prepare Video",
    running: "Preparing…",
    done: "Prepare Video",
    failed: "Try again",
    cancelled: "Resume Preparation",
  };
  return (
    <section className="prepare panel">
      <StepOf n={4} />
      <h2>Prepare the video</h2>
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
      <FaceMovementChoice onChanged={() => void read()} disabled={running} />
      {status !== null && !running && (
        <button
          type="button"
          className={starting ? "busy" : undefined}
          onClick={start}
          disabled={starting || status.state === "done"}
        >
          {starting ? "Starting…" : stopped ? "Try again" : label[status.state]}
        </button>
      )}
      {refused && <p className="error">{refused}</p>}
      {stopped && (
        <p className="error">
          Preparing stopped: the app is no longer working on it. Click Try again to carry on where
          it left off.
        </p>
      )}
      {running && !cancelling && (
        <p className="busy">
          Preparing… {status.percent}% done
          {status.left_s != null && ` · about ${countdown(status.left_s)} left`}
        </p>
      )}
      {running && (
        <button
          type="button"
          className={cancelling ? "secondary busy" : "secondary"}
          onClick={() => void cancel()}
          disabled={cancelling}
        >
          {cancelling ? "Stopping…" : "Cancel"}
        </button>
      )}
      {cancelling && !status.stopping_late && (
        <p className="muted">Stopping, usually within 10 seconds…</p>
      )}
      {cancelling && status.stopping_late && (
        <p className="muted">
          Still stopping: the part it is on, such as loading a library, can't be cut short
          safely. It stops as soon as that part is done.
        </p>
      )}
      {cancelled && (
        <p className="muted">
          Preparing stopped at {status.percent}%. Click Resume Preparation to carry on from where
          it stopped. {RESTART_WARNING}
        </p>
      )}
      {slow && <p className="muted">This is taking longer than usual. It&apos;s still working.</p>}
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
          <p className="done">Done. Watch the sample video, then say whether it is right.</p>
          <video
            controls
            preload="metadata"
            src={clipUrl("sample", status)}
            aria-label="Sample video"
          />
          <ReviewChoices
            sample={status.finished_at}
            onBack={props.onBack}
            avatarVoice={props.avatarVoice}
            onPending={props.onPending}
          />
        </div>
      )}
      {status?.state === "failed" &&
        (status.failure ? (
          <FailureReport failure={status.failure} at={status.finished_at} />
        ) : (
          <p className="error">{status.error}</p>
        ))}
      {dialog}
    </section>
  );
}

// What a failed prepare tells the customer (roadmap R134): the step, the reason, whether Try
// again may help and the reference for support, with the details to copy for support. Never
// "look in the log": a customer can't.
export function FailureReport(props: { failure: PrepareFailure; at: string | null }) {
  const { failure } = props;
  // What the last copy did: copied, or the text to copy by hand when the browser refused.
  const [copied, setCopied] = useState<{ byHand: string | null }>();
  const text = [
    `Reference: ${failure.reference}`,
    `Step: ${failure.step ?? "Before the first step"}`,
    `Reason: ${failure.message}`,
    `Time: ${props.at ?? "unknown"}`,
    `App version: ${failure.version}`,
    `Browser: ${navigator.userAgent}`,
    `Error: ${failure.details}`,
  ].join("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      console.info(`Prepare failure copied for support (${failure.reference})`);
      setCopied({ byHand: null });
    } catch (e) {
      console.error("Could not copy the failure's details", e);
      setCopied({ byHand: text });
    }
  }

  return (
    <div className="failure" role="alert">
      <p className="error">
        {failure.step ? `“${failure.step}” failed. ` : "Preparing failed. "}
        {failure.message}
      </p>
      <p className="muted">
        {failure.retry
          ? "Try again may help. If it keeps failing, please give support the reference "
          : "Please give support the reference "}
        <strong>{failure.reference}</strong>.
      </p>
      <button type="button" className="secondary" onClick={copy}>
        Copy details for support
      </button>
      {copied && copied.byHand === null && <span className="done"> Copied.</span>}
      {copied?.byHand && (
        <>
          <p className="error">The browser didn't allow copying. Select the text below and copy it.</p>
          <textarea readOnly value={copied.byHand} rows={7} aria-label="Details for support" />
        </>
      )}
      <details>
        <summary>Details</summary>
        <pre>{failure.details}</pre>
      </details>
    </div>
  );
}

const REJECTS: { decision: Decision; label: string; back: Back }[] = [
  { decision: "reject-image", label: "Reject image", back: "photos" },
  { decision: "reject-voice", label: "Reject voice", back: "sounds" },
  { decision: "change-accent", label: "Change accent", back: "accent" },
];

// Under the sample video (roadmap R14): accept it and go to the chat, or go back to the photos,
// the recordings or the accent. sample tells samples apart, so a new one is read afresh.
function ReviewChoices(props: {
  sample: string | null;
  onBack: (to: Back) => void;
  avatarVoice?: boolean;
  onPending?: (pending: boolean) => void;
}) {
  // null until the server has answered.
  const [current, setCurrent] = useState<Review | null>(null);
  // The sample rejected here, so leaving the page afterwards doesn't ask (Larry's test of #131).
  const [rejected, setRejected] = useState<string | null>(null);
  const [saving, setSaving] = useState<Decision | "default-voice" | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    getReview()
      .then(setCurrent)
      .catch((e: unknown) => console.error("Could not get the review", e));
  }, [props.sample]);

  async function defaultVoice() {
    const started = performance.now();
    setSaving("default-voice");
    setFailed(null);
    try {
      setCurrent(await useAvatarReadyVoice());
      console.info(`Avatar's default voice used again from the review (${Math.round(performance.now() - started)} ms)`);
      goWithoutAsking("#/chat");
    } catch (e) {
      console.error("Could not use the avatar's default voice again", e);
      setFailed(`Could not return to the default voice: ${(e as Error).message}`);
    }
    setSaving(null);
  }

  async function decide(decision: Decision, back?: Back) {
    setSaving(decision);
    setFailed(null);
    try {
      setCurrent(await review(decision));
      if (back) setRejected(props.sample);
      if (back) props.onBack(back);
      else goWithoutAsking("#/chat");
    } catch (e) {
      console.error(`Could not save the review (${decision})`, e);
      setFailed(`Could not save your choice: ${(e as Error).message}`);
    }
    setSaving(null);
  }

  // With a ready-made avatar in use, the chat is open whatever this sample's review; what counts
  // is whether this sample, of the user's own, is accepted (Larry's test of PR #128), or, with
  // the avatar to speak in the user's voice, the avatar's sample in that voice (R24d).
  const avatar = current?.default_person === true;
  const avatarVoice = props.avatarVoice === true || (avatar && current?.own_voice === true);
  const accepted = avatarVoice
    ? current?.voice_accepted === true
    : avatar
      ? current?.own_sample_accepted === true
      : current?.accepted;
  // Neither accepted nor rejected yet: leaving setup asks first (Larry's test of PR #131).
  const pending = current !== null && !accepted && rejected !== props.sample;
  const { onPending } = props;
  useEffect(() => onPending?.(pending), [pending]);
  useEffect(() => () => onPending?.(false), []);
  // The avatar's picture is not the user's to reject (R24d).
  const rejects = avatarVoice ? REJECTS.filter((r) => r.back !== "photos") : REJECTS;
  async function useIt() {
    setSaving("accept");
    setFailed(null);
    try {
      await switchToOwn(true, "Setup");
    } catch (e) {
      console.error("Could not switch to your own photo and voice", e);
      setFailed(`Could not switch: ${(e as Error).message}`);
    }
    setSaving(null);
  }
  return (
    <div className="review">
      <h3>Is this right?</h3>
      {accepted && avatar && !avatarVoice ? (
        <p className="done">
          You accepted this sample, but the chat uses a ready-made avatar.{" "}
          <button type="button" className="link" disabled={saving !== null} onClick={() => void useIt()}>
            Use your own photo and voice in the chat
          </button>
        </p>
      ) : accepted ? (
        <p className="done">
          You accepted this sample. <a href="#/chat">Go to the chat</a>
        </p>
      ) : (
        <p className="muted">
          {avatarVoice
            ? "Accept it to have the avatar speak in your voice, go back and change what is wrong, or return to the avatar's default voice."
            : "Accept it to unlock the chat, or go back and change what is wrong."}
        </p>
      )}
      <div className="choices">
        {!accepted && (
          <button
            type="button"
            className={saving === "accept" ? "busy" : undefined}
            disabled={saving !== null}
            onClick={() => void decide("accept")}
          >
            Accept
          </button>
        )}
        {rejects.map(({ decision, label, back }) => (
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
        {avatarVoice && (
          // Back to the avatar's default voice, with nothing to accept (Larry's test of #131).
          <button
            type="button"
            className={saving === "default-voice" ? "secondary busy" : "secondary"}
            disabled={saving !== null}
            onClick={() => void defaultVoice()}
          >
            Return to default voice for avatar
          </button>
        )}
      </div>
      {failed && <p className="error">{failed}</p>}
    </div>
  );
}

// Chat (roadmap R14): locked until a sample video is accepted.
export function ChatPage() {
  const participant = useSettings().view === "participant"; // setup is the host's (R41b)
  // null until the server has answered.
  const [accepted, setAccepted] = useState<boolean | null>(null);
  const [readyMade, setReadyMade] = useState(false); // a ready-made avatar, not their own
  useEffect(() => {
    getReview()
      .then((r) => {
        setAccepted(r.accepted);
        setReadyMade(r.default_person === true);
      })
      .catch((e: unknown) => {
        console.error("Could not get the review", e);
        setAccepted(false);
      });
  }, []);

  // Exit (roadmap R29): the exit screen after the person says "Goodbye.", and back to the chat
  // with Start again, where they say "Welcome back." The conversation is the server's, so it
  // is still there.
  const [exited, setExited] = useState(false);
  const [returned, setReturned] = useState(false);
  const asked = useRef<Promise<unknown> | null>(null); // still being answered at Exit

  if (accepted === null) return <p className="muted busy">Loading…</p>;
  if (exited) {
    return (
      <ExitScreen
        onStartAgain={() => {
          setExited(false);
          setReturned(true);
        }}
      />
    );
  }
  if (!accepted) {
    if (participant) {
      return (
        <>
          <h1>Chat</h1>
          <p>The chat isn't ready yet. Ask your host to finish setting it up.</p>
        </>
      );
    }
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
    <div className="chat-page">
      <h1 className="sr-only">Chat</h1>
      {!participant && <AvatarLinks readyMade={readyMade} />}
      <Chat
        welcome={returned}
        after={asked.current}
        onExit={(pending) => {
          asked.current = pending;
          setExited(true);
        }}
      />
    </div>
  );
}

// Avatar Choice from the chat (Larry's test of R32a): another ready-made avatar, or the host's own
// photo and voice, without going through Settings. The participant view has neither (R41b).
function AvatarLinks({ readyMade }: { readyMade: boolean }) {
  const links: [string, string, string][] = readyMade
    ? [
        ["#/start-now", "Choose another avatar", "another ready-made avatar"],
        [OWN_CONSENT, "Use your own photo and voice", "their own photo and voice"],
      ]
    : [
        ["#/start-now", "Use a ready-made avatar", "a ready-made avatar"],
        ["#/setup/photos", "Change your photo", "their own photo"],
      ];
  return (
    <p className="avatar-links">
      <span className="muted">Avatar Choice:</span>
      {links.map(([href, label, what]) => (
        <a
          key={href}
          href={href}
          onClick={() => console.info(`Choosing ${what} from the chat`)}
        >
          {label}
        </a>
      ))}
    </p>
  );
}

// The reply shown when Hold to talk wasn't sure of every word it heard (R179), with the words
// left in the prompt box to edit and send. It is shown only, not added to the conversation.
export const CHECK_HEARD =
  "I am not clear on what you said. Can you edit your question and resend?";
// What the chat says when there is no reply, whatever the reason; the reason goes to the
// browser console and the server log, not to the participant (R41d).
export const CANT_ANSWER = "Sorry, I couldn't answer that just now. Please try again in a moment.";

// How often the chat asks for a reply's new clips while they are being made.
export const CLIP_POLL_MS = 300;

// The fixed lines Prepare makes with the sample (roadmap R29): said on Exit and on Start again.
export type Line = "goodbye" | "welcome-back";
const LINE_TEXT: Record<Line, string> = { goodbye: "Goodbye", "welcome-back": "Welcome back" };
// The longest a fixed line is waited for, should its video never play or end; it is about a
// second long.
export const LINE_TIMEOUT_MS = 10_000;

function newReplyId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// When a sentence's clip went through, in milliseconds on this page's clock (performance.now()):
// its text arrived from the LLM, its clip was ready, it started playing and it ended (roadmap
// R22a). The server's times are moved onto this clock from the `now` it answers with.
export interface ClipTime {
  text: number;
  ready: number;
  started: number | null;
  ended: number | null;
}

// The sound of the person speaking (roadmap R19): volume from 0 to 1, and muted or not. Kept
// in this browser so it lasts from one visit to the next.
export interface Sound {
  volume: number;
  muted: boolean;
}

const SOUND_KEY = "imageskin.sound";

// The lesson this browser has (roadmap R41h), kept so a participant who stops picks up where they
// left off.

export function loadLesson(): Lesson | null {
  try {
    const saved = JSON.parse(localStorage.getItem(LESSON_KEY) ?? "null") as Partial<Lesson> | null;
    if (typeof saved?.topic !== "string" || !Number.isInteger(saved.part) || saved.part! < 0)
      return null;
    const parts = Number.isInteger(saved.parts) ? saved.parts : undefined;
    return { topic: saved.topic, part: saved.part!, active: saved.active !== false, parts };
  } catch {
    return null; // storage blocked, or something else saved there
  }
}

// The quiz this browser has (roadmap R41i), kept so a reload doesn't lose it.

export function loadQuiz(): Quiz | null {
  try {
    const saved = JSON.parse(localStorage.getItem(QUIZ_KEY) ?? "null") as Partial<Quiz> | null;
    if (
      typeof saved?.topic !== "string" ||
      typeof saved.question !== "string" ||
      !Number.isInteger(saved.number) ||
      !Number.isInteger(saved.part)
    )
      return null;
    const strings = (v: unknown) =>
      Array.isArray(v) ? v.filter((s): s is string => typeof s === "string") : [];
    const count = (v: unknown) => (Number.isInteger(v) ? (v as number) : 0);
    return {
      topic: saved.topic,
      number: saved.number!,
      question: saved.question,
      part: saved.part!,
      asked: strings(saved.asked),
      right: count(saved.right),
      partly: count(saved.partly),
      review: strings(saved.review),
      source: typeof saved.source === "string" ? saved.source : "",
      questions: Number.isInteger(saved.questions) ? saved.questions : undefined,
    };
  } catch {
    return null; // storage blocked, or something else saved there
  }
}

// The assessment this browser has (roadmap R41j), kept so a reload doesn't lose it.

export function loadAssessment(): Assessment | null {
  try {
    const saved = JSON.parse(localStorage.getItem(ASSESSMENT_KEY) ?? "null") as Assessment | null;
    const whole =
      typeof saved?.topic === "string" &&
      typeof saved.question === "string" &&
      typeof saved.source === "string" &&
      [saved.total, saved.number, saved.level, saved.part].every(Number.isInteger) &&
      Array.isArray(saved.answers);
    return whole ? saved : null; // the server checks the rest
  } catch {
    return null; // storage blocked, or something else saved there
  }
}

function saveAssessment(assessment: Assessment | null) {
  try {
    if (assessment) localStorage.setItem(ASSESSMENT_KEY, JSON.stringify(assessment));
    else localStorage.removeItem(ASSESSMENT_KEY);
  } catch (e) {
    console.error("Could not keep the assessment", e);
  }
}

function saveQuiz(quiz: Quiz | null) {
  try {
    if (quiz) localStorage.setItem(QUIZ_KEY, JSON.stringify(quiz));
    else localStorage.removeItem(QUIZ_KEY);
  } catch (e) {
    console.error("Could not keep the quiz", e);
  }
}

function saveLesson(lesson: Lesson | null) {
  try {
    if (lesson) localStorage.setItem(LESSON_KEY, JSON.stringify(lesson));
    else localStorage.removeItem(LESSON_KEY);
  } catch (e) {
    console.error("Could not keep the lesson", e);
  }
}

export function loadSound(): Sound {
  try {
    const saved = JSON.parse(localStorage.getItem(SOUND_KEY) ?? "null") as Partial<Sound> | null;
    const volume = Number(saved?.volume);
    return {
      volume: Number.isFinite(volume) ? Math.min(Math.max(volume, 0), 1) : 1,
      muted: saved?.muted === true,
    };
  } catch {
    return { volume: 1, muted: false }; // storage blocked, or something else saved there
  }
}

function saveSound(sound: Sound) {
  try {
    localStorage.setItem(SOUND_KEY, JSON.stringify(sound));
  } catch {
    // Storage blocked: the choice lasts until the page is left.
  }
}

// How long typing pauses before the question so far is read ahead, and the fewest words read
// (R148).
export const READ_AHEAD_PAUSE_MS = 600;
const READ_AHEAD_WORDS = 3;

// How often the chat asks again whether the person's voice and face are ready (R181): each
// second, so the seconds left count down one by one (R183).
export const READY_CHECK_MS = 1000;
// Said in place of Thinking while they are got ready, after the app starts or after switching
// back to your own photo and voice from a ready-made avatar, with the seconds left when the
// server can tell (Larry, 2026-10-29, R183).
export function preparingChat(leftS: number | null): string {
  if (leftS === null) return "Preparing chat…";
  return `Preparing chat… ${leftS} ${leftS === 1 ? "second" : "seconds"} remaining`;
}

// Text chat with the LLM (roadmap R15). The person speaks each reply in their voice, on their
// photo (roadmap R17), starting on its first sentence while the rest is still being made
// (roadmap R22); if that fails, the reply stays as text with a short note.
function Chat(props: {
  welcome?: boolean;
  after?: Promise<unknown> | null; // a prompt asked before Exit, still being answered (R29)
  onExit?: (asked: Promise<unknown> | null) => void;
}) {
  const metrics = useSettings().show_metrics; // the timing readout (R41a)
  // The Teach me, Quiz me and Assessment buttons, lessons, quizzes and assessments (R41h, R41i,
  // R41j), and Copy chat.
  const { teach_me: teachMe, quiz_me: quizMe, assessment: assessOn, debug } = useSettings();
  const [turns, setTurns] = useState<Turn[] | null>(null);
  const [prompt, setPrompt] = useState("");
  const [sending, setSending] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [clips, setClips] = useState<string[]>([]);
  const [times, setTimes] = useState<ClipTime[]>([]); // one per clip of the latest reply
  const [earlier, setEarlier] = useState<number[]>([]); // the waits of the replies before it
  const [whole, setWhole] = useState(false); // the latest reply is one video, not clips
  // Why the latest reply could not be spoken, by its place in the turns shown.
  const [unspoken, setUnspoken] = useState<{ turn: number } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const promptBox = useRef<HTMLTextAreaElement>(null);
  const [notClear, setNotClear] = useState(false); // CHECK_HEARD shown as the reply (R179)
  // What Hold to talk heard but wasn't sure of, or was stopped with Edit, left in the box (R179):
  // sent unchanged, it is still a spoken question, so misheard names are put back (R24).
  const unsure = useRef<string | null>(null);
  const gone = useRef(false); // the page was left: stop following clips
  const replying = useRef<string | null>(null); // the latest reply's id
  const stopped = useRef<string | null>(null); // the id of a reply stopped with Stop (R19)
  const wakeOnStop = useRef<() => void>(() => {}); // ends the latest reply's waits on Stop
  const [halted, setHalted] = useState(false); // the latest reply was stopped
  const [sound, setSound] = useState<Sound>(loadSound);
  const [idle, setIdle] = useState<Idle>("loading"); // the idle video (roadmap R23)
  // The photo, shown until the idle video plays, and its shape, which the person's frame takes
  // from its first drawing (R41d); undefined until the server has answered.
  const [photo, setPhoto] = useState<{
    url: string | null;
    ratio: number | null;
    idle?: string;
  }>();
  // Between sending a prompt and the person starting to speak, unless the reply has nothing
  // to say aloud, couldn't be spoken, or was stopped (R41d).
  const [waiting, setWaiting] = useState(false);
  // The topics line and example questions under the prompt box (R41g), read again after each
  // reply so they follow the PDFs.
  const [hints, setHints] = useState<ChatHints>({ line: null, examples: [] });
  const [lesson, setLesson] = useState<Lesson | null>(loadLesson); // Teach me (R41h)
  const [quiz, setQuiz] = useState<Quiz | null>(loadQuiz); // Quiz me (R41i)
  const [choices, setChoices] = useState<Choice[]>([]); // offered with the latest reply
  const [assessment, setAssessment] = useState<Assessment | null>(loadAssessment); // R41j
  // While a quiz or an assessment is going, whatever is sent is taken as the answer.
  const assessing = assessOn && assessment !== null;
  const quizGoing = (quizMe && quiz !== null) || assessing;
  // Choices belong to Teach me, Quiz me or the assessment, so turning any of them on or off drops
  // them: a choice can't be sent once its setting is off (review on PR #88).
  useEffect(() => {
    setChoices([]);
  }, [teachMe, quizMe, assessOn]);
  // "Goodbye." or "Welcome back." being said (R29): nothing can be sent meanwhile.
  const [saying, setSaying] = useState<Line | null>(props.welcome ? "welcome-back" : null);
  const line = useRef<{ name: Line; at: number; timer?: ReturnType<typeof setTimeout> } | null>(
    null,
  );
  // Whether replies are ready, or the person's voice and face are still being got ready (R181):
  // nothing can be sent until the server has said they are, so a prompt never shows Thinking
  // all that time (Codex's review of PR #216: Send was on while the answer was still coming).
  // Null until the server has said; a failed check counts as ready.
  const [ready, setReady] = useState<boolean | null>(null);
  const [leftS, setLeftS] = useState<number | null>(null); // seconds left, when known (R183)
  const gettingReady = ready === false;
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let waitedFrom: number | null = null;
    const check = () => {
      getChatReady().then(
        ({ ready: now, leftS: left, warming }) => {
          if (gone.current) return;
          setReady(now);
          setLeftS(left);
          // A warm-up in its first seconds leaves the chat open, but is asked about again in
          // case it runs longer (R183).
          if (!now || warming) {
            if (waitedFrom === null) {
              waitedFrom = performance.now();
              console.info(
                now
                  ? "Chat open while the voice and face are got ready"
                  : "Chat waits while the voice and face are got ready",
              );
            }
            timer = setTimeout(check, READY_CHECK_MS);
          } else if (waitedFrom !== null) {
            console.info(`Voice and face ready for the chat (${Math.round(performance.now() - waitedFrom)} ms)`);
          }
        },
        (e: unknown) => {
          console.error("Could not ask whether the chat is ready", e);
          if (!gone.current) setReady(true); // never kept waiting by a failed check
        },
      );
    };
    check();
    return () => clearTimeout(timer);
  }, []);
  const busy = sending || speaking || saying !== null || ready !== true;
  // Say it simpler is shown with every reply, but can be pressed only once the server has found
  // that it would say it more simply (R177): after a few presses the LLM may give the same reply
  // back. Hidden, it looked flaky (Larry, PR #211). Checked once each reply is said, not while a
  // quiz is going.
  const last = turns?.[turns.length - 1];
  const latestReply = last?.role === "assistant" ? last.content : null;
  // The latest reply checked, and whether it can be said more simply.
  const [simplerOf, setSimplerOf] = useState<{ reply: string; simpler: boolean } | null>(null);
  const simplerChecked = useRef<string | null>(null);
  useEffect(() => {
    if (busy || quizGoing || latestReply === null || simplerChecked.current === latestReply) return;
    simplerChecked.current = latestReply;
    checkSimpler().then(
      (simpler) => {
        console.info(`Say it simpler ${simpler ? "enabled" : "disabled"}`);
        if (simplerChecked.current === latestReply) setSimplerOf({ reply: latestReply, simpler });
      },
      (e: unknown) => {
        console.error("Could not check for a simpler reply", e);
        if (simplerChecked.current === latestReply) setSimplerOf({ reply: latestReply, simpler: false });
      },
    );
  }, [busy, quizGoing, latestReply]);
  // The question typed so far is read ahead by the LLM once typing pauses (R148), so most of it
  // is in the LLM's cache on Send. Not while a reply is made, nor for an answer to a quiz.
  const readAheadOf = useRef("");
  useEffect(() => {
    const text = prompt.trim();
    if (busy) readAheadOf.current = ""; // the conversation changes: read it again after
    if (busy || quizGoing || text === readAheadOf.current) return;
    if (text.split(/\s+/).length < READ_AHEAD_WORDS) return;
    const timer = setTimeout(() => {
      readAheadOf.current = text;
      readAhead(text).then(
        (read) => console.debug(`Question read ahead: ${read}`),
        (e: unknown) => console.debug("Could not read the question ahead", e),
      );
    }, READ_AHEAD_PAUSE_MS);
    return () => clearTimeout(timer);
  }, [prompt, busy, quizGoing]);
  // The prompt being answered, if any: Exit hands it on, so Start again waits for it (R29).
  const inFlight = useRef<Promise<unknown> | null>(null);
  const clipTotal = useRef(0); // how many clips the latest reply has so far
  const allMade = useRef(false); // and that no more will come
  const clipsEnded = useRef(0); // how many of them have ended or been passed over

  useEffect(() => {
    if (props.welcome) void say("welcome-back");
    return () => {
      gone.current = true;
      clearTimeout(line.current?.timer);
    };
  }, []);
  useEffect(() => {
    getChatPhoto()
      .then(({ url, width, height, idle }) => {
        const ratio = width && height ? width / height : null;
        setPhoto({ url: url ?? null, ratio, idle: idle ?? undefined });
        if (url && width && height) console.info(`Chat photo ${width}x${height}`);
      })
      .catch((e: unknown) => {
        console.error("Could not find the photo for the chat", e);
        setPhoto({ url: null, ratio: null });
      });
  }, []);
  useEffect(() => {
    if (sending) return;
    getChatHints()
      .then(setHints)
      .catch((e: unknown) => {
        console.error("Could not load the topic hints", e);
        setHints({ line: null, examples: [] }); // hints read before may no longer hold
      });
  }, [sending]);
  useEffect(() => {
    // Back from Exit while a prompt was still being answered: the server adds it to the
    // conversation once it is answered, so the conversation is read after that (review on
    // PR #106).
    if (props.after) console.info("Waiting for the prompt asked before Exit");
    const answered = props.after ? props.after.catch(() => {}) : Promise.resolve();
    answered
      .then(() => getChat())
      .then(setTurns)
      .catch((e: unknown) => {
        console.error("Could not load the conversation", e);
        setTurns([]);
        setFailed("The conversation couldn't be loaded. Reload the page to try again.");
      });
  }, []);

  // Follow the reply's clips until the last one is made, or until the server has none to tell
  // of once the reply is in: it wasn't streamed, or a newer prompt (from another tab, say) took
  // its clips. Returns how many clips there were; throws when a clip failed.
  async function followClips(replyId: string, replied: () => boolean): Promise<number> {
    let known = 0;
    while (!gone.current && stopped.current !== replyId) {
      const answered = replied(); // read first: the clips may be dropped once it has replied
      const got = await getClips(replyId, known);
      if (stopped.current === replyId) return known; // stopped while it asked
      if (got === null) {
        if (answered) return known;
        await sleep(CLIP_POLL_MS);
        continue;
      }
      const offset = performance.now() - got.now * 1000; // the server's clock to this page's
      const made = got.clips.slice(known).map((c) => ({
        text: c.sentence_at * 1000 + offset,
        ready: c.ready_at * 1000 + offset,
        started: null,
        ended: null,
      }));
      if (made.length) setTimes((t) => [...t, ...made]);
      setClips(got.clips.map((c) => c.url));
      clipTotal.current = got.clips.length;
      if (got.error !== null) throw new Error(got.error);
      if (got.done) return got.clips.length;
      if (got.clips.length === known) await sleep(CLIP_POLL_MS); // its wait ran out
      known = got.clips.length;
    }
    return known;
  }

  // Says "Goodbye." or "Welcome back." (R29), then goes to the exit screen or readies the
  // prompt. When its video can't be found or played, it goes on without it.
  async function say(name: Line) {
    line.current = { name, at: performance.now() };
    setSaying(name);
    setClips([]);
    setTimes([]);
    setWhole(false);
    console.info(`Saying ${LINE_TEXT[name]}`);
    let url: string | null = null;
    try {
      url = await lineUrl(name);
    } catch (e) {
      console.error(`Could not find the ${LINE_TEXT[name]} video`, e);
    }
    if (gone.current || line.current?.name !== name) return;
    if (url === null) {
      console.warn(`No ${LINE_TEXT[name]} video, so it isn't said`);
      said();
      return;
    }
    setHalted(false);
    setClips([url]);
    line.current.timer = setTimeout(() => {
      console.warn(`${LINE_TEXT[name]} didn't finish playing in time, so the chat went on`);
      said();
    }, LINE_TIMEOUT_MS);
  }

  function said() {
    const done = line.current;
    if (done === null) return;
    clearTimeout(done.timer);
    line.current = null;
    console.info(`Said ${LINE_TEXT[done.name]} (${Math.round(performance.now() - done.at)} ms)`);
    if (done.name === "goodbye") {
      props.onExit?.(inFlight.current);
      return;
    }
    setSaying(null);
    setClips([]);
  }

  // Exit (R29): a reply being spoken stops, then the person says "Goodbye."
  function exit() {
    console.info("Exit");
    if (stoppable) stop();
    void say("goodbye");
  }

  // The player says when each clip starts and ends, for the timing readout.
  function started(clip: number, at: number) {
    setWaiting(false);
    setTimes((t) => t.map((c, i) => (i === clip && c.started === null ? { ...c, started: at } : c)));
  }
  function ended(clip: number, at: number) {
    if (line.current) {
      said();
      return;
    }
    clipsEnded.current = Math.max(clipsEnded.current, clip + 1);
    // Every clip passed over as broken, without one starting: nothing will be said aloud.
    if (allMade.current && clipsEnded.current >= clipTotal.current) setWaiting(false);
    setTimes((t) => t.map((c, i) => (i === clip && c.ended === null ? { ...c, ended: at } : c)));
  }

  // Sends what is typed, or an example question that was clicked (R41g), or what was said with
  // Hold to talk (R24).
  async function send(asked?: string, spoken = false) {
    const text = (asked ?? prompt).trim();
    if (!text || busy) return;
    spoken ||= asked === undefined && text === unsure.current;
    unsure.current = null;
    const shownAt = (turns ?? []).length + 1; // where the reply shows, after the prompt
    const replyId = newReplyId();
    let replied = false;
    replying.current = replyId;
    // Settles on Stop, so the reply no longer waits for clips or a video it won't play.
    const stopping = new Promise<"stopped">((resolve) => {
      wakeOnStop.current = () => resolve("stopped");
    });
    setHalted(false);
    setSending(true);
    setSpeaking(true);
    setWaiting(true);
    clipTotal.current = 0;
    allMade.current = false;
    clipsEnded.current = 0;
    setFailed(null);
    setNotClear(false);
    setUnspoken(null);
    setClips([]); // the server replaces the last reply's clips or video with this one's
    setEarlier((e) => [...e, ...clipWaits(times)]);
    setTimes([]);
    setWhole(false);
    setTurns((t) => [...(t ?? []), { role: "user", content: text }]);
    setPrompt("");
    setChoices([]);
    // Why the clips failed, if they did, kept until the reply is in: a clip can fail long
    // before, and a rejection with nothing waiting on it would be reported as unhandled.
    let clipCount = 0;
    const following: Promise<Error | null> = followClips(replyId, () => replied).then(
      (n) => {
        clipCount = n;
        allMade.current = true;
        return null;
      },
      (e: unknown) => (e instanceof Error ? e : new Error(String(e))),
    );
    let reply: Reply;
    let repliedAt = 0;
    try {
      const asking = sendPrompt(
        text,
        replyId,
        teachMe ? lesson : null,
        quizMe ? quiz : null,
        assessOn ? assessment : null,
        spoken,
      );
      inFlight.current = asking;
      reply = await asking;
      repliedAt = performance.now();
      // With Teach me off, the lesson isn't sent, so the one kept stays for when it is back on.
      if (teachMe && reply.lesson !== undefined) {
        const next = reply.lesson;
        setLesson(next);
        saveLesson(next);
        if (next) console.info(`Lesson: ${next.topic}, part ${next.part + 1}`);
      }
      // The same for the quiz (R41i).
      if (quizMe && reply.quiz !== undefined) {
        const next = reply.quiz;
        setQuiz(next);
        saveQuiz(next);
        if (next) console.info(`Quiz: ${next.topic}, question ${next.number}`);
      }
      // The same for the assessment (R41j).
      if (assessOn && reply.assessment !== undefined) {
        const next = reply.assessment;
        setAssessment(next);
        saveAssessment(next);
        if (next) console.info(`Assessment: question ${next.number} of ${next.total}`);
      }
      setChoices(reply.choices ?? []);
      const { role, content } = reply;
      // A spoken prompt shows as it was answered, with any misheard words put back (R24).
      const meant = reply.prompt;
      if (meant && meant !== text) console.info(`Push-to-talk: "${text}" taken as "${meant}"`);
      setTurns((t) => [
        ...(t ?? []).map((turn, i, all) =>
          meant && i === all.length - 1 ? { ...turn, content: meant } : turn,
        ),
        { role, content },
      ]);
    } catch (e) {
      // Stopped while it was answered: the server cut the LLM off and dropped the prompt
      // (Larry's test of PR #129), so it goes back in the box, with nothing to apologize for.
      const halt = e instanceof ServerRefusal && e.status === 409 && stopped.current === replyId;
      if (halt) console.info("Prompt stopped while it was answered");
      else console.error("Could not get a reply", e);
      // The server forgets a prompt that got no reply, so it goes back in the box.
      setTurns((t) => (t ?? []).slice(0, -1));
      setPrompt((typed) => (halt && typed ? typed : text));
      // A prompt the server can't use (empty, too long) says why in plain words; any other
      // trouble gets the same short apology (R41d).
      if (!halt) setFailed(e instanceof ServerRefusal && e.status === 400 ? e.message : CANT_ANSWER);
      replied = true;
      await Promise.race([following, stopping]);
      setClips([]); // with any clip made before the LLM failed, and its timing row
      setTimes([]);
      setWhole(false);
      setSpeaking(false);
      setWaiting(false);
      return;
    } finally {
      replied = true;
      inFlight.current = null;
      setSending(false);
    }
    try {
      const clipsFailed = await Promise.race([following, stopping]);
      if (gone.current || clipsFailed === "stopped") return; // left or stopped meanwhile
      if (clipsFailed !== null) throw clipsFailed;
      // Nothing to say aloud, or every clip already passed over as broken.
      if (reply.streamed && clipsEnded.current >= clipCount) setWaiting(false);
      if (!reply.streamed) {
        // Not streamed: the whole reply is spoken in one video (roadmap R17), asked for by the
        // server's count, which another tab's replies may have moved on from this tab's.
        const url = await Promise.race([speakReply(reply.turn, replyId), stopping]);
        if (url === "stopped") return; // stopped while it was made
        // A new address each time, so the same reply number after a restart plays afresh.
        setClips(url ? [`${url}?t=${Date.now()}`] : []);
        clipTotal.current = url ? 1 : 0;
        if (!url) setWaiting(false); // nothing to say aloud
        if (url) {
          setWhole(true);
          setTimes([{ text: repliedAt, ready: performance.now(), started: null, ended: null }]);
        }
      }
    } catch (e) {
      console.error("Could not speak the reply", e);
      setUnspoken({ turn: shownAt }); // why is in the console above, not shown (R41d)
      setWaiting(false);
    } finally {
      setSpeaking(false);
    }
  }

  // Repeat (roadmap R156): the latest reply is said again from its clips, or spoken again from
  // its text, with no LLM call; the conversation is unchanged. Stop stops it like a reply.
  async function repeat() {
    if (busy) return;
    const replyId = newReplyId();
    replying.current = replyId;
    const stopping = new Promise<"stopped">((resolve) => {
      wakeOnStop.current = () => resolve("stopped");
    });
    const at = (turns ?? []).length - 1;
    console.info("Repeating the latest reply");
    setHalted(false);
    setSpeaking(true);
    setWaiting(true);
    clipTotal.current = 0;
    allMade.current = false;
    clipsEnded.current = 0;
    setFailed(null);
    setUnspoken(null);
    setClips([]);
    setEarlier((e) => [...e, ...clipWaits(times)]);
    setTimes([]);
    setWhole(false);
    try {
      if ((await Promise.race([repeatReply(replyId), stopping])) === "stopped") return;
      const count = await Promise.race([followClips(replyId, () => true), stopping]);
      if (gone.current || count === "stopped") return;
      allMade.current = true;
      if (clipsEnded.current >= count) setWaiting(false); // nothing to say aloud
    } catch (e) {
      console.error("Could not repeat the reply", e);
      setUnspoken({ turn: at });
      setWaiting(false);
    } finally {
      setSpeaking(false);
    }
  }

  // Stop (roadmap R19): the person stops speaking at once, and the server stops making the
  // reply's clips. A prompt still being answered is stopped too: the LLM is cut off and the
  // prompt goes back in the box (Larry's test of PR #129); a reply already written still shows.
  function stop() {
    const replyId = replying.current;
    if (replyId === null) return;
    stopped.current = replyId;
    wakeOnStop.current();
    setHalted(true); // the player pauses and fades back to the idle video (R41c)
    setWaiting(false);
    setTimes([]);
    setWhole(false);
    console.info(`Reply stopped (${clips.length} clips so far)`);
    stopReply(replyId).catch((e: unknown) => console.error("Could not stop the reply", e));
  }

  function changeSound(change: Partial<Sound>) {
    const next = { ...sound, ...change };
    setSound(next);
    saveSound(next);
  }

  // Something to stop: a reply still being made, or a clip that hasn't finished playing.
  const stoppable = !halted && (speaking || times.some((t) => t.ended === null));
  const stage = (
    <Stage
      idle={idle}
      onIdle={setIdle}
      photo={photo?.url}
      ratio={photo?.ratio}
      idleUrl={photo === undefined ? null : photo.idle}
    >
      {clips.length > 0 && (
        <ClipPlayer
          clips={clips}
          onStarted={started}
          onEnded={ended}
          sound={sound}
          rest={idle === "ready"}
          stopped={halted}
        />
      )}
    </Stage>
  );
  // The person shows from the start, while the conversation loads (R41c). On a wide screen
  // they are on the left and the conversation on the right; on a narrow one, above it (R41d).
  // Nothing is drawn until the photo's shape is known, so the frame never changes size (R41d).
  if (photo === undefined) return <p className="muted busy">Loading…</p>;
  if (turns === null)
    return (
      <div className="chat">
        <div className="person">{stage}</div>
        <div className="talk">
          <p className="muted busy">Loading…</p>
        </div>
      </div>
    );
  // One line saying what is happening, until the person starts to speak (R41d).
  // Stopped while thinking: the server is cutting the LLM off.
  const status = gettingReady
    ? preparingChat(leftS)
    : sending
    ? halted
      ? "Stopping…"
      : "Thinking…"
    : waiting
      ? "Getting ready to say it…"
      : null;
  return (
    <div className="chat">
      <div className="person">
        {stage}
        <SoundControls
          sound={sound}
          onChange={changeSound}
          onStop={stoppable ? stop : undefined}
          onExit={exit}
          saying={saying !== null}
        />
        {metrics && times.length > 0 && (
          <ClipTimes times={times} whole={whole} earlier={earlier} />
        )}
      </div>
      <div className="talk">
        {turns.length === 0 && !notClear && (
          <p className="muted hint">Ask a question to start the conversation.</p>
        )}
        <TurnList
          turns={turns}
          from={latestExchange(turns)}
          unspoken={unspoken}
          notice={notClear ? CHECK_HEARD : undefined}
        />
        {turns[turns.length - 1]?.role === "assistant" && !notClear && (
          <ReplyActions
            disabled={busy}
            onRepeat={() => void repeat()}
            onSimpler={quizGoing ? undefined : () => void send(SAY_IT_SIMPLER)}
            simpler={simplerOf?.reply === latestReply ? simplerOf.simpler : null}
          />
        )}
        <p className="status muted" aria-live="polite">
          {status && <span className="busy">{status}</span>}
        </p>
        {failed && (
          <p className="error" role="alert">
            {failed}
          </p>
        )}
        <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <label className="prompt">
          <span>Your message</span>
          <textarea
            ref={promptBox}
            rows={2}
            placeholder="Type your question here"
            value={prompt}
            onInput={(e) => setPrompt(e.currentTarget.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift+Enter starts a new line.
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
        </label>
        <div className="send-buttons">
          <button type="submit" disabled={busy || !prompt.trim()}>
            Send
          </button>
          <TalkButton
            disabled={busy}
            onHearing={setPrompt}
            onHeard={(text) => void send(text, true)}
            onUnsure={(text) => {
              unsure.current = text;
              setNotClear(true);
              promptBox.current?.focus();
            }}
            onEdit={(text) => {
              unsure.current = text;
              promptBox.current?.focus();
            }}
            onProblem={(problem) => {
              setFailed(problem);
              setNotClear(false); // listening again, or it failed
            }}
          />
          {teachMe && !quizGoing && (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => void send(TEACH_ME)}
            >
              Teach me
            </button>
          )}
          {quizMe && !quizGoing && (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => void send(QUIZ_ME)}
            >
              Quiz me
            </button>
          )}
          {assessOn && !quizGoing && (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => void send(ASSESS_ME)}
            >
              Assessment
            </button>
          )}
        </div>
      </form>
      {/* The choices are a lesson's or a quiz's, so they go with the settings (review on PR
          #87). While a quiz is going, whatever is sent is taken as the answer, so only the quiz's
          own controls are shown (review on PR #88). */}
      {(teachMe || quizMe || assessOn) && !quizGoing && (
        <Choices choices={choices} disabled={busy} onAsk={(q) => void send(q)} />
      )}
      {teachMe && lesson?.active && !quizGoing && (
        <LessonControls
          lesson={lesson}
          disabled={busy}
          onAsk={(q) => void send(q)}
        />
      )}
      {quizGoing && !assessing && quiz && (
        <QuizControls quiz={quiz} disabled={busy} onAsk={(q) => void send(q)} />
      )}
      {assessing && assessment && (
        <AssessmentControls
          assessment={assessment}
          disabled={busy}
          onAsk={(q) => void send(q)}
        />
      )}
      {!quizGoing && (
        <Hints hints={hints} disabled={busy} onAsk={(q) => void send(q)} />
      )}
      {turns.length > 0 && <History turns={turns} unspoken={unspoken} />}
      {debug && <CopyChat turns={turns} />}
      </div>
    </div>
  );
}

// What the Teach me button sends (R41h); typing it does the same.
const TEACH_ME = "Teach me";

// What the Quiz me button sends (R41i); typing it does the same.
const QUIZ_ME = "Quiz me";

// What the Assessment button sends (R41j); typing it does the same.
const ASSESS_ME = "Assess me";

// While an assessment is going (R41j): the question being asked, and Stop. The answer is typed
// in the prompt box.
function AssessmentControls(props: {
  assessment: Assessment;
  disabled: boolean;
  onAsk: (prompt: string) => void;
}) {
  const { number, total } = props.assessment;
  return (
    <div className="lesson">
      <p className="muted">
        Assessment · question {number} of {total}
      </p>
      <div className="lesson-buttons">
        <button
          type="button"
          className="secondary"
          disabled={props.disabled}
          onClick={() => props.onAsk("Stop the assessment")}
        >
          Stop the assessment
        </button>
      </div>
    </div>
  );
}

// While a quiz is going (R41i): its topic, the question being asked, and Stop. The answer is
// typed in the prompt box.
function QuizControls(props: { quiz: Quiz; disabled: boolean; onAsk: (prompt: string) => void }) {
  const { topic, number, questions } = props.quiz;
  return (
    <div className="lesson">
      <p className="muted">
        Quiz: {topic} · question {number}
        {questions === undefined ? "" : ` of ${questions}`}
      </p>
      <div className="lesson-buttons">
        <button
          type="button"
          className="secondary"
          disabled={props.disabled}
          onClick={() => props.onAsk("Stop the quiz")}
        >
          Stop the quiz
        </button>
      </div>
    </div>
  );
}

// What Say it simpler sends (R157); typing it does the same. In a lesson, it is the lesson's own
// "Say it more simply" (R41h).
const SAY_IT_SIMPLER = "Say it simpler";

// Under the latest reply: Repeat says it again (R156), and Say it simpler has the LLM say it
// again in simpler terms (R157). Say it simpler can be pressed only when the reply can be said
// more simply (`simpler`, null while that is being checked: R177). Not while a quiz is going,
// where whatever is sent is the answer.
function ReplyActions(props: {
  disabled: boolean;
  onRepeat: () => void;
  onSimpler?: () => void;
  simpler?: boolean | null;
}) {
  return (
    <div className="reply-actions">
      <button
        type="button"
        className="secondary"
        disabled={props.disabled}
        onClick={props.onRepeat}
      >
        Repeat
      </button>
      {props.onSimpler && (
        <button
          type="button"
          className="secondary"
          disabled={props.disabled || props.simpler !== true}
          title={
            props.simpler === false
              ? "This reply can't be said more simply."
              : props.simpler == null
                ? "Finding a simpler way to say it…"
                : undefined
          }
          onClick={() => {
            console.info("Say it simpler");
            props.onSimpler?.();
          }}
        >
          {SAY_IT_SIMPLER}
        </button>
      )}
    </div>
  );
}

// Buttons offered with the latest reply, such as which topic to learn (R41h).
function Choices(props: { choices: Choice[]; disabled: boolean; onAsk: (prompt: string) => void }) {
  if (props.choices.length === 0) return null;
  return (
    <ul className="choices-row" aria-label="Choices">
      {props.choices.map((choice) => (
        <li key={choice.prompt}>
          <button
            type="button"
            className="example"
            disabled={props.disabled}
            onClick={() => props.onAsk(choice.prompt)}
          >
            {choice.label}
          </button>
        </li>
      ))}
    </ul>
  );
}

// While a lesson is going (R41h): where it is, and Next, more simply and Stop.
function LessonControls(props: {
  lesson: Lesson;
  disabled: boolean;
  onAsk: (prompt: string) => void;
}) {
  const { topic, part, parts } = props.lesson;
  const where =
    parts === undefined ? "" : part >= parts ? " · summary" : ` · part ${part + 1} of ${parts}`;
  return (
    <div className="lesson">
      <p className="muted">
        Lesson: {topic}
        {where}
      </p>
      <div className="lesson-buttons">
        {["Next", "Say it more simply", "Stop the lesson"].map((label) => (
          <button
            key={label}
            type="button"
            className="secondary"
            disabled={props.disabled}
            onClick={() => props.onAsk(label)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

// Under the prompt box (R41g): a line leading into the topics, and example questions about them
// that are sent when clicked, three at a time. "other topics..." shows the next three, wrapping
// round to the first, when there are more (R182).
export const SHOWN_EXAMPLES = 3;

function Hints(props: { hints: ChatHints; disabled: boolean; onAsk: (question: string) => void }) {
  const { line, examples } = props.hints;
  const [first, setFirst] = useState(0);
  if (!line && examples.length === 0) return null;
  const shown = shownExamples(examples, first);
  return (
    <div className="hints">
      {line && <p className="muted">{line}</p>}
      {examples.length > 0 && (
        <ul aria-label="Example questions">
          {shown.map((question) => (
            <li key={question}>
              <button
                type="button"
                className="example"
                disabled={props.disabled}
                onClick={() => {
                  console.info("Example question asked");
                  props.onAsk(question);
                }}
              >
                {question}
              </button>
            </li>
          ))}
          {examples.length > SHOWN_EXAMPLES && (
            <li>
              <button
                type="button"
                className="link"
                onClick={() => {
                  const next = (first + SHOWN_EXAMPLES) % examples.length;
                  console.info(`Other topics shown, from ${next + 1} of ${examples.length}`);
                  setFirst(next);
                }}
              >
                other topics...
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

// The example questions shown, starting at `first` and wrapping round to the start, so there
// are always SHOWN_EXAMPLES of them when there are that many (R182).
export function shownExamples(examples: string[], first: number): string[] {
  if (examples.length <= SHOWN_EXAMPLES) return examples;
  return Array.from(
    { length: SHOWN_EXAMPLES },
    (_, i) => examples[(first + i) % examples.length],
  );
}

// Where the latest exchange starts: the last prompt, with the reply after it if there is one.
export function latestExchange(turns: Turn[]): number {
  for (let i = turns.length - 1; i >= 0; i--) if (turns[i].role === "user") return i;
  return Math.max(turns.length - 1, 0);
}

// The turns from `from` on, numbered by their place in the whole conversation so a note on a
// reply that couldn't be spoken stays with it. With `search`, the matches of its query are
// marked, numbered in order, and the current one stands out. A `notice` shows last as a reply
// that isn't part of the conversation (R179).
function TurnList(props: {
  turns: Turn[];
  from?: number;
  unspoken: { turn: number } | null;
  search?: { query: string; current: number };
  notice?: string;
}) {
  const { turns, from = 0, unspoken, search, notice } = props;
  let counted = 0; // matches marked in the turns before this one
  return (
    <ol className="turns">
      {turns.slice(from).map((turn, k) => {
        const i = from + k;
        const first = counted;
        const parts = search ? splitMatches(turn.content, search.query) : [turn.content];
        counted += (parts.length - 1) / 2;
        return (
          <li key={i} className={turn.role}>
            <span className="who">{turn.role === "user" ? "You" : "Reply"}</span>
            {search ? (
              <span>
                {parts.map((part, p) => {
                  if (p % 2 === 0) return part;
                  const n = first + (p - 1) / 2;
                  const current = n === search.current ? "current" : undefined;
                  return (
                    <mark key={p} data-match={n} className={current}>
                      {part}
                    </mark>
                  );
                })}
              </span>
            ) : (
              turn.content
            )}
            {unspoken?.turn === i && (
              <span className="note">
                I couldn&apos;t say this one aloud, so here it is as text.
              </span>
            )}
          </li>
        );
      })}
      {notice && (
        <li className="assistant notice" role="status">
          <span className="who">Reply</span>
          {notice}
        </li>
      )}
    </ol>
  );
}

// Splits `text` around each match of `query`, ignoring case: the even items are the text
// between matches and the odd ones the matches, as written. A blank query matches nothing.
export function splitMatches(text: string, query: string): string[] {
  const q = query.trim().toLowerCase();
  if (!q) return [text];
  const lower = text.toLowerCase();
  const parts: string[] = [];
  let at = 0;
  for (let found = lower.indexOf(q); found >= 0; found = lower.indexOf(q, at)) {
    parts.push(text.slice(at, found), text.slice(found, found + q.length));
    at = found + q.length;
  }
  parts.push(text.slice(at));
  return parts;
}

// How many times `query` is found in the conversation.
export function countMatches(turns: Turn[], query: string): number {
  return turns.reduce((n, turn) => n + (splitMatches(turn.content, query).length - 1) / 2, 0);
}

// The whole conversation, both the prompts and the replies, closed on every page load so the
// video stays the focus (roadmap R18a). Opened, it is a box of limited height with its own
// scrollbar, kept scrolled to the newest turn, and a search box that marks every match and steps
// through them with Next and Previous, or Enter and Shift+Enter (roadmap R18).
// The conversation as text to paste somewhere else: the last `count` exchanges (a prompt and its
// reply), oldest first.
// The chat's exchanges, a prompt and its reply each. A prompt still waiting for its reply isn't
// one yet, so it isn't copied (review on PR #89).
export function exchanges(turns: Turn[]): Turn[][] {
  const found: Turn[][] = [];
  for (const turn of turns) {
    if (turn.role === "user" || found.length === 0) found.push([turn]);
    else found[found.length - 1].push(turn);
  }
  const last = found[found.length - 1];
  if (last?.length === 1 && last[0].role === "user") found.pop();
  return found;
}

export function chatText(turns: Turn[], count: number): string {
  const all = exchanges(turns);
  const kept = all.slice(Math.max(all.length - count, 0));
  const head = `Chat: the last ${kept.length} of ${all.length} exchanges`;
  const lines = kept.flat().map((t) => `${t.role === "user" ? "You" : "Reply"}: ${t.content}`);
  return [head, ...lines].join("\n\n");
}

// With Debug on in the settings: copies the last N exchanges, all of them unless N is lowered, so
// they can be pasted elsewhere for review (Larry, 2026-10-15). Where the browser won't copy, the
// text is shown to copy by hand. What a copy did is shown only while the chat is the one it
// copied: a new turn, or a copy still under way when one comes, makes it out of date (review on
// PR #89).
function CopyChat(props: { turns: Turn[] }) {
  const all = exchanges(props.turns).length;
  const [count, setCount] = useState<number | null>(null); // null: every exchange
  // What the last copy did, and the chat (and count) it copied.
  const [done, setDone] = useState<{ turns: Turn[]; shown: number; byHand: string | null }>();
  if (all === 0) return null;
  const shown = Math.min(count ?? all, all);
  const current = done?.turns === props.turns && done.shown === shown ? done : undefined;

  async function copy() {
    const { turns } = props;
    const text = chatText(turns, shown);
    try {
      await navigator.clipboard.writeText(text);
      console.info(`Chat copied (${shown} of ${all} exchanges, ${text.length} characters)`);
      setDone({ turns, shown, byHand: null });
    } catch (e) {
      console.error("Could not copy the chat", e);
      setDone({ turns, shown, byHand: text });
    }
  }

  return (
    <div className="copy-chat">
      <label>
        Copy the last{" "}
        <input
          type="number"
          min={1}
          max={all}
          value={shown}
          onChange={(e) => {
            const n = Math.round(Number(e.currentTarget.value));
            setCount(Number.isFinite(n) ? Math.min(Math.max(n, 1), all) : null);
          }}
        />{" "}
        of {all} exchanges
      </label>
      <button type="button" className="secondary" onClick={() => void copy()}>
        Copy chat
      </button>
      {current && current.byHand === null && <span className="muted">Copied</span>}
      {current?.byHand != null && (
        <textarea
          readOnly
          aria-label="Chat to copy"
          value={current.byHand}
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
    </div>
  );
}

export function History(props: { turns: Turn[]; unspoken: { turn: number } | null }) {
  const { turns, unspoken } = props;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [current, setCurrent] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const total = query.trim() ? countMatches(turns, query) : 0;
  // The match shown as current, kept in range when the conversation shrinks under it (a prompt
  // taken back when the LLM fails).
  const active = Math.min(current, Math.max(total - 1, 0));
  useEffect(() => {
    if (open && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [open, turns]);
  useEffect(() => {
    if (total === 0) return;
    const mark = box.current?.querySelector(`mark[data-match="${active}"]`);
    mark?.scrollIntoView?.({ block: "nearest" });
  }, [open, query, active, total]);

  function toggle() {
    console.info(`Chat history ${open ? "hidden" : "shown"} (${turns.length} turns)`);
    if (open) search(""); // it opens again without the old search
    setOpen(!open);
  }

  function search(text: string) {
    const began = performance.now();
    const found = text.trim() ? countMatches(turns, text) : 0;
    setQuery(text);
    setCurrent(0);
    if (text.trim()) {
      const ms = Math.round(performance.now() - began);
      console.info(`History search found ${found} matches in ${turns.length} turns (${ms} ms)`);
    }
  }

  // Steps to the next match, or back with -1, wrapping round at either end.
  function step(by: number) {
    if (total > 0) setCurrent((active + by + total) % total);
  }

  return (
    <section className="history">
      <button type="button" className="link" aria-expanded={open} onClick={toggle}>
        {open ? "Hide history" : "Show history"}
      </button>
      {open && (
        <>
          <div className="history-search" role="search">
            <input
              type="search"
              aria-label="Search the history"
              placeholder="Search the history"
              value={query}
              onInput={(e) => search(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  step(e.shiftKey ? -1 : 1);
                }
              }}
            />
            <button type="button" disabled={total < 2} onClick={() => step(-1)}>
              Previous
            </button>
            <button type="button" disabled={total < 2} onClick={() => step(1)}>
              Next
            </button>
            {query.trim() && (
              <span className="muted" aria-live="polite">
                {total === 0 ? "No matches" : `${active + 1} of ${total}`}
              </span>
            )}
          </div>
          <div ref={box} className="history-box" tabIndex={0} aria-label="Conversation history">
            <TurnList turns={turns} unspoken={unspoken} search={{ query, current: active }} />
          </div>
        </>
      )}
    </section>
  );
}

// Whether the idle video is loading, showing, or there is none (an engine that can't make
// one, or it failed: then the chat holds each reply's last frame, as before R23).
export type Idle = "loading" | "ready" | "none";

// Where the person is shown (roadmap R23): between replies, the idle video plays on a loop, so
// the person blinks and moves slightly instead of freezing; a reply's clips play over it. The
// stage keeps one size from the start, and the photo the videos are made from shows under them,
// so there is no empty or black frame while a video loads and nothing jumps when one starts
// (R41c): each video fades in over the photo once it plays.
export function Stage(props: {
  idle: Idle;
  onIdle: (idle: Idle) => void;
  photo?: string | null;
  // The photo's width over its height. The videos are made from it, so the stage takes its
  // shape and has no empty bands beside or above the person (R41d); a 4:3 box without it.
  ratio?: number | null;
  // The idle video's address for the photo; null until it is known, so the person before's
  // isn't fetched first (Larry's test of R32a). IDLE_VIDEO_URL when not given.
  idleUrl?: string | null;
  children?: ComponentChildren;
}) {
  const { idle, onIdle, photo, ratio } = props;
  const idleUrl = props.idleUrl === undefined ? IDLE_VIDEO_URL : props.idleUrl;
  const [still, setStill] = useState(true); // the photo loaded, or is loading
  return (
    <div className="stage" style={ratio ? { "--ratio": String(ratio) } : undefined}>
      {photo && still && (
        <img
          className="still"
          src={photo}
          alt=""
          onError={() => {
            console.error(`Could not show the photo under the video: ${photo}`);
            setStill(false);
          }}
        />
      )}
      {idle !== "none" && idleUrl !== null && (
        <video
          className={idle === "ready" ? "idle-video" : "idle-video resting"}
          src={idleUrl}
          autoPlay
          loop
          muted
          playsInline
          disablePictureInPicture
          onPlaying={() => {
            if (idle === "ready") return;
            console.info("Idle video ready");
            onIdle("ready");
          }}
          onError={() => {
            console.info("No idle video: the chat holds each reply's last frame");
            onIdle("none");
          }}
        />
      )}
      {props.children}
    </div>
  );
}

// Plays a reply's clips one after another, as they arrive (roadmap R22). When it reaches the
// end of the clips so far, it waits on the last frame for the next one. Two players take turns:
// while one plays a clip, the other loads the next, so the switch between sentences costs no
// time (roadmap R22a). `onStarted` and `onEnded` are told when each clip starts and ends. There
// are no controls: the person speaks on their own, as if live. Only if the browser refuses to
// play with sound (its autoplay rules) is there a button to start them.
export function ClipPlayer(props: {
  clips: string[];
  onStarted?: (clip: number, at: number) => void;
  onEnded?: (clip: number, at: number) => void;
  sound?: Sound; // the volume and mute (roadmap R19); full volume when not given
  // There is an idle video under the player (roadmap R23): each clip fades in over it when it
  // starts, and the player fades back to it when it runs out of clips, rather than holding the
  // last frame. Clips that follow straight on join without a fade, as each starts where the
  // one before ended.
  rest?: boolean;
  // Stop was pressed (roadmap R19): the clip pauses at once, then fades back to the idle video,
  // or holds its frame when there is none (R41c).
  stopped?: boolean;
}) {
  const { clips, onStarted, onEnded, sound, rest, stopped } = props;
  const [on, setOn] = useState(false); // a clip is showing, not resting on the idle video
  const [playing, setPlaying] = useState(0); // the clip to play; clips.length once all have
  const [active, setActive] = useState(0); // which of the two players is showing
  const players = [useRef<HTMLVideoElement>(null), useRef<HTMLVideoElement>(null)];
  const [refused, setRefused] = useState(false); // the browser wouldn't play it by itself
  const begun = useRef(new Set<number>()); // clips that have started, told of once each
  const broken = useRef(new Set<string>()); // clips that failed to load while waiting
  const first = clips[0];

  function play(player: HTMLVideoElement | null) {
    if (stopped) return;
    try {
      void player
        ?.play()
        ?.then(() => setRefused(false))
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === "NotAllowedError") setRefused(true);
        });
    } catch {
      // Not every browser (or test) can play.
    }
  }

  useLayoutEffect(() => {
    // A new reply starts from its first clip, which plays by itself. Reset before the browser
    // can tell of the clip playing, so that isn't undone here (R41c).
    setPlaying(0);
    setActive(0);
    setOn(false);
    begun.current = new Set();
    play(players[0].current);
  }, [first]);
  useLayoutEffect(() => {
    // Both players, so the next clip starts at the same volume; set before the browser
    // paints, so a new player never starts at full volume.
    for (const player of players) {
      if (!player.current) continue;
      player.current.volume = sound?.volume ?? 1;
      player.current.muted = sound?.muted ?? false;
    }
  });
  const current = Math.min(playing, clips.length - 1);
  const shown = clips[current];
  const next = clips[current + 1];
  useEffect(() => {
    // The next clip is showing: the other player took over with it loaded, or, when playing
    // caught up with the clips, it arrived in the same player after the last one ended. Either
    // way it is started here, so a refusal shows the button.
    if (shown === first) return; // the first clip is started above
    if (broken.current.has(shown)) skip(shown);
    else play(players[active].current);
  }, [active, shown]);
  useEffect(() => {
    if (!stopped) return;
    for (const player of players) {
      try {
        player.current?.pause();
      } catch {
        // Not every browser (or test) can pause.
      }
    }
    if (rest) setOn(false);
    setRefused(false);
  }, [stopped]);
  useEffect(() => {
    // The idle video came after the reply ended or was stopped, so its held frame fades to it.
    if (rest && (stopped || playing >= clips.length)) setOn(false);
  }, [rest]);

  function begins(at: number) {
    setOn(true);
    if (playing < clips.length && !begun.current.has(playing)) {
      begun.current.add(playing);
      onStarted?.(playing, at);
    }
  }

  function ends(at: number) {
    if (playing >= clips.length) return; // played again by hand, after the last clip so far
    onEnded?.(playing, at);
    if (next !== undefined) {
      // The next clip is loaded there already; one that failed to load is passed over out of
      // sight, so its empty player is never shown (R41c).
      if (broken.current.has(next)) setOn(false);
      setActive((a) => 1 - a);
    } else if (rest) setOn(false); // back to the idle video until the next clip comes
    setPlaying(playing + 1);
  }

  // A clip that can't be played is passed over quietly (R41c): the reply's text still shows,
  // and the clips after it still play.
  function skip(url: string) {
    console.error(`Could not play a clip of the reply, so it was skipped: ${url}`);
    setOn(false);
    ends(performance.now());
  }

  return (
    <>
      {[0, 1].map((n) =>
        n === active ? (
          <video
            key={n}
            ref={players[n]}
            className={on ? "reply-video" : "reply-video resting"}
            src={shown}
            autoPlay={!stopped}
            playsInline
            disablePictureInPicture
            onPlaying={() => begins(performance.now())}
            onEnded={() => ends(performance.now())}
            onError={() => skip(shown)}
          />
        ) : (
          next !== undefined && (
            <video
              key={n}
              ref={players[n]}
              src={next}
              preload="auto"
              playsInline
              hidden
              onError={() => broken.current.add(next)}
            />
          )
        ),
      )}
      {refused && !stopped && (
        <button type="button" className="play-reply" onClick={() => play(players[active].current)}>
          Play the reply
        </button>
      )}
    </>
  );
}

// Stop, mute and volume for the person speaking (roadmap R19). Stop is always shown, first and in
// red, so it is easy to find; it can be clicked only while there is something to stop.
export function SoundControls(props: {
  sound: Sound;
  onChange: (change: Partial<Sound>) => void;
  onStop?: () => void;
  // Exit (roadmap R29), shown last when given; it can't be clicked while "Goodbye." or
  // "Welcome back." is being said.
  onExit?: () => void;
  saying?: boolean;
}) {
  const { sound, onChange, onStop, onExit, saying } = props;
  return (
    <div className="sound-controls">
      <button type="button" className="stop" onClick={onStop} disabled={onStop === undefined}>
        <span className="stop-icon" aria-hidden="true" />
        Stop
      </button>
      <button
        type="button"
        className="secondary"
        aria-pressed={sound.muted}
        onClick={() => onChange({ muted: !sound.muted })}
      >
        {sound.muted ? "Unmute" : "Mute"}
      </button>
      <label>
        <span>Volume</span>
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(sound.volume * 100)}
          disabled={sound.muted}
          onInput={(e) => onChange({ volume: Number(e.currentTarget.value) / 100 })}
        />
      </label>
      {onExit && (
        <button type="button" className="secondary" onClick={onExit} disabled={saying}>
          Exit
        </button>
      )}
    </div>
  );
}

// 1.26 -> "1.3 s"
function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`;
}

// How long each clip that has started waited, in milliseconds: from when it could have started
// (its text arrived, and the clip before it ended) to when it did.
export function clipWaits(times: ClipTime[]): number[] {
  return times.flatMap((_, i) => {
    const wait = clipWait(times, i);
    return wait === null ? [] : [wait];
  });
}

// How long clip i waited, as above, or null if it has not started.
function clipWait(times: ClipTime[], i: number): number | null {
  const t = times[i];
  if (t.started === null) return null;
  const before = times[i - 1]?.ended ?? null;
  return Math.max(0, t.started - Math.max(t.text, before ?? t.text));
}

function average(waits: number[]): number {
  return waits.reduce((a, b) => a + b, 0) / waits.length;
}

// How long each clip took to be spoken, against the 1 to 2 second target (roadmap R22a): from
// its text arriving from the LLM to it playing, and the pause after the clip before it. A clip
// is late when its wait passes the target: from its text for the first, and from the later of
// its text and the end of the clip before for the others, since a clip whose text arrived while
// the one before it was still playing is on time if it follows straight on. Then the average
// wait, for this reply and, with `earlier` (the waits of the replies before it since the page
// was opened), for all of them. A clip is a sentence, except the first, which is the first
// sentence's first clause (R22b). A reply spoken in one video has one line.
export function ClipTimes(props: { times: ClipTime[]; whole?: boolean; earlier?: number[] }) {
  const { times, whole, earlier = [] } = props;
  const limit = 2000;
  const waits = clipWaits(times);
  const all = [...earlier, ...waits];
  return (
    <div className="timing">
      <span>Timing (target 1 to 2 s)</span>
      <ol>
        {times.map((t, i) => {
          const name = whole ? "Reply" : `Clip ${i + 1}`;
          if (t.started === null) return <li key={i}>{name}: not spoken yet</li>;
          const after = t.started - t.text;
          const before = times[i - 1];
          const pause = before?.ended === null || before === undefined ? null : Math.max(0, t.started - before.ended);
          const late = (clipWait(times, i) ?? 0) > limit;
          return (
            <li key={i} className={late ? "late" : undefined}>
              {name}: spoken {seconds(after)} after its text arrived
              {pause !== null && `, ${seconds(pause)} after clip ${i} ended`}
            </li>
          );
        })}
      </ol>
      {waits.length > 0 && (
        <p className={average(waits) > limit ? "average late" : "average"}>
          Average wait: {seconds(average(waits))} over {waits.length}{" "}
          {waits.length === 1 ? "clip" : "clips"} of this reply
          {earlier.length > 0 &&
            `; ${seconds(average(all))} over ${all.length} clips since the page was opened`}
        </p>
      )}
    </div>
  );
}

// Next to each step: done (and how long it took), what it is doing and about how long it has left
// (R134b), or waiting its turn.
function StepState(props: { step: PrepareStep; status: PrepareStatus; index: number }) {
  const { step, status } = props;
  const metrics = useSettings().show_metrics; // how long a step took (R41a)
  if (step.done >= step.total) {
    const took = metrics && step.seconds !== null ? ` in ${duration(step.seconds)}` : "";
    return <span className="done">Done{took}</span>;
  }
  const current = status.steps?.findIndex((s) => s.done < s.total) === props.index;
  if (!current) return <span className="muted">Waiting</span>;
  if (status.state === "cancelled") return <span className="muted">Stopped</span>;
  if (status.state === "failed" || status.stopped) return <span className="error">Stopped</span>;
  return (
    <span className="busy">
      {step.activity ?? (step.total > 1 ? `${step.done} of ${step.total}` : "Working…")}
      {step.left_s !== null && ` · about ${countdown(step.left_s)} left`}
    </span>
  );
}

// The time left while preparing, to the second, so the page changes as it counts down
// (review on PR #170): 42 -> "42 s", 725 -> "12 min 5 s", 3785 -> "1 h 3 min 5 s".
export function countdown(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const parts = [h && `${h} h`, (h || m) && `${m} min`, `${s % 60} s`];
  return parts.filter(Boolean).join(" ");
}

// 42 -> "42 s", 1034 -> "17 min"
export function duration(seconds: number): string {
  return seconds < 90 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
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
