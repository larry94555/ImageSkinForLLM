// The app's pages. Each one is a function that returns what the page shows.

import { useState } from "preact/hooks";

import { confirmConsent } from "./api";

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

export function SetupPage() {
  return (
    <>
      <h1>Setup</h1>
      <p className="done">Thank you, consent is confirmed.</p>
      <p>Uploading photos and recordings comes in the next version.</p>
    </>
  );
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
