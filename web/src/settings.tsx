// The Settings page (roadmap R27), its link in the top bar, and the settings every page can read.
// Anyone can change them for now; R44's sign-on restricts them later. The page took over R41a's
// Settings menu.

import type { ComponentChildren } from "preact";
import { createContext } from "preact";
import { useContext, useEffect, useRef, useState } from "preact/hooks";

import { changeSettings, DEFAULT_SETTINGS, getSettings, type UiSettings, type View } from "./api";
import { ChangeSetup } from "./change-setup";
import { DeleteData } from "./delete-data";
import { VideoAndChat } from "./video-and-chat";
import { YourFiles } from "./your-files";

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

// The on and off settings, in the order shown, each with what it does.
type Switch = "general_prompts" | "teach_me" | "quiz_me" | "assessment" | "show_metrics" | "debug";
const SWITCHES: { group: string; about: string; items: [Switch, string, string][] }[] = [
  {
    group: "Chat",
    about: "What the person in the video answers, and the buttons under the prompt box.",
    items: [
      [
        "general_prompts",
        "Answer questions outside the content",
        "Off: a question the PDFs don't cover gets a short, polite reply instead of an answer.",
      ],
      ["teach_me", "Teach me", "A Teach me button that teaches the content a part at a time."],
      [
        "quiz_me",
        "Quiz me",
        "A Quiz me button that asks five questions on a topic and judges each answer.",
      ],
      [
        "assessment",
        "Assessment",
        "An Assessment button that asks questions across all the content, then says how broad " +
          "and deep your knowledge is.",
      ],
    ],
  },
  {
    group: "Display",
    about: "What else is shown on the pages.",
    items: [
      [
        "show_metrics",
        "Show timing metrics",
        "How long replies and other steps take, under the video and on the pages.",
      ],
      [
        "debug",
        "Debug",
        "Copy chat under the conversation, to paste the latest exchanges somewhere else.",
      ],
    ],
  },
];

const ICON = (
  <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
    <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
    <circle cx="16" cy="7" r="2" />
    <circle cx="10" cy="17" r="2" />
  </svg>
);

// The Settings link in the top bar, on every page (item 8).
export function SettingsLink({ current }: { current: boolean }) {
  return (
    <a href="#/settings" className={current ? "settings-link current" : "settings-link"}>
      {ICON}
      Settings
    </a>
  );
}

// The Settings page. `back` is the page it was opened from, which Return to the app goes back to.
export function SettingsPage({ back }: { back: string }) {
  const { settings, change } = useContext(SettingsContext);
  const [failed, setFailed] = useState(false);
  const page = useRef<HTMLDivElement>(null);

  useEffect(() => console.info(`Settings page opened, returning to ${back}`), [back]);

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
      const box = page.current?.querySelector<HTMLInputElement>(`input[value="${was}"]`);
      if (box) box.checked = true;
    });
  }

  return (
    <div className="teacher-page settings-page" ref={page}>
      <h1>Settings</h1>
      <p className="lead">Changes are saved at once and kept after a restart.</p>
      {failed && <p className="error">The setting could not be changed. Try again.</p>}
      <section className="panel" aria-labelledby="settings-view">
        <h2 id="settings-view">View</h2>
        <p className="muted">Who the app is set out for.</p>
        <fieldset>
          <legend className="sr-only">View</legend>
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
      </section>
      {SWITCHES.map(({ group, about, items }) => (
        <section key={group} className="panel" aria-labelledby={`settings-${group}`}>
          <h2 id={`settings-${group}`}>{group}</h2>
          <p className="muted">{about}</p>
          {items.map(([name, label, help]) => (
            <div key={name} className="switch">
              <label>
                <input
                  type="checkbox"
                  checked={settings[name]}
                  onChange={(e) => {
                    const box = e.currentTarget;
                    save({ [name]: box.checked }, () => (box.checked = !box.checked));
                  }}
                />{" "}
                {label}
              </label>
              <p className="muted">{help}</p>
            </div>
          ))}
        </section>
      ))}
      <YourFiles />
      {/* Setup is the teacher's (R41b), so the student view has no way to change them. */}
      {settings.view === "teacher" && <ChangeSetup />}
      <VideoAndChat />
      {/* The photos and recordings are the teacher's (R41b), so only they can delete them. */}
      {settings.view === "teacher" && <DeleteData />}
      <p>
        <a className="button" href={back}>
          Return to the app
        </a>
      </p>
    </div>
  );
}
