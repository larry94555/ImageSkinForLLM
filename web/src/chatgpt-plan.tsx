// Sign in with ChatGPT on the Settings page (roadmap R43, item 29). OpenAI lets an open-source
// app running on the user's own machine use their ChatGPT plan instead of an API key. Signing in
// is a plain link: the server sends the browser to OpenAI, which sends it back to Settings. The
// page is only told which account is connected; the tokens stay on the server. Signing in again
// uses the account the app is registered to; "Use another ChatGPT account" registers it anew, and
// "Allow use of my plan" asks again after a sign-in that didn't allow it.

import { useEffect, useState } from "preact/hooks";

import { type ChatGptStatus, getChatGpt, signOutChatGpt } from "./api";

export function ChatGptPlanSection() {
  const [status, setStatus] = useState<ChatGptStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unconfirmed, setUnconfirmed] = useState(false);

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
    setUnconfirmed(false);
    const started = performance.now();
    try {
      const now = await signOutChatGpt();
      setStatus(now);
      setUnconfirmed(now.revoked === false);
      const confirmed = now.revoked === false ? ", not confirmed by ChatGPT" : "";
      console.info(`Disconnected ChatGPT (${Math.round(performance.now() - started)} ms${confirmed})`);
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
        <>
          <p>
            <a className="button" href="/api/chatgpt/sign-in">
              Continue with ChatGPT
            </a>
          </p>
          {status.registered_email && (
            <p className="muted">
              Signs in again as {status.registered_email}.{" "}
              <a href="/api/chatgpt/sign-in?another=true">Use another ChatGPT account</a>
            </p>
          )}
        </>
      )}
      {status?.connected && (
        <>
          <p>
            Connected as <strong>{status.email || status.name || "your ChatGPT account"}</strong>
          </p>
          {!status.plan_usage && (
            <p>
              <span className="error">Using your plan wasn't allowed when you signed in.</span>{" "}
              <a href="/api/chatgpt/sign-in?consent=true">Allow use of my plan</a>
            </p>
          )}
          <button type="button" disabled={busy} onClick={() => void disconnect()}>
            {busy ? "Disconnecting…" : "Disconnect"}
          </button>
        </>
      )}
      {unconfirmed && (
        <p className="error" role="alert">
          Disconnected here, but ChatGPT didn't confirm it ended the sign-in. To be sure, remove
          ImageSkinForLLM from the connected apps in your ChatGPT settings.
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
