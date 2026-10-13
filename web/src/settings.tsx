// The Settings menu in the top bar (roadmap R41a) and the settings every page can read. Anyone
// can change them for now; R44's sign-on restricts them later, and R27's Settings page takes
// the menu over.

import type { ComponentChildren } from "preact";
import { createContext } from "preact";
import { useContext, useEffect, useState } from "preact/hooks";

import { changeSettings, DEFAULT_SETTINGS, getSettings, type UiSettings } from "./api";

interface Shared {
  settings: UiSettings;
  change: (changes: Partial<UiSettings>) => Promise<void>;
}

const Settings = createContext<Shared>({
  settings: DEFAULT_SETTINGS,
  change: async () => {},
});

// The settings as saved on the server: the defaults until it answers, or if it can't.
export function useSettings(): UiSettings {
  return useContext(Settings).settings;
}

export function SettingsProvider({ children }: { children: ComponentChildren }) {
  const [settings, setSettings] = useState<UiSettings>(DEFAULT_SETTINGS);

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch((e: unknown) => console.error("Could not load the settings", e));
  }, []);

  async function change(changes: Partial<UiSettings>) {
    const started = performance.now();
    const saved = await changeSettings(changes);
    setSettings(saved);
    const took = Math.round(performance.now() - started);
    console.info(`Settings changed: ${JSON.stringify(changes)} (${took} ms)`);
  }

  return <Settings.Provider value={{ settings, change }}>{children}</Settings.Provider>;
}

export function SettingsMenu() {
  const { settings, change } = useContext(Settings);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  async function toggle(name: keyof UiSettings, box: HTMLInputElement) {
    const on = box.checked;
    setFailed(false);
    try {
      await change({ [name]: on });
    } catch (e) {
      console.error(`Could not change the setting ${name}`, e);
      setFailed(true);
      box.checked = !on; // the setting stays as it was
    }
  }

  return (
    <div className="settings">
      <button
        type="button"
        className="link"
        aria-expanded={open}
        aria-controls="settings-menu"
        onClick={() => setOpen(!open)}
      >
        Settings
      </button>
      {open && (
        <div id="settings-menu" className="settings-menu" role="group" aria-label="Settings">
          <label>
            <input
              type="checkbox"
              checked={settings.show_metrics}
              onChange={(e) => toggle("show_metrics", e.currentTarget)}
            />{" "}
            Show timing metrics
          </label>
          <p className="muted">
            How long replies and other steps take, under the video and on the pages.
          </p>
          {failed && <p className="error">The setting could not be changed. Try again.</p>}
        </div>
      )}
    </div>
  );
}
