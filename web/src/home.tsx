// The home page: where to go next. Once setup is done (the sample video was accepted), Chat and
// Manage Content stand beside Setup as equal choices, and a return visit to the app's address
// goes straight to the chat (roadmap R30).

import { useEffect, useState } from "preact/hooks";

import { DEFAULT_PICTURE, getPhotoChoice, getReview, getStartNow, uploadUrl } from "./api";

// The setup wizard (R131).
export const WIZARD = "#/setup/wizard";

interface Choice {
  href: string;
  title: string;
  text: string;
}

// What the home page knows once the server has answered: whether setup is done, and the photo
// the video is made from (null when there is none yet).
export interface HomeState {
  done: boolean;
  photo: string | null;
  defaultPerson?: boolean; // the person is a default one (R24c)
}

// With a default person chosen (R24c), setup is done. Otherwise, before consent, setup can't be
// done and the server refuses the setup reads, so none are made.
export async function loadHome(consented: boolean): Promise<HomeState> {
  try {
    if ((await getStartNow()).chosen) {
      console.info("Home loaded (a default person is chosen)");
      return { done: true, photo: DEFAULT_PICTURE, defaultPerson: true };
    }
  } catch (e) {
    console.error("Could not read the default person", e);
  }
  if (!consented) {
    console.info("Home loaded (setup not started: no consent yet)");
    return { done: false, photo: null };
  }
  const started = performance.now();
  try {
    const [review, choice] = await Promise.all([getReview(), getPhotoChoice()]);
    const state = {
      done: review.accepted,
      photo: review.accepted && choice.id ? uploadUrl("photos", choice.id) : null,
    };
    console.info(
      `Home loaded in ${Math.round(performance.now() - started)} ms (setup ${state.done ? "done" : "not done"})`,
    );
    return state;
  } catch (e) {
    console.error("Could not load the home page's setup state", e);
    return { done: false, photo: null };
  }
}

// Where Setup goes, on the home page and in the top bar alike: with a ready-made avatar in use
// (R24c), to Start now to choose another or use your own photo and voice; before consent, to the
// consent page; otherwise to setup.
export function setupLink(consented: boolean, defaultPerson = false): string {
  if (defaultPerson) return "#/start-now";
  return consented ? "#/setup" : "#/consent";
}

export function choices(done: boolean, consented: boolean, defaultPerson = false): Choice[] {
  const setupHref = setupLink(consented);
  if (!done) {
    return [
      {
        href: "#/start-now",
        title: "Start now",
        text: "Chat at once with a ready-made avatar: a made-up person in a ready-made voice.",
      },
      {
        href: setupHref,
        title: "Start setup",
        text: "Add photos and voice recordings, then review a sample video of the person speaking.",
      },
    ];
  }
  return [
    {
      href: "#/chat",
      title: "Chat",
      text: "Ask a question. The person answers in their own voice and face.",
    },
    {
      href: "#/content",
      title: "Manage Content",
      text: "Add, replace or remove the PDFs that answers come from.",
    },
    defaultPerson
      ? {
          href: setupLink(consented, true),
          title: "Setup",
          text: "Choose another ready-made avatar, or use your own photo and voice.",
        }
      : {
          href: setupHref,
          title: "Setup",
          text: "Change the photos, the voice recordings or the accent.",
        },
  ];
}

// `landing` is set when the visit started here, at the app's address with no page: once setup
// is done and saved, the chat opens instead, with the conversation kept on the server. Home,
// opened from the top bar, still shows the choices.
export function HomePage({ consented, landing = false }: { consented: boolean; landing?: boolean }) {
  // null until the server has answered.
  const [state, setState] = useState<HomeState | null>(null);
  useEffect(() => {
    // Once home is left, an answer arriving late changes nothing: it mustn't take the user away
    // from the page they chose (review on PR #108).
    let active = true;
    void loadHome(consented).then((loaded) => {
      if (!active) return;
      if (landing && loaded.done) {
        console.info("Setup is saved, so the visit starts in the chat");
        window.location.replace("#/chat");
        return;
      }
      setState(loaded);
    });
    return () => {
      active = false;
    };
  }, [consented]);

  if (state === null) return <p className="muted busy">Loading…</p>;
  return (
    <section className="home">
      <div className="hero">
        {state.photo && <img className="portrait" src={state.photo} alt="The person in the video" />}
        <div>
          <h1>{state.done ? "Welcome back" : "Welcome"}</h1>
          <p className="muted">
            {state.done
              ? "Setup is done. Pick up where you left off."
              : "Make a talking video of a person from a few photos and voice recordings. The person then speaks the chatbot's replies."}
          </p>
        </div>
      </div>
      <ul className={state.done ? "choices three" : "choices two"}>
        {choices(state.done, consented, state.defaultPerson).map((c) => (
          <li key={c.title}>
            <a href={c.href}>
              <ChoiceIcon href={c.href} />
              <span className="title">{c.title}</span>
              <span className="text">{c.text}</span>
            </a>
          </li>
        ))}
      </ul>
      {!state.done && (
        <p className="wizard-link">
          <a href={WIZARD}>Set up with your own photo and voice</a>, one step at a time.
        </p>
      )}
    </section>
  );
}

// A small picture for each choice (R41e2): a speech bubble for the chat, a page for the
// content, and sliders for setup.
const ICONS: Record<string, string> = {
  "#/chat": "M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v6a2.5 2.5 0 0 1-2.5 2.5H11l-4 3.5V15h0.5A2.5 2.5 0 0 1 5 12.5z",
  "#/content": "M7 3.5h6.5L18 8v12.5H7zM13.5 3.5V8H18M9.5 12h6M9.5 15.5h6",
  "#/start-now": "M12 4a3.5 3.5 0 1 1 0 7a3.5 3.5 0 0 1 0-7zM5 20a7 7 0 0 1 14 0",
  setup: "M4 7h10M18 7h2M4 17h4M12 17h8M16 5v4M10 15v4",
};

function ChoiceIcon({ href }: { href: string }) {
  return (
    <span className="icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round">
        <path d={ICONS[href] ?? ICONS.setup} />
      </svg>
    </span>
  );
}
