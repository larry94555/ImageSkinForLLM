// Where each participant may go (roadmap R261, item 211), on the host's account page: for every
// participant, and for any one of them in its place, which of the host's sites they may open and
// the site they are sent to after signing in. Until the host saves one, every site is open and
// they are sent to the first.

import { useEffect, useState } from "preact/hooks";

import {
  getParticipantPolicy,
  type ParticipantPolicy,
  type ParticipantPolicyView,
  type ParticipantRule,
  putParticipantPolicy,
  ServerRefusal,
} from "./api";

const FIRST = ""; // the landing choice for "the first site they may open"

function siteName(view: ParticipantPolicyView, site: string): string {
  const found = view.sites.find((s) => s.site === site);
  return found ? found.address.replace(/^https?:\/\//, "") : site;
}

// One rule's sites and landing site. Every site ticked is kept as "every site", so a site the
// host adds later is open too.
function RuleEditor({
  view,
  label,
  rule,
  change,
  remove,
}: {
  view: ParticipantPolicyView;
  label: string;
  rule: ParticipantRule;
  change: (rule: ParticipantRule) => void;
  remove?: () => void;
}) {
  const all = view.sites.map((s) => s.site);
  const open = rule.sites ?? all;
  function toggle(site: string, on: boolean) {
    const now = all.filter((s) => (s === site ? on : open.includes(s)));
    const landing = rule.landing && now.includes(rule.landing) ? rule.landing : null;
    change({ sites: now.length === all.length ? null : now, landing });
  }
  return (
    <fieldset className="participant-rule">
      <legend>{label}</legend>
      <p className="muted">May open:</p>
      {view.sites.map((s) => (
        <label key={s.site} className="check">
          <input
            type="checkbox"
            checked={open.includes(s.site)}
            onChange={(e) => toggle(s.site, e.currentTarget.checked)}
          />
          {siteName(view, s.site)}
        </label>
      ))}
      <label>
        Sent to after signing in
        <select
          value={rule.landing ?? FIRST}
          onChange={(e) =>
            change({ ...rule, landing: e.currentTarget.value || null })
          }
        >
          <option value={FIRST}>The first site they may open</option>
          {open.map((site) => (
            <option key={site} value={site}>
              {siteName(view, site)}
            </option>
          ))}
        </select>
      </label>
      {remove && (
        <button type="button" className="secondary" onClick={remove}>
          Use the rule for every participant
        </button>
      )}
    </fieldset>
  );
}

export function ParticipantPolicyPanel() {
  const [view, setView] = useState<ParticipantPolicyView | null>(null);
  const [policy, setPolicy] = useState<ParticipantPolicy | null>(null);
  const [adding, setAdding] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getParticipantPolicy().then(
      (found) => {
        setView(found);
        setPolicy(found.policy);
      },
      (e: unknown) => {
        console.error("Could not read where participants may go", e);
        setError("Where participants may go can't be read just now.");
      },
    );
  }, []);

  if (!view || !policy) {
    // Not an alert: the rest of the account page is still usable.
    return error ? (
      <p className="muted">{error}</p>
    ) : (
      <p className="muted">Reading where participants may go…</p>
    );
  }

  function edit(next: ParticipantPolicy) {
    setPolicy(next);
    setSaved(false);
    setError(null);
  }

  function setOwn(email: string, rule: ParticipantRule | null) {
    const participants = { ...policy!.participants };
    if (rule) participants[email] = rule;
    else delete participants[email];
    edit({ ...policy!, participants });
  }

  async function save(e: Event) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const started = performance.now();
    try {
      const kept = await putParticipantPolicy(policy!);
      setView(kept);
      setPolicy(kept.policy);
      setSaved(true);
      console.info(
        `Participant policy saved (${Math.round(performance.now() - started)} ms)`,
      );
    } catch (err) {
      console.error("Could not save where participants may go", err);
      setError(
        err instanceof ServerRefusal
          ? err.message
          : "That didn't work. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const without = view.participants.filter((p) => !(p in policy.participants));
  return (
    <form
      className="participant-policy"
      aria-labelledby="participant-policy"
      onSubmit={(e) => void save(e)}
    >
      <h2 id="participant-policy">Where participants may go</h2>
      <p className="muted">
        Which of your sites your participants may open, and the site they are
        sent to after signing in. A participant can be given a rule of their
        own in place of the one for every participant.
      </p>
      <RuleEditor
        view={view}
        label="Every participant"
        rule={policy.every}
        change={(every) => edit({ ...policy, every })}
      />
      {Object.entries(policy.participants).map(([email, rule]) => (
        <RuleEditor
          key={email}
          view={view}
          label={email}
          rule={rule}
          change={(r) => setOwn(email, r)}
          remove={() => setOwn(email, null)}
        />
      ))}
      {without.length > 0 && (
        <div className="participant-add">
          <label>
            A participant
            <select
              value={adding}
              onChange={(e) => setAdding(e.currentTarget.value)}
            >
              <option value="">Choose…</option>
              {without.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="secondary"
            disabled={!adding}
            onClick={() => {
              setOwn(adding, { ...policy.every });
              setAdding("");
            }}
          >
            Give them a rule of their own
          </button>
        </div>
      )}
      <button type="submit" disabled={busy}>
        Save
      </button>
      {saved && (
        <p className="muted" role="status">
          Saved. It applies the next time a participant signs in.
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
