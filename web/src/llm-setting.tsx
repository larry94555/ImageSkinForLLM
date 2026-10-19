// The LLM setting on the Settings page (roadmap R42, item 29): local llama.cpp, or Claude, OpenAI,
// Grok or OpenRouter with the user's own API key. The key is sent to the server once and kept
// there: the page is only told that a provider has one. The Model box offers the models the
// provider lists for the key, looked up live, since a fixed list goes out of date; any name can
// still be typed.

import { useEffect, useRef, useState } from "preact/hooks";

import {
  chooseLlm,
  getLlm,
  listModels,
  type LlmProvider,
  type LlmSetting,
  ServerRefusal,
} from "./api";

// The provider's models: being looked up, listed, or why they couldn't be.
type Models = { state: "loading" } | { state: "listed"; ids: string[] } | { state: "failed"; error: string };

export function LlmSettingSection() {
  const [setting, setSetting] = useState<LlmSetting | null>(null);
  const [picked, setPicked] = useState("local");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [models, setModels] = useState<Models | null>(null);
  const asking = useRef(""); // the provider whose models were asked for last

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
    const provider = from?.providers.find((p) => p.id === id);
    setPicked(id);
    setKey("");
    setModel(provider?.model ?? "");
    setSaved(false);
    setModels(null);
    asking.current = id;
    if (provider?.has_key) void lookUp(id);
  }

  // Asks the provider which models the key can use. A late answer for a provider no longer
  // picked is dropped.
  async function lookUp(id: string, typedKey?: string) {
    asking.current = id;
    setModels({ state: "loading" });
    const started = performance.now();
    try {
      const ids = await listModels(id, typedKey);
      if (asking.current !== id) return;
      console.info(`Listed ${ids.length} models for ${id} (${Math.round(performance.now() - started)} ms)`);
      setModels({ state: "listed", ids });
    } catch (e) {
      if (asking.current !== id) return;
      console.error(`Could not list the models for ${id}`, e);
      const error = e instanceof ServerRefusal ? e.message : "The models couldn't be listed.";
      setModels({ state: "failed", error });
    }
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
                  onBlur={() => key.trim() && void lookUp(chosen.id, key.trim())}
                  disabled={saving}
                />
              </label>
              <label>
                Model
                <input
                  type="text"
                  list="llm-models"
                  value={model}
                  placeholder={chosen.default_model}
                  onInput={(e) => setModel((e.target as HTMLInputElement).value)}
                  disabled={saving}
                />
              </label>
              {models?.state === "listed" && (
                <datalist id="llm-models">
                  {models.ids.map((id) => (
                    <option key={id} value={id} />
                  ))}
                </datalist>
              )}
              <p className="muted">{modelsNote(models, model || chosen.default_model, chosen)}</p>
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

// What the line under the Model box says about the provider's models.
export function modelsNote(models: Models | null, model: string, provider: LlmProvider): string {
  const blank = `Leave the model blank for ${provider.default_model}.`;
  if (models === null) return `${blank} Enter the key to see ${provider.label}'s models.`;
  if (models.state === "loading") return `Looking up ${provider.label}'s models…`;
  if (models.state === "failed") return `${models.error} You can still type a model's name.`;
  const n = models.ids.length;
  const listed = `${n} model${n === 1 ? "" : "s"} available: pick one or type a name.`;
  if (!models.ids.includes(model)) return `${listed} ${model} isn't in ${provider.label}'s list for this key.`;
  return `${listed} ${blank}`;
}
