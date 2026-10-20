// Sign in with ChatGPT on the Settings page (roadmap R43, item 29). OpenAI lets an open-source
// app running on the user's own machine use their ChatGPT plan instead of an API key. Signing in
// is a plain link: the server sends the browser to OpenAI, which sends it back to Settings. The
// page is only told which account is connected; the tokens stay on the server. Signing in again
// uses the account the app is registered to; "Use another ChatGPT account" registers it anew, and
// "Allow use of my plan" asks again after a sign-in that didn't allow it. Each account keeps its
// own tokens, so the other accounts are listed in both views: one still connected is switched to
// with no sign-in, the rest sign in again.

import { useEffect, useState } from "preact/hooks";

import {
  CHATGPT_ACCOUNT_CHANGED,
  type ChatGptStatus,
  getChatGpt,
  signOutChatGpt,
  useChatGptAccount,
} from "./api";

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
      window.dispatchEvent(new Event(CHATGPT_ACCOUNT_CHANGED));
      setUnconfirmed(now.revoked === false);
      const confirmed = now.revoked === false ? ", not confirmed by ChatGPT" : "";
      console.info(`Disconnected ChatGPT (${Math.round(performance.now() - started)} ms${confirmed})`);
    } catch (e) {
      console.error("Could not disconnect ChatGPT", e);
      setError("ChatGPT could not be disconnected. Try again.");
    }
    setBusy(false);
  }

  async function switchTo(account: string) {
    setBusy(true);
    setError(null);
    setUnconfirmed(false);
    try {
      const now = await useChatGptAccount(account);
      setStatus(now);
      window.dispatchEvent(new Event(CHATGPT_ACCOUNT_CHANGED));
      console.info(`Switched ChatGPT account (${now.connected ? "connected" : "not connected"})`);
    } catch (e) {
      console.error("Could not switch the ChatGPT account", e);
      setError("The ChatGPT account could not be switched. Reload the page to try again.");
    }
    setBusy(false);
  }

  const others = status?.accounts ?? [];

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
              Signs in again as {status.label || status.registered_email}.{" "}
              <a href="/api/chatgpt/sign-in?another=true">Use another ChatGPT account</a>
            </p>
          )}
        </>
      )}
      {status?.connected && (
        <>
          <p>
            Connected as{" "}
            <strong>{status.label || status.email || status.name || "your ChatGPT account"}</strong>
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
      {others.length > 0 && (
        <p className="muted">
          {status?.connected ? "Other accounts:" : "Or sign in as"}{" "}
          {others.map((a, i) => (
            <span key={a.id}>
              {i > 0 && ", "}
              {a.connected ? (
                <button
                  type="button"
                  className="link"
                  disabled={busy}
                  onClick={() => void switchTo(a.id)}
                >
                  Switch to {a.label || a.email || "an earlier account"}
                </button>
              ) : (
                <a href={`/api/chatgpt/sign-in?account=${encodeURIComponent(a.id)}`}>
                  {a.label || a.email || "an earlier account"}
                </a>
              )}
            </span>
          ))}
        </p>
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
