// The LLM setting on the Settings page (roadmap R42, item 29): local llama.cpp, or Claude, OpenAI,
// Grok or OpenRouter with the user's own API key. The key is sent to the server once and kept
// there: the page is only told that a provider has one. The Model box offers the models the
// provider lists for the key, looked up live, since a fixed list goes out of date; any name can
// still be typed. Listing them is also how a key is checked: the server refuses to save a key
// the provider refuses. OpenRouter lists its models for anyone, so its list shows at once; for
// the others the Model box shows only once a key works (Larry, 2026-10-19), or when the provider
// can't be reached to check it.

import { useEffect, useRef, useState } from "preact/hooks";

import {
  chooseLlm,
  getLlm,
  listModels,
  type LlmProvider,
  type LlmSetting,
  ServerRefusal,
} from "./api";

// The provider's models: being looked up, listed (`checked` when a key was asked with), or why
// they couldn't be (`unreachable` when the provider couldn't be asked, rather than refusing).
type Models =
  | { state: "loading" }
  | { state: "listed"; ids: string[]; checked: boolean }
  | { state: "failed"; error: string; unreachable: boolean };

export function LlmSettingSection() {
  const [setting, setSetting] = useState<LlmSetting | null>(null);
  const [picked, setPicked] = useState("local");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [models, setModels] = useState<Models | null>(null);
  const asking = useRef(0); // which look-up was asked for last; only its answer is shown

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
    setError(null);
    setModels(null);
    asking.current += 1; // a look-up for the provider picked before is dropped
    if (provider?.has_key || provider?.lists_freely) void lookUp(id, undefined, provider.has_key);
  }

  // Asks the provider which models the key can use. A late answer to an earlier look-up, for a
  // provider no longer picked or a key since replaced, is dropped (a review on PR #115).
  async function lookUp(id: string, typedKey?: string, savedKey = false) {
    const asked = (asking.current += 1);
    setModels({ state: "loading" });
    const started = performance.now();
    try {
      const ids = await listModels(id, typedKey);
      if (asking.current !== asked) return;
      console.info(`Listed ${ids.length} models for ${id} (${Math.round(performance.now() - started)} ms)`);
      setModels({ state: "listed", ids, checked: Boolean(typedKey) || savedKey });
    } catch (e) {
      if (asking.current !== asked) return;
      console.error(`Could not list the models for ${id}`, e);
      const refused = e instanceof ServerRefusal && e.status < 500;
      const error = e instanceof ServerRefusal ? e.message : "The models couldn't be listed.";
      setModels({ state: "failed", error, unreachable: !refused });
    }
  }

  async function use() {
    setSaving(true);
    setError(null);
    setSaved(false);
    const started = performance.now();
    try {
      const local = picked === "local";
      const typed = key.trim();
      const now = await chooseLlm({
        provider: picked,
        ...(typed && !local ? { api_key: typed } : {}),
        ...(local ? {} : { model }),
      });
      console.info(`LLM changed to ${picked} (${Math.round(performance.now() - started)} ms)`);
      setSetting(now);
      setKey("");
      setSaved(true);
      // A key just saved was checked by the server, so its models can be offered now.
      if (!local && (typed || models?.state !== "listed")) void lookUp(picked, undefined, true);
    } catch (e) {
      console.error(`Could not change the LLM to ${picked}`, e);
      setError(e instanceof ServerRefusal ? e.message : "The LLM could not be changed. Try again.");
    }
    setSaving(false);
  }

  const current = setting?.providers.find((p) => p.id === setting.provider);
  const chosen: LlmProvider | undefined = setting?.providers.find((p) => p.id === picked);
  const showModel =
    chosen?.lists_freely || models?.state === "listed" || (models?.state === "failed" && models.unreachable);

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
                  onInput={(e) => {
                    setKey((e.target as HTMLInputElement).value);
                    setError(null); // a refused key's message goes once another is typed
                  }}
                  onBlur={() => key.trim() && void lookUp(chosen.id, key.trim())}
                  disabled={saving}
                />
              </label>
              {showModel && (
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
              )}
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
  if (models === null) return `Enter your key to choose one of ${provider.label}'s models.`;
  if (models.state === "loading") return `Looking up ${provider.label}'s models…`;
  if (models.state === "failed") {
    return models.unreachable ? `${models.error} You can still type a model's name.` : models.error;
  }
  const n = models.ids.length;
  const available = `${n} model${n === 1 ? "" : "s"} available: pick one or type a name.`;
  // Listing the models with a key needs one the provider accepts, so such a list means it works.
  const listed = models.checked ? `The key works. ${available}` : available;
  if (!models.ids.includes(model)) return `${listed} ${model} isn't in ${provider.label}'s list for this key.`;
  return `${listed} ${blank}`;
}
