// Admin guidelines, the admin view's third page (roadmap R244, items 197 and 198): the
// administrator's own identity, goals and guidelines for each feature, laid out as the host's
// Customization page is (R94). The LLM follows them first, over every host's (R243). Each part has
// its own Save and Clear; a save sends them whole, with only that part changed from what was last
// saved, so text typed in another part and not saved stays as typed.

import { useEffect, useRef, useState } from "preact/hooks";

import { useAdmin } from "./admin";
import {
  type AdminGuidelineFeature,
  type AdminGuidelines,
  type AdminGuidelinesEdit,
  getAdminGuidelines,
  saveAdminGuidelines,
  ServerRefusal,
} from "./api";

type Identity = AdminGuidelines["identity"];
type Save = (part: string, change: Partial<AdminGuidelinesEdit>) => Promise<AdminGuidelines | null>;

const IDENTITY: [keyof Identity, string][] = [
  ["name", "Name"],
  ["speaks_as", "Speaks as"],
  ["purpose", "Purpose"],
  ["audience", "Who it is for"],
  ["helps_with", "What it can help with"],
];

const SAVED = "Saved. It is followed first from the next prompt, for every host.";
const CLEARED = "Cleared. The host's are followed alone from the next prompt.";

function editOf(read: AdminGuidelines): AdminGuidelinesEdit {
  return { identity: read.identity, goals: read.goals, guidelines: read.guidelines };
}

// Saving one part: whether it is being saved, and what to say after. Its editors are read-only
// while it saves, as what comes back replaces them.
function usePart(save: Save) {
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);

  async function run(part: string, change: Partial<AdminGuidelinesEdit>, done = SAVED) {
    setBusy(true);
    setSaid(null);
    const saved = await save(part, change);
    setBusy(false);
    setSaid(saved ? done : null);
    return saved;
  }

  const status = said && (
    <p className="notice" role="status">
      {said}
    </p>
  );
  return { busy, run, status, changed: () => setSaid(null) };
}

function Buttons({ busy, part, empty, onClear }: { busy: boolean; part?: string; empty: boolean; onClear: () => void }) {
  return (
    <p>
      <button type="submit" disabled={busy}>
        {part ? `Save ${part}` : "Save"}
      </button>{" "}
      <button type="button" className="secondary" disabled={busy || empty} onClick={onClear}>
        {part ? `Clear ${part}` : "Clear"}
      </button>
    </p>
  );
}

function IdentitySection({ identity, save }: { identity: Identity; save: Save }) {
  const [fields, setFields] = useState(identity);
  const [kept, setKept] = useState(identity);
  const { busy, run, status, changed } = usePart(save);
  const blank = Object.fromEntries(IDENTITY.map(([k]) => [k, ""])) as Identity;

  function put(value: Identity, done?: string) {
    void run("identity", { identity: value }, done).then((saved) => {
      if (saved) {
        setFields(saved.identity);
        setKept(saved.identity);
      }
    });
  }

  return (
    <section className="panel" aria-labelledby="admin-guidelines-identity">
      <h2 id="admin-guidelines-identity">Identity</h2>
      <p className="muted">
        Told to the LLM before the host's identity. "Who are you?" is still answered from the
        host's.
      </p>
      <form
        className="customization-edit"
        onSubmit={(e) => {
          e.preventDefault();
          put(fields);
        }}
      >
        {IDENTITY.map(([key, label]) => (
          <label key={key}>
            <span>{label}</span>
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
        <Buttons
          busy={busy}
          part="the identity"
          empty={!Object.values(kept).some(Boolean)}
          onClear={() => put(blank, CLEARED)}
        />
      </form>
    </section>
  );
}

function GoalsSection({ goals, save }: { goals: string[]; save: Save }) {
  const [text, setText] = useState(goals.join("\n"));
  const [kept, setKept] = useState(goals);
  const { busy, run, status, changed } = usePart(save);

  function put(value: string[], done?: string) {
    void run("goals", { goals: value }, done).then((saved) => {
      if (saved) {
        setText(saved.goals.join("\n"));
        setKept(saved.goals);
      }
    });
  }

  return (
    <section className="panel" aria-labelledby="admin-guidelines-goals">
      <h2 id="admin-guidelines-goals">Goals</h2>
      <p className="muted">What every reply aims for first, one goal on each line.</p>
      <form
        className="customization-edit"
        onSubmit={(e) => {
          e.preventDefault();
          put(text.split("\n"));
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
        <Buttons busy={busy} part="the goals" empty={kept.length === 0} onClear={() => put([], CLEARED)} />
      </form>
    </section>
  );
}

function FeatureGuidelines({ feature, save }: { feature: AdminGuidelineFeature; save: Save }) {
  const [text, setText] = useState(feature.text);
  const [kept, setKept] = useState(feature.text);
  const { busy, run, status, changed } = usePart(save);

  function put(value: string, done?: string) {
    void run(`guidelines ${feature.key}`, { guidelines: { [feature.key]: value } }, done).then((saved) => {
      if (saved) {
        const now = saved.guidelines[feature.key] ?? "";
        setText(now);
        setKept(now);
      }
    });
  }

  return (
    <form
      className="customization-edit guideline"
      aria-label={feature.label}
      onSubmit={(e) => {
        e.preventDefault();
        put(text);
      }}
    >
      <label>
        <span>
          {feature.label}
          {!kept && <span className="muted"> · none</span>}
        </span>
        <textarea
          rows={3}
          value={text}
          readOnly={busy}
          onInput={(e) => {
            changed();
            setText(e.currentTarget.value);
          }}
        />
      </label>
      <p className="muted">{feature.changes}</p>
      {status}
      <Buttons busy={busy} empty={!kept} onClear={() => put("", CLEARED)} />
    </form>
  );
}

// The features in the sections the Customization page shows them in, in the order each first
// comes.
function sections(features: AdminGuidelineFeature[]): [string, AdminGuidelineFeature[]][] {
  const grouped = new Map<string, AdminGuidelineFeature[]>();
  for (const f of features) grouped.set(f.section, [...(grouped.get(f.section) ?? []), f]);
  return [...grouped.entries()];
}

export function AdminGuidelinesPage() {
  const { refresh } = useAdmin();
  const [read, setRead] = useState<AdminGuidelines | null>(null);
  const [error, setError] = useState<string | null>(null);
  // What was last saved, so saves made one after another each start from the one before.
  const last = useRef<AdminGuidelines | null>(null);

  useEffect(() => {
    const started = performance.now();
    getAdminGuidelines()
      .then((got) => {
        console.info(`Admin guidelines shown (${Math.round(performance.now() - started)} ms)`);
        last.current = got;
        setRead(got);
      })
      .catch(async (e: unknown) => {
        console.error("Could not read the admin guidelines", e);
        if (e instanceof ServerRefusal && e.status === 401) return refresh();
        setError("The admin guidelines could not be read. Reload the page to try again.");
      });
  }, []);

  // Only `change` differs from what was last saved, so another part's unsaved text isn't sent.
  // Merged with the guidelines last saved, as a feature's save changes only its own.
  const save: Save = async (part, change) => {
    if (!last.current) return null;
    setError(null);
    const started = performance.now();
    const before = editOf(last.current);
    try {
      const saved = await saveAdminGuidelines({
        ...before,
        ...change,
        guidelines: { ...before.guidelines, ...change.guidelines },
      });
      last.current = saved;
      console.info(`Admin guidelines saved: ${part} (${Math.round(performance.now() - started)} ms)`);
      setRead(saved);
      return saved;
    } catch (e) {
      console.error(`Could not save the admin guidelines: ${part}`, e);
      if (e instanceof ServerRefusal && e.status === 401) {
        await refresh();
        return null;
      }
      setError(e instanceof ServerRefusal ? e.message : "Could not save. Try again.");
      return null;
    }
  };

  if (!read) {
    return error ? <p className="error">{error}</p> : <p className="muted busy">Reading the admin guidelines…</p>;
  }
  return (
    <div className="admin-guidelines">
      <p className="notice">
        These come first, over every host's: the LLM follows them first, and a host's identity,
        goals and guidelines only where they don't conflict. Hosts can't see or change them. Empty
        parts add nothing.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <IdentitySection identity={read.identity} save={save} />
      <GoalsSection goals={read.goals} save={save} />
      {sections(read.features).map(([name, features]) => (
        <section key={name} className="panel" aria-labelledby={`admin-guidelines-${name.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
          <h2 id={`admin-guidelines-${name.toLowerCase().replace(/[^a-z]+/g, "-")}`}>{name}</h2>
          {features.map((f) => (
            <FeatureGuidelines key={f.key} feature={f} save={save} />
          ))}
        </section>
      ))}
    </div>
  );
}
