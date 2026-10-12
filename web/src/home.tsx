// The home page: where to go next. Once setup is done (the sample video was accepted), Chat and
// Manage Content stand beside Setup as equal choices.

import { useEffect, useState } from "preact/hooks";

import { getPhotoChoice, getReview, uploadUrl } from "./api";

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
}

// Before consent, setup can't be done and the server refuses the setup reads, so none are made.
export async function loadHome(consented: boolean): Promise<HomeState> {
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

export function choices(done: boolean, consented: boolean): Choice[] {
  const setupHref = consented ? "#/setup" : "#/consent";
  if (!done) {
    return [
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
    {
      href: setupHref,
      title: "Setup",
      text: "Change the photos, the voice recordings or the accent.",
    },
  ];
}

export function HomePage({ consented }: { consented: boolean }) {
  // null until the server has answered.
  const [state, setState] = useState<HomeState | null>(null);
  useEffect(() => {
    void loadHome(consented).then(setState);
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
      <ul className={state.done ? "choices three" : "choices"}>
        {choices(state.done, consented).map((c) => (
          <li key={c.title}>
            <a href={c.href}>
              <span className="title">{c.title}</span>
              <span className="text">{c.text}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
