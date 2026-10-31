// The Customization page (roadmap R92 and R94, items 85 and 87): the AI's identity, its goals and
// each feature's guidelines, which the LLM is given with every prompt, edited and saved by a
// signed-in host. A save is used from the next prompt, and kept as a version in the History (R95).

import { useEffect, useState } from "preact/hooks";

import {
  type Customization,
  type CustomizationDraft,
  type CustomizationVersion,
  type GuidelineFeature,
  discardDraft,
  generateDraft,
  getCustomization,
  getCustomizationHistory,
  restoreCustomizationVersion,
  saveDraft,
  saveGoals,
  saveGuidelines,
  saveIdentity,
  ServerRefusal,
} from "./api";
import { HostOnlyPage, useHost } from "./host";

type Identity = Customization["identity"];

const IDENTITY: [keyof Identity, string, string][] = [
  ["name", "Name", "Said first to \"Who are you?\": I'm …"],
  ["speaks_as", "Speaks as", "Told to the LLM only."],
  ["purpose", "Purpose", "My purpose is …"],
  ["audience", "Who it is for", "I'm here for …"],
  ["helps_with", "What it can help with", "I can help with …"],
];

const SAVED = "Saved. It is used from the next prompt.";

// Saving one part of the page: whether it is being saved, and what to say after. While a save is
// in flight its editors are read-only, as what it gives back replaces them: text typed then would
// be lost (Codex's review on PR #243).
function useSave() {
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ ok: boolean; text: string } | null>(null);

  async function run(part: string, save: () => Promise<Customization>): Promise<Customization | null> {
    setBusy(true);
    setSaid(null);
    const started = performance.now();
    try {
      const saved = await save();
      console.info(`Customization saved: ${part} (${Math.round(performance.now() - started)} ms)`);
      setSaid({ ok: true, text: SAVED });
      return saved;
    } catch (e) {
      console.error(`Could not save the customization: ${part}`, e);
      setSaid({ ok: false, text: e instanceof ServerRefusal ? e.message : "Could not save. Try again." });
      return null;
    } finally {
      setBusy(false);
    }
  }

  const status = said && (
    <p className={said.ok ? "notice" : "error"} role="status">
      {said.text}
    </p>
  );
  return { busy, run, status, changed: () => setSaid(null) };
}

function IdentitySection({ identity }: { identity: Identity }) {
  const [fields, setFields] = useState(identity);
  const { busy, run, status, changed } = useSave();
  return (
    <section className="panel" aria-labelledby="customization-identity">
      <h2 id="customization-identity">Identity</h2>
      <p className="muted">Who the person in the video is. "Who are you?" is answered from it.</p>
      <form
        className="customization-edit"
        onSubmit={(e) => {
          e.preventDefault();
          void run("identity", () => saveIdentity(fields)).then((saved) => {
            if (saved) setFields(saved.identity);
          });
        }}
      >
        {IDENTITY.map(([key, label, about]) => (
          <label key={key}>
            <span>
              {label}
              <span className="muted"> · {about}</span>
            </span>
            <input
              value={fields[key]}
              readOnly={busy}
              onInput={(e) => {
                changed();
                setFields({ ...fields, [key]: e.currentTarget.value });
              }}
            />
          </label>
        ))}
        {status}
        <p>
          <button type="submit" disabled={busy}>
            Save the identity
          </button>
        </p>
      </form>
    </section>
  );
}

function GoalsSection({ goals }: { goals: string[] }) {
  const [text, setText] = useState(goals.join("\n"));
  const { busy, run, status, changed } = useSave();
  return (
    <section className="panel" aria-labelledby="customization-goals">
      <h2 id="customization-goals">Goals</h2>
      <p className="muted">What every reply aims for, one goal on each line.</p>
      <form
        className="customization-edit"
        onSubmit={(e) => {
          e.preventDefault();
          void run("goals", () => saveGoals(text.split("\n"))).then((saved) => {
            if (saved) setText(saved.goals.join("\n"));
          });
        }}
      >
        <label>
          <span className="sr-only">Goals</span>
          <textarea
            rows={4}
            value={text}
            readOnly={busy}
            onInput={(e) => {
              changed();
              setText(e.currentTarget.value);
            }}
          />
        </label>
        {status}
        <p>
          <button type="submit" disabled={busy}>
            Save the goals
          </button>
        </p>
      </form>
    </section>
  );
}

function FeatureGuidelines({ feature }: { feature: GuidelineFeature }) {
  const [shown, setShown] = useState(feature);
  const [text, setText] = useState(feature.text);
  const { busy, run, status, changed } = useSave();

  function save(value: string | null) {
    void run(`guidelines ${shown.key}`, () => saveGuidelines(shown.key, value)).then((saved) => {
      const now = saved?.features.find((f) => f.key === shown.key);
      if (now) {
        setShown(now);
        setText(now.text);
      }
    });
  }

  return (
    <form
      className="customization-edit guideline"
      aria-label={shown.label}
      onSubmit={(e) => {
        e.preventDefault();
        save(text);
      }}
    >
      <label>
        <span>
          {shown.label}
          {!shown.edited && <span className="muted"> · as shipped</span>}
          {shown.generated && <span className="muted"> · drafted by the LLM</span>}
        </span>
        <textarea
          rows={4}
          value={text}
          readOnly={busy}
          onInput={(e) => {
            changed();
            setText(e.currentTarget.value);
          }}
        />
      </label>
      <p className="muted">
        {shown.changes} {shown.stays}
      </p>
      {status}
      <p>
        <button type="submit" disabled={busy}>
          Save
        </button>{" "}
        <button type="button" className="secondary" disabled={busy || !shown.edited} onClick={() => save(null)}>
          Set back to how it shipped
        </button>
      </p>
    </form>
  );
}

// What each section of guidelines is about. Assessment and Level of detail have their own
// (Larry, PR #253).
const SECTION_ABOUT: Record<string, string> = {
  Guidelines: "How each feature writes what it says.",
  Assessment: "How the assessment writes its questions and judges the answers.",
  "Level of detail":
    "What the Level of detail bar on the chat screen asks of each reply, from High level to In depth.",
};

// The features in the sections they are shown in, in the order each section first comes.
export function sections(features: GuidelineFeature[]): [string, GuidelineFeature[]][] {
  const grouped = new Map<string, GuidelineFeature[]>();
  for (const feature of features) {
    const section = feature.section || "Guidelines";
    grouped.set(section, [...(grouped.get(section) ?? []), feature]);
  }
  return [...grouped.entries()];
}

function GuidelineSection({ name, features }: { name: string; features: GuidelineFeature[] }) {
  const id = `customization-${name.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section className="panel" aria-labelledby={id}>
      <h2 id={id}>{name}</h2>
      {SECTION_ABOUT[name] && <p className="muted">{SECTION_ABOUT[name]}</p>}
      {features.length ? (
        features.map((feature) => <FeatureGuidelines key={feature.key} feature={feature} />)
      ) : (
        <p className="muted">No feature has guidelines to edit yet.</p>
      )}
    </section>
  );
}

// What a draft shows beside the current text: each part of the identity it drafts, the goals,
// and the guidelines of each feature it drafted (R93).
const DRAFTED_IDENTITY: [keyof Identity, string][] = [
  ["name", "Name"],
  ["purpose", "Purpose"],
  ["audience", "Who it is for"],
  ["helps_with", "What it can help with"],
];

function draftRows(now: Customization, { draft, drafted }: CustomizationDraft): [string, string, string][] {
  const textOf = (c: Customization, key: string) => c.features.find((f) => f.key === key)?.text ?? "";
  return [
    ...DRAFTED_IDENTITY.map(([key, label]): [string, string, string] => [label, now.identity[key], draft.identity[key]]),
    ["Goals", now.goals.join("\n"), draft.goals.join("\n")],
    ...draft.features
      .filter((f) => drafted.includes(f.key))
      .map((f): [string, string, string] => [f.label, textOf(now, f.key), f.text]),
  ];
}

// Generate again (R93): the LLM drafts the identity, the goals and the guidelines the host
// hasn't changed, shown beside the current text; only Save keeps the draft.
function GenerateSection({ now, onSaved }: { now: Customization; onSaved: (saved: Customization) => void }) {
  const [draft, setDraft] = useState<CustomizationDraft | null>(null);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { busy, run, status, changed } = useSave();

  async function generate() {
    setWriting(true);
    setError(null);
    changed();
    const started = performance.now();
    try {
      setDraft(await generateDraft());
      console.info(`Customization draft made (${Math.round(performance.now() - started)} ms)`);
    } catch (e) {
      console.error("Could not make a customization draft", e);
      setError(e instanceof ServerRefusal ? e.message : "A draft could not be made. Try again.");
    } finally {
      setWriting(false);
    }
  }

  function discard() {
    setDraft(null);
    void discardDraft().catch((e: unknown) => console.error("Could not discard the draft", e));
  }

  return (
    <section className="panel" aria-labelledby="customization-generate">
      <h2 id="customization-generate">Generate again</h2>
      <p className="muted">
        The LLM drafts the identity, the goals and every feature's guidelines you haven't
        changed, from the person and the content. Guidelines you changed are left alone. Only
        Save keeps the draft.
      </p>
      {!draft && (
        <p>
          <button type="button" disabled={writing} onClick={() => void generate()}>
            Generate again
          </button>
        </p>
      )}
      {writing && <p className="muted busy">Writing a draft. This can take up to two minutes…</p>}
      {error && <p className="error">{error}</p>}
      {draft && (
        <div className="customization-draft">
          <table>
            <thead>
              <tr>
                <th scope="col">Part</th>
                <th scope="col">Now</th>
                <th scope="col">Draft</th>
              </tr>
            </thead>
            <tbody>
              {draftRows(now, draft).map(([label, current, drafted]) => (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  <td className="muted">{current}</td>
                  <td>{drafted}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {status}
          <p>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void run("draft", () => saveDraft(draft)).then((saved) => {
                  if (saved) {
                    setDraft(null);
                    onSaved(saved);
                  }
                })
              }
            >
              Save the draft
            </button>{" "}
            <button type="button" className="secondary" disabled={busy} onClick={discard}>
              Discard
            </button>
          </p>
        </div>
      )}
    </section>
  );
}

// What made a version, as the History list says it (R95).
export function madeBy(version: CustomizationVersion, features: GuidelineFeature[]): string {
  const label = features.find((f) => f.key === version.feature)?.label ?? version.feature;
  switch (version.made_by) {
    case "shipped":
      return "As shipped";
    case "generated":
      return "Drafted by the LLM";
    case "gone back to":
      return `Gone back to version ${version.back_to}`;
  }
  if (version.part === "identity") return "Saved the identity";
  if (version.part === "goals") return "Saved the goals";
  if (version.part === "guidelines set back") return `Set ${label} back to as shipped`;
  if (version.feature) return `Saved ${label}`;
  return "Saved";
}

function when(at: string): string {
  const date = new Date(at);
  return Number.isNaN(date.getTime()) ? at : date.toLocaleString();
}

// The History (R95): every saved version, newest first. Go back saves a copy of a version as the
// new latest one, so it can be undone; Edit goes to the editors, which edit the latest.
function HistorySection({
  features,
  onRestored,
}: {
  features: GuidelineFeature[];
  onRestored: (saved: Customization) => void;
}) {
  const [versions, setVersions] = useState<CustomizationVersion[] | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { busy, run, status, changed } = useSave();

  async function load(opened: boolean) {
    setError(null);
    const started = performance.now();
    try {
      const got = await getCustomizationHistory(opened);
      setVersions(got);
      console.info(`Customization history shown: ${got.length} versions (${Math.round(performance.now() - started)} ms)`);
    } catch (e) {
      console.error("Could not read the customization history", e);
      setError("The history could not be read. Try again.");
    }
  }

  function toggle() {
    changed();
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    void load(true);
  }

  async function goBack(number: number) {
    const saved = await run(`went back to version ${number}`, () => restoreCustomizationVersion(number));
    if (saved) {
      console.info(`Customization restored: version ${number}`);
      onRestored(saved);
      await load(false);
    }
  }

  function edit() {
    setOpen(false);
    document.getElementById("customization-identity")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <section className="panel" aria-labelledby="customization-history">
      <h2 id="customization-history">History</h2>
      <p className="muted">
        Every save is kept as a version. Go back to one to make a copy of it the latest; that can
        be undone by going back again.
      </p>
      <p>
        <button type="button" className="secondary" aria-expanded={open} onClick={toggle}>
          {open ? "Hide the history" : "History"}
        </button>
      </p>
      {open && error && <p className="error">{error}</p>}
      {open && !error && versions === null && <p className="muted busy">Loading…</p>}
      {open && versions?.length === 0 && (
        <p className="muted">Nothing has been saved yet. Each save from now on is kept here.</p>
      )}
      {open && versions && versions.length > 0 && (
        <ol className="customization-history" reversed>
          {versions.map((v, i) => (
            <li key={v.number}>
              <span>
                <strong>Version {v.number}</strong>
                {i === 0 && " (latest)"} · {madeBy(v, features)}
                <span className="muted"> · {when(v.made_at)}</span>
              </span>
              {i === 0 ? (
                <button type="button" className="secondary" onClick={edit}>
                  Edit
                </button>
              ) : (
                <button type="button" disabled={busy} onClick={() => void goBack(v.number)}>
                  Go back
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
      {open && status}
    </section>
  );
}

export function CustomizationPage() {
  const session = useHost().session;
  const host = session?.signed_in === true;
  const [read, setRead] = useState<Customization | null>(null);
  // Counts drafts saved, so each editor starts again from what was saved.
  const [saves, setSaves] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!host) return;
    getCustomization(true).then(
      (got) => {
        setRead(got);
        console.info(`Customization page opened: shipped=${got.shipped}`);
      },
      (e: unknown) => {
        console.error("Could not read the customization", e);
        setFailed(true);
      },
    );
  }, [host]);

  if (session === null) return <p>Loading…</p>;
  if (!host) return <HostOnlyPage />;
  return (
    <div className="host-page customization-page">
      <h1>Customization</h1>
      <p className="lead">
        Who the person in the video is, what they aim for, and how each feature answers, given to
        the LLM with every prompt.
      </p>
      {failed && (
        <p className="error">The customization could not be read. Reload to try again.</p>
      )}
      {!failed && read === null && <p className="muted busy">Loading…</p>}
      {read && (
        <>
          <GenerateSection
            now={read}
            onSaved={(saved) => {
              setRead({ ...saved, shipped: false });
              setSaves((n) => n + 1);
            }}
          />
          <HistorySection
            features={read.features}
            onRestored={(saved) => {
              setRead({ ...saved, shipped: false });
              setSaves((n) => n + 1);
            }}
          />
          <IdentitySection key={`identity-${saves}`} identity={read.identity} />
          <GoalsSection key={`goals-${saves}`} goals={read.goals} />
          {read.features.length ? (
            sections(read.features).map(([name, features]) => (
              <GuidelineSection key={`${name}-${saves}`} name={name} features={features} />
            ))
          ) : (
            <GuidelineSection name="Guidelines" features={[]} />
          )}
        </>
      )}
    </div>
  );
}
