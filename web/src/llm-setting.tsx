// The LLM setting on the Settings page (roadmap R42, item 29): local llama.cpp, or Claude, OpenAI,
// Grok or OpenRouter with the user's own API key. The key is sent to the server once and kept
// there: the page is only told that a provider has one.

import { useEffect, useState } from "preact/hooks";

import { chooseLlm, getLlm, type LlmProvider, type LlmSetting, ServerRefusal } from "./api";

export function LlmSettingSection() {
  const [setting, setSetting] = useState<LlmSetting | null>(null);
  const [picked, setPicked] = useState("local");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getLlm()
      .then((read) => {
        if (!Array.isArray(read.providers)) throw new Error("The LLM setting has no providers");
        setSetting(read);
        pick(read.provider, read);
      })
      .catch((e: unknown) => {
        console.error("Could not read the LLM setting", e);
        setError("The LLM setting could not be read. Reload the page to try again.");
      });
  }, []);

  function pick(id: string, from: LlmSetting | null = setting) {
    setPicked(id);
    setKey("");
    setModel(from?.providers.find((p) => p.id === id)?.model ?? "");
    setSaved(false);
  }

  async function use() {
    setSaving(true);
    setError(null);
    setSaved(false);
    const started = performance.now();
    try {
      const local = picked === "local";
      const now = await chooseLlm({
        provider: picked,
        ...(key.trim() && !local ? { api_key: key.trim() } : {}),
        ...(local ? {} : { model }),
      });
      console.info(`LLM changed to ${picked} (${Math.round(performance.now() - started)} ms)`);
      setSetting(now);
      setKey("");
      setSaved(true);
    } catch (e) {
      console.error(`Could not change the LLM to ${picked}`, e);
      setError(e instanceof ServerRefusal ? e.message : "The LLM could not be changed. Try again.");
    }
    setSaving(false);
  }

  const current = setting?.providers.find((p) => p.id === setting.provider);
  const chosen: LlmProvider | undefined = setting?.providers.find((p) => p.id === picked);

  return (
    <section className="panel llm-setting" aria-labelledby="settings-llm">
      <h2 id="settings-llm">LLM</h2>
      <p className="muted">
        Who writes the replies. A provider other than the local model needs your own API key,
        which is kept on the app's server and never shown again.
      </p>
      {current && (
        <p className="current-llm">
          Answering now: <strong>{current.label}</strong>
        </p>
      )}
      {setting && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void use();
          }}
        >
          <fieldset disabled={saving}>
            <legend className="sr-only">LLM</legend>
            {setting.providers.map((p) => (
              <label key={p.id} className="choice">
                <input
                  type="radio"
                  name="llm"
                  value={p.id}
                  checked={picked === p.id}
                  onChange={() => pick(p.id)}
                />{" "}
                <span>
                  {p.label}
                  {p.id !== "local" && (
                    <span className="muted"> · {p.has_key ? "key saved" : "needs a key"}</span>
                  )}
                </span>
              </label>
            ))}
          </fieldset>
          {chosen && chosen.id !== "local" && (
            <div className="llm-fields">
              <label>
                API key
                <input
                  type="password"
                  autoComplete="off"
                  value={key}
                  placeholder={chosen.has_key ? "Saved. Paste a new key to replace it." : `From ${chosen.keys_at}`}
                  onInput={(e) => setKey((e.target as HTMLInputElement).value)}
                  disabled={saving}
                />
              </label>
              <label>
                Model
                <input
                  type="text"
                  value={model}
                  placeholder={chosen.default_model}
                  onInput={(e) => setModel((e.target as HTMLInputElement).value)}
                  disabled={saving}
                />
              </label>
              <p className="muted">Leave the model blank for {chosen.default_model}.</p>
            </div>
          )}
          <button type="submit" className="use" disabled={saving}>
            {saving ? "Saving…" : "Use this LLM"}
          </button>
        </form>
      )}
      {saved && current && <p className="muted">Saved. {current.label} answers from the next prompt.</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
