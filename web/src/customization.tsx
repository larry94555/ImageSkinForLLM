// The Customization page (roadmap R92 and R94, items 85 and 87): the AI's identity, its goals and
// each feature's guidelines, which the LLM is given with every prompt, edited and saved by a
// signed-in host. A save is used from the next prompt.

import { useEffect, useState } from "preact/hooks";

import {
  type Customization,
  type GuidelineFeature,
  getCustomization,
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

export function CustomizationPage() {
  const session = useHost().session;
  const host = session?.signed_in === true;
  const [read, setRead] = useState<Customization | null>(null);
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
          <IdentitySection identity={read.identity} />
          <GoalsSection goals={read.goals} />
          {read.features.length ? (
            sections(read.features).map(([name, features]) => (
              <GuidelineSection key={name} name={name} features={features} />
            ))
          ) : (
            <GuidelineSection name="Guidelines" features={[]} />
          )}
        </>
      )}
    </div>
  );
}
