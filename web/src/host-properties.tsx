// Host properties in Admin settings (roadmap R241, item 195): every host, by email, with a search
// box that narrows the list as it is typed to the emails containing the text anywhere in them,
// ignoring capitals. The server does the matching. Selecting a host shows their own Allow and Deny
// of a custom image and sound (R242), over Admin settings' checkboxes.

import { useEffect, useState } from "preact/hooks";

import { useAdmin } from "./admin";
import {
  type CustomKind,
  getAdminHosts,
  getHostChoices,
  type HostChoice,
  type HostChoices,
  saveHostChoice,
  ServerRefusal,
} from "./api";

// What the server answered, and the search it answered: only the answer for what is in the box
// now is shown (Codex's review of PR #267), so while a new search is read, the last one's list or
// message isn't shown under it.
type Answer = { query: string; hosts: string[] } | { query: string; error: string };

export function HostProperties() {
  const { refresh } = useAdmin();
  const [search, setSearch] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const query = search.trim();

  useEffect(() => {
    // Only the answer for what is in the box now is kept, so a slow one can't replace it.
    let active = true;
    const started = performance.now();
    getAdminHosts(query).then(
      (found) => {
        if (!active) return;
        console.info(`Host list: ${found.length} shown (${Math.round(performance.now() - started)} ms)`);
        setAnswer({ query, hosts: found });
      },
      (e: unknown) => {
        if (!active) return;
        console.error("Could not read the hosts", e);
        if (e instanceof ServerRefusal && e.status === 401) return void refresh();
        const error = e instanceof ServerRefusal ? e.message : "The hosts could not be read. Try again.";
        setAnswer({ query, error });
      },
    );
    return () => {
      active = false;
    };
  }, [query]);

  const current = answer?.query === query ? answer : null;
  return (
    <section className="panel" aria-labelledby="host-properties">
      <h2 id="host-properties">Host properties</h2>
      <label className="host-search">
        <span>Search hosts by email</span>
        <input
          type="search"
          value={search}
          placeholder="Any part of the email"
          onInput={(e) => setSearch(e.currentTarget.value)}
        />
      </label>
      {current === null && <p className="muted">{query ? "Searching…" : "Reading the hosts…"}</p>}
      {current && "error" in current && <p className="error">{current.error}</p>}
      {current && "hosts" in current && current.hosts.length === 0 && (
        <p className="muted">{query ? "No host's email contains that." : "No host has signed up yet."}</p>
      )}
      {current && "hosts" in current && current.hosts.length > 0 && (
        <ul className="host-list" aria-label="Hosts">
          {current.hosts.map((email) => (
            <li key={email}>
              <button
                type="button"
                className={email === selected ? "host-pick picked" : "host-pick"}
                aria-pressed={email === selected}
                onClick={() => {
                  console.info("Host selected in Host properties");
                  setSelected(email === selected ? null : email);
                }}
              >
                {email}
              </button>
              {/* Keyed by the host, so one host's answer is never shown for another. */}
              {email === selected && <HostChoicesPanel key={email} email={email} />}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const KINDS: { kind: CustomKind; label: string }[] = [
  { kind: "custom_image", label: "Custom Image" },
  { kind: "custom_voice", label: "Custom Sound" },
];

// The selected host's Allow and Deny (R242). Allow and Deny of the same thing can't both be
// chosen: choosing one clears the other, and choosing it again clears it, back to the default.
// Each choice is saved at once and used from the host's next page.
function HostChoicesPanel({ email }: { email: string }) {
  const { refresh } = useAdmin();
  const [choices, setChoices] = useState<HostChoices | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function failed(e: unknown, what: string) {
    console.error(what, e);
    if (e instanceof ServerRefusal && e.status === 401) return void refresh();
    setError(e instanceof ServerRefusal ? e.message : "That didn't work. Try again.");
  }

  useEffect(() => {
    getHostChoices(email).then(setChoices, (e: unknown) => failed(e, "Could not read the host's properties"));
  }, [email]);

  async function choose(kind: CustomKind, choice: "allow" | "deny") {
    if (!choices) return;
    const next: HostChoice = choices[kind] === choice ? null : choice;
    setBusy(true);
    setError(null);
    const started = performance.now();
    try {
      setChoices(await saveHostChoice(email, kind, next));
      console.info(`Host properties changed: ${kind} ${next ?? "default"} (${Math.round(performance.now() - started)} ms)`);
    } catch (e) {
      failed(e, "Could not change the host's properties");
    } finally {
      setBusy(false);
    }
  }

  if (!choices) {
    return error ? <p className="error">{error}</p> : <p className="muted">Reading {email}…</p>;
  }
  return (
    <div className="host-choices" aria-label={`Properties of ${email}`} role="group">
      {KINDS.map(({ kind, label }) => (
        <div key={kind} className="host-choice">
          {(["allow", "deny"] as const).map((choice) => (
            <button
              key={choice}
              type="button"
              className={choices[kind] === choice ? "choice chosen" : "choice"}
              aria-pressed={choices[kind] === choice}
              disabled={busy}
              onClick={() => void choose(kind, choice)}
            >
              {choice === "allow" ? "Allow" : "Deny"} {label}
            </button>
          ))}
          <span className="muted">
            Default: {choices.default[kind]}
          </span>
        </div>
      ))}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
