// Sign in with ChatGPT on the Settings page (roadmap R43, item 29). OpenAI lets an open-source
// app running on the user's own machine use their ChatGPT plan instead of an API key. Signing in
// is a plain link: the server sends the browser to OpenAI, which sends it back to Settings. The
// page is only told which account is connected; the tokens stay on the server.

import { useEffect, useState } from "preact/hooks";

import { type ChatGptStatus, getChatGpt, signOutChatGpt } from "./api";

export function ChatGptPlanSection() {
  const [status, setStatus] = useState<ChatGptStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getChatGpt()
      .then((read) => {
        setStatus(read);
        console.info(`ChatGPT sign-in: ${read.connected ? "connected" : "not connected"}`);
      })
      .catch((e: unknown) => {
        console.error("Could not read the ChatGPT sign-in", e);
        setError("The ChatGPT sign-in could not be read. Reload the page to try again.");
      });
  }, []);

  async function disconnect() {
    setBusy(true);
    setError(null);
    const started = performance.now();
    try {
      setStatus(await signOutChatGpt());
      console.info(`Disconnected ChatGPT (${Math.round(performance.now() - started)} ms)`);
    } catch (e) {
      console.error("Could not disconnect ChatGPT", e);
      setError("ChatGPT could not be disconnected. Try again.");
    }
    setBusy(false);
  }

  return (
    <section className="panel chatgpt-plan" aria-labelledby="settings-chatgpt">
      <h2 id="settings-chatgpt">ChatGPT plan</h2>
      <p className="muted">
        Sign in with your ChatGPT account to use your ChatGPT Plus or Pro plan instead of an
        API key, while the app runs on your own computer.
      </p>
      {status && !status.connected && (
        <a className="button" href="/api/chatgpt/sign-in">
          Continue with ChatGPT
        </a>
      )}
      {status?.connected && (
        <>
          <p>
            Connected as <strong>{status.email || status.name || "your ChatGPT account"}</strong>
          </p>
          {!status.plan_usage && (
            <p className="error">
              Using your plan wasn't allowed when you signed in. Disconnect and sign in again to
              allow it.
            </p>
          )}
          <button type="button" disabled={busy} onClick={() => void disconnect()}>
            {busy ? "Disconnecting…" : "Disconnect"}
          </button>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
