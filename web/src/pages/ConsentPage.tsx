import { type FormEvent, useState } from "react";

import { confirmConsent } from "../api";

export function ConsentPage({ onConfirmed }: { onConfirmed: () => void }) {
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  async function submit(event: FormEvent) {
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
            onChange={(e) => setChecked(e.target.checked)}
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
