// The app's pages. Each one is a function that returns what the page shows.

import { useEffect, useState } from "preact/hooks";

import {
  confirmConsent,
  type Kind,
  listUploads,
  removeUpload,
  type Upload,
  uploadFile,
  uploadUrl,
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

// Setup step 1 (roadmap R7): upload photos and recordings, see them and play them back.
export function SetupPage() {
  return (
    <>
      <h1>Setup</h1>
      <p className="done">Thank you, consent is confirmed.</p>
      <UploadSection
        kind="photos"
        title="Photos"
        hint="Add the five photos from the recording guide (JPG, PNG or HEIC). At least one is needed; the app will pick the best."
        accept="image/jpeg,image/png,image/heic,.heic"
      />
      <UploadSection
        kind="sounds"
        title="Recordings"
        hint="Add the voice recordings from the recording guide (WAV, M4A or MP3, up to 10 minutes each)."
        accept="audio/*,.m4a,.wav,.mp3"
      />
    </>
  );
}

interface Refused {
  name: string;
  reason: string;
}

function UploadSection(props: { kind: Kind; title: string; hint: string; accept: string }) {
  const { kind } = props;
  // null until the list has loaded.
  const [items, setItems] = useState<Upload[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [sending, setSending] = useState<string | null>(null);
  const [refused, setRefused] = useState<Refused[]>([]);

  useEffect(() => {
    listUploads(kind)
      .then(setItems)
      .catch((e: unknown) => {
        console.error(`Could not list ${kind}`, e);
        setLoadFailed(true);
      });
  }, [kind]);

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
    } catch (e) {
      console.error(`Could not remove ${item.name}`, e);
      setRefused([{ name: item.name, reason: "Could not remove it. Please try again." }]);
    }
  }

  // Adding waits for the first list, so a late list can't hide a file uploaded meanwhile.
  const ready = sending === null && (items !== null || loadFailed);

  return (
    <section>
      <h2>{props.title}</h2>
      <p className="muted">{props.hint}</p>
      <label className="button">
        {sending
          ? `${kind === "photos" ? "Uploading and checking" : "Uploading"} ${sending}…`
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
      {items?.length === 0 && <p className="muted">None yet.</p>}
      <ul className={kind}>
        {items?.map((item) => (
          <li key={item.id}>
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
            {kind === "photos" && <FaceChecks problems={item.problems} />}
            <button type="button" className="remove" onClick={() => remove(item)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

// Under each photo (roadmap R8): what to fix, or that it passed the face checks.
function FaceChecks({ problems }: { problems: string[] | null }) {
  if (problems == null) return <span className="muted check">Not checked</span>;
  if (problems.length === 0) return <span className="done check">Looks good</span>;
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
