// Admin settings, the admin view's second page (roadmap R155, items 123 and 125): the minutes
// without activity before the administrator is signed out, and the thresholds for the resource
// dashboard's colours, as the percentage of a resource remaining, and, under Hosts, whether hosts
// may use a custom image and a custom voice (R239); then Host properties, every host by email
// (R241), and the test email for test accounts, set only in the file (R264). Only the administrator sees them; they apply at once, to the sign-in going now, to the
// dashboard and to each host's next request.

import { useEffect, useState } from "preact/hooks";

import { useAdmin } from "./admin";
import { type AdminSettings, getAdminSettings, saveAdminSettings, ServerRefusal } from "./api";
import { MEANINGS } from "./dashboard";
import { HostProperties } from "./host-properties";

type Fields = {
  minutes: string;
  blue: string;
  orange: string;
  red: string;
  noImage: boolean;
  noVoice: boolean;
  days: string;
};

function fieldsOf(settings: AdminSettings): Fields {
  const t = settings.thresholds;
  return {
    minutes: String(settings.timeout_minutes),
    blue: String(t.blue_above),
    orange: String(t.orange_below),
    red: String(t.red_below),
    noImage: settings.disable_custom_image,
    noVoice: settings.disable_custom_voice,
    days: String(settings.days_before_deleting),
  };
}

export function AdminSettingsPage() {
  const { refresh } = useAdmin();
  const [settings, setSettings] = useState<AdminSettings | null>(null);
  const [fields, setFields] = useState<Fields | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAdminSettings()
      .then((read) => {
        console.info("Admin settings shown");
        setSettings(read);
        setFields(fieldsOf(read));
      })
      .catch(async (e: unknown) => {
        console.error("Could not read the admin settings", e);
        if (e instanceof ServerRefusal && e.status === 401) return refresh();
        setError("The admin settings could not be read. Reload the page to try again.");
      });
  }, []);

  async function save(changes: Fields) {
    setBusy(true);
    setError(null);
    setSaved(false);
    const started = performance.now();
    try {
      const read = await saveAdminSettings({
        timeout_minutes: Number(changes.minutes),
        thresholds: {
          blue_above: Number(changes.blue),
          orange_below: Number(changes.orange),
          red_below: Number(changes.red),
        },
        disable_custom_image: changes.noImage,
        disable_custom_voice: changes.noVoice,
        days_before_deleting: Number(changes.days),
      });
      console.info(`Admin settings saved (${Math.round(performance.now() - started)} ms)`);
      setSettings(read);
      setFields(fieldsOf(read));
      setSaved(true);
      await refresh(); // the minutes shown on the Settings page and in the sign-out notice
    } catch (e) {
      console.error("Could not save the admin settings", e);
      if (e instanceof ServerRefusal && e.status === 401) {
        await refresh();
        return;
      }
      setError(e instanceof ServerRefusal ? e.message : "Could not save. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!settings || !fields) {
    return error ? <p className="error">{error}</p> : <p className="muted">Reading the admin settings…</p>;
  }

  const input = (
    name: "minutes" | "blue" | "orange" | "red" | "days",
    label: string,
    min: number,
    max: number,
  ) => (
    <label className="admin-number">
      <span>{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        step={name === "minutes" || name === "days" ? 1 : "any"}
        value={fields[name]}
        onInput={(e) => {
          setSaved(false);
          setFields({ ...fields, [name]: e.currentTarget.value });
        }}
      />
    </label>
  );
  const recommended = settings.recommended.thresholds;
  const checkbox = (name: "noImage" | "noVoice", label: string) => (
    <label className="check">
      <input
        type="checkbox"
        checked={fields[name]}
        onChange={(e) => {
          setSaved(false);
          setFields({ ...fields, [name]: e.currentTarget.checked });
        }}
      />{" "}
      {label}
    </label>
  );

  return (
    <>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save(fields);
        }}
      >
        {error && <p className="error">{error}</p>}
        {saved && (
          <p className="notice" role="status">
            Saved. The dashboard, the sign-out and the hosts use them now.
          </p>
        )}
        <section className="panel" aria-labelledby="admin-sign-out">
          <h2 id="admin-sign-out">Automatic sign-out</h2>
          <p className="muted">
            The administrator is signed out after this many minutes without a click or key press in
            the admin view or on the Settings page. Recommended: {settings.recommended.timeout_minutes}.
          </p>
          {input("minutes", "Minutes without activity (5 to 240)", 5, 240)}
        </section>
        <section className="panel" aria-labelledby="admin-thresholds">
          <h2 id="admin-thresholds">Colours on the dashboard</h2>
          <p className="muted">
            As the percentage of a resource remaining, for every resource. Green is between orange
            and blue. Recommended: blue above {recommended.blue_above}%, orange below{" "}
            {recommended.orange_below}%, red below {recommended.red_below}%.
          </p>
          {input("blue", "Blue: more than this % remaining", 1, 99)}
          {input("orange", "Orange: less than this % remaining", 1, 99)}
          {input("red", "Red: less than this % remaining", 1, 99)}
          {MEANINGS.map(([colour, meaning, todo]) => (
            <p key={colour} className="colour-key">
              <span className={`colour-name ${colour}`}>{colour[0].toUpperCase() + colour.slice(1)}</span>:{" "}
              {meaning}. {todo}
            </p>
          ))}
          <p>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              // Only the thresholds: the minutes as typed, saved or not, stay (Codex's review).
              onClick={() =>
                void save({
                  ...fields,
                  blue: String(recommended.blue_above),
                  orange: String(recommended.orange_below),
                  red: String(recommended.red_below),
                })
              }
            >
              Use the recommended thresholds
            </button>
          </p>
        </section>
        <section className="panel" aria-labelledby="admin-hosts">
          <h2 id="admin-hosts">Hosts</h2>
          <p className="muted">
            Checked, hosts use a default person and a ready-made voice, and can't add their own photo
            or record their own voice. Both are checked to begin with.
          </p>
          <p>{checkbox("noImage", "Disable custom image")}</p>
          <p>{checkbox("noVoice", "Disable custom voice")}</p>
        </section>
        <section className="panel" aria-labelledby="admin-deleting">
          <h2 id="admin-deleting">Deleting paused sites</h2>
          <p className="muted">
            A site paused because its subscription ended, its trial was cancelled or its host
            asked to delete it keeps its content this many days, so its host can come back, then
            everything on it is deleted. Recommended: {settings.recommended.days_before_deleting}.
          </p>
          {input("days", "Days before deleting (1 to 365)", 1, 365)}
        </section>
        <p>
          <button type="submit" disabled={busy}>
            Save
          </button>
        </p>
      </form>
      <TestEmail address={settings.test_email} />
      {/* Not part of the form: the list is only read here, and Save doesn't touch it (R241). */}
      <HostProperties />
    </>
  );
}

// The test email (R264): only shown, as it is set in the file on the host, never here.
function TestEmail({ address }: { address: string }) {
  return (
    <section className="panel" aria-labelledby="admin-test-email">
      <h2 id="admin-test-email">Test email</h2>
      <p>
        Test email: <strong>{address || "not set"}</strong>
      </p>
      <p className="muted">
        Every email for an administrator's test account goes to this address. It is set only in
        admin-settings.json, in the admin folder on the host, as "test_email", and is used as soon
        as the file is saved.
      </p>
    </section>
  );
}
