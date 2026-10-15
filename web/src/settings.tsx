// The Settings menu in the top bar (roadmap R41a) and the settings every page can read. Anyone
// can change them for now; R44's sign-on restricts them later, and R27's Settings page takes
// the menu over.

import type { ComponentChildren } from "preact";
import { createContext } from "preact";
import { useContext, useEffect, useRef, useState } from "preact/hooks";

import { changeSettings, DEFAULT_SETTINGS, getSettings, type UiSettings, type View } from "./api";

interface Shared {
  settings: UiSettings;
  loaded: boolean; // the server has answered, or couldn't
  change: (changes: Partial<UiSettings>) => Promise<void>;
}

export const SettingsContext = createContext<Shared>({
  settings: DEFAULT_SETTINGS,
  loaded: true,
  change: async () => {},
});

// The settings as saved on the server: the defaults until it answers, or if it can't.
export function useSettings(): UiSettings {
  return useContext(SettingsContext).settings;
}

// Whether the settings have been read, so a page the view hides isn't shown first (R41b).
export function useSettingsLoaded(): boolean {
  return useContext(SettingsContext).loaded;
}

export function SettingsProvider({ children }: { children: ComponentChildren }) {
  const [settings, setSettings] = useState<UiSettings>(DEFAULT_SETTINGS);
  const [loaded, setLoaded] = useState(false);
  const changed = useRef(false); // a change was saved, so the first read is out of date

  useEffect(() => {
    getSettings()
      .then((read) => changed.current || setSettings(read))
      .catch((e: unknown) => console.error("Could not load the settings", e))
      .finally(() => setLoaded(true));
  }, []);

  async function change(changes: Partial<UiSettings>) {
    const started = performance.now();
    const saved = await changeSettings(changes);
    changed.current = true;
    setSettings(saved);
    const took = Math.round(performance.now() - started);
    console.info(`Settings changed: ${JSON.stringify(changes)} (${took} ms)`);
  }

  return <SettingsContext.Provider value={{ settings, loaded, change }}>{children}</SettingsContext.Provider>;
}

const VIEWS: [View, string, string][] = [
  ["teacher", "Teacher", "every page and option"],
  ["student", "Student", "the chat and a read-only wiki"],
];

export function SettingsMenu() {
  const { settings, loaded, change } = useContext(SettingsContext);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  // Saves the change; if it can't be saved, says so and `undo` puts the box back as it was.
  async function save(changes: Partial<UiSettings>, undo: () => void) {
    setFailed(false);
    try {
      await change(changes);
    } catch (e) {
      console.error(`Could not change the settings ${JSON.stringify(changes)}`, e);
      setFailed(true);
      undo();
    }
  }

  function chooseView(view: View) {
    const was = settings.view;
    save({ view }, () => {
      const box = menu.current?.querySelector<HTMLInputElement>(`input[value="${was}"]`);
      if (box) box.checked = true;
    });
  }

  return (
    <div className="settings">
      <button
        type="button"
        className="link"
        aria-expanded={open}
        aria-controls="settings-menu"
        disabled={!loaded} // a change before the first read could be undone by it (PR #77 review)
        onClick={() => setOpen(!open)}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
          <circle cx="16" cy="7" r="2" />
          <circle cx="10" cy="17" r="2" />
        </svg>
        Settings
      </button>
      {open && (
        <div
          id="settings-menu"
          ref={menu}
          className="settings-menu"
          role="group"
          aria-label="Settings"
        >
          <fieldset>
            <legend>View</legend>
            {VIEWS.map(([view, label, about]) => (
              <label key={view} className="choice">
                <input
                  type="radio"
                  name="view"
                  value={view}
                  checked={settings.view === view}
                  onChange={() => chooseView(view)}
                />{" "}
                <span>
                  {label}
                  <span className="muted"> · {about}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <label>
            <input
              type="checkbox"
              checked={settings.show_metrics}
              onChange={(e) => {
                const box = e.currentTarget;
                save({ show_metrics: box.checked }, () => (box.checked = !box.checked));
              }}
            />{" "}
            Show timing metrics
          </label>
          <p className="muted">
            How long replies and other steps take, under the video and on the pages.
          </p>
          <label>
            <input
              type="checkbox"
              checked={settings.teach_me}
              onChange={(e) => {
                const box = e.currentTarget;
                save({ teach_me: box.checked }, () => (box.checked = !box.checked));
              }}
            />{" "}
            Teach me
          </label>
          <p className="muted">
            A Teach me button in the chat that teaches the content a part at a time.
          </p>
          <label>
            <input
              type="checkbox"
              checked={settings.quiz_me}
              onChange={(e) => {
                const box = e.currentTarget;
                save({ quiz_me: box.checked }, () => (box.checked = !box.checked));
              }}
            />{" "}
            Quiz me
          </label>
          <p className="muted">
            A Quiz me button in the chat that asks five questions on a topic and judges each
            answer.
          </p>
          <label>
            <input
              type="checkbox"
              checked={settings.assessment}
              onChange={(e) => {
                const box = e.currentTarget;
                save({ assessment: box.checked }, () => (box.checked = !box.checked));
              }}
            />{" "}
            Assessment
          </label>
          <p className="muted">
            An Assessment button in the chat that asks questions across all the content, then
            says how broad and deep your knowledge is.
          </p>
          <label>
            <input
              type="checkbox"
              checked={settings.debug}
              onChange={(e) => {
                const box = e.currentTarget;
                save({ debug: box.checked }, () => (box.checked = !box.checked));
              }}
            />{" "}
            Debug
          </label>
          <p className="muted">
            Copy chat under the conversation, to paste the latest exchanges somewhere else.
          </p>
          {failed && <p className="error">The setting could not be changed. Try again.</p>}
        </div>
      )}
    </div>
  );
}
