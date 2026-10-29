// Push-to-talk (roadmap R24): hold the button, say the question, let go, and it is sent as if
// typed, unless the browser isn't sure it heard every word (R179). A quick click or tap instead
// keeps it listening until the button is clicked again. The browser's own speech recognition turns
// it into text; where the browser has none (Firefox), the button isn't shown.

import { useEffect, useRef, useState } from "preact/hooks";

// How long it keeps listening after the button is let go, so the last word, said as the button
// comes up, isn't cut off (Larry's "can you explain what Euler noticed about", 2026-10-15).
export const TAIL_MS = 600;

// Let go sooner than this and the press was a click or a tap, not a hold: it keeps listening
// until the button is clicked again. A touchpad tap lets go after about 80 ms, which sent nothing
// and said "I didn't hear anything" (Larry, 2026-10-19).
export const TAP_MS = 400;

// The browser is less sure than this (0 to 1) of a phrase it heard: perhaps a word was misheard
// ("Jill Biden" heard as "Joe Budden", Larry, 2026-10-28), so what was heard is left in the prompt
// box to check and send, not sent (R179). Speech heard clearly is sent as before.
export const SURE = 0.8;

// One way the browser heard a phrase, and how sure it is of it: Chrome gives 0 while the phrase
// is still changing, and some engines always.
export interface Heard {
  transcript: string;
  confidence?: number;
}
type Results = ArrayLike<ArrayLike<Heard>>;

// The part of the Web Speech API used here; TypeScript's DOM types don't include it.
export interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: { results: Results }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

type RecognitionMaker = new () => Recognition;

// The browser's speech recognition, or null when it has none.
export function speechRecognition(): RecognitionMaker | null {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionMaker;
    webkitSpeechRecognition?: RecognitionMaker;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

// What to tell the person when recognition fails, by its error code.
export function talkProblem(error: string): string | null {
  if (error === "aborted") return null; // stopped on purpose
  if (error === "no-speech") return "I didn't hear anything. Hold the button while you speak.";
  if (error === "not-allowed" || error === "service-not-allowed") {
    return "The browser isn't allowed to use the microphone. Allow it in the address bar.";
  }
  if (error === "audio-capture") return "No microphone was found.";
  return "Speech recognition didn't work. Try again, or type your question.";
}

// Everything heard so far, the final and the still-changing parts together.
export function heard(results: Results): string {
  return Array.from(results, (r) => r[0]?.transcript ?? "")
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

// How sure the browser is of the phrase it is least sure of, or null when it didn't say (each
// phrase came with 0 or nothing).
export function leastSure(results: Results): number | null {
  const known = Array.from(results, (r) => r[0]?.confidence ?? 0).filter((c) => c > 0);
  return known.length ? Math.min(...known) : null;
}

export function TalkButton(props: {
  disabled: boolean;
  onHearing: (text: string) => void; // shown in the prompt box while speaking
  onHeard: (text: string) => void; // sent when the button is let go
  onUnsure: (text: string) => void; // let go, but perhaps misheard: left in the box to check
  onEdit: (text: string) => void; // Edit clicked while listening: left in the box to change
  onProblem: (problem: string | null) => void;
}) {
  const Maker = speechRecognition();
  const [listening, setListening] = useState(false);
  const recognition = useRef<Recognition | null>(null);
  const said = useRef("");
  const sure = useRef<number | null>(null);
  const started = useRef(0);
  const failed = useRef(false);
  const stopping = useRef<number | null>(null);
  // Set when the button is let go: what was heard is sent only then, not when recognition
  // fails, ends on its own while held or the page is left (review on PR #91).
  const sending = useRef(false);
  // Set when the button was tapped rather than held: listening until it is clicked again.
  const [tapped, setTapped] = useState(false);
  const latched = useRef(false);
  // Edit, shown right of the button while listening (R179): stops listening without sending.
  const editLink = useRef<HTMLButtonElement>(null);
  const editing = useRef(false);

  function clearTail() {
    if (stopping.current !== null) window.clearTimeout(stopping.current);
    stopping.current = null;
  }

  useEffect(
    () => () => {
      clearTail();
      sending.current = false;
      recognition.current?.stop();
    },
    [],
  );
  if (!Maker) return null;

  function start() {
    if (props.disabled || recognition.current || !Maker) return;
    const r = new Maker();
    r.lang = navigator.language || "en-US";
    r.continuous = true; // keeps listening while the button is held
    r.interimResults = true;
    said.current = "";
    sure.current = null;
    failed.current = false;
    sending.current = false;
    editing.current = false;
    latched.current = false;
    started.current = performance.now();
    r.onresult = (e) => {
      said.current = heard(e.results);
      sure.current = leastSure(e.results);
      props.onHearing(said.current);
    };
    r.onerror = (e) => {
      const problem = talkProblem(e.error);
      if (problem) {
        failed.current = true;
        console.error("Push-to-talk failed", e.error);
        props.onProblem(problem);
      }
    };
    r.onend = () => {
      recognition.current = null;
      clearTail();
      latched.current = false;
      setTapped(false);
      const send = sending.current && !failed.current;
      sending.current = false;
      setListening(false);
      const text = said.current;
      const ms = Math.round(performance.now() - started.current);
      const words = text.split(" ").filter(Boolean).length;
      console.info(`Push-to-talk: heard ${words} words in ${ms} ms`);
      if (!send) {
        // Not let go to send: what was heard stays in the prompt box, to send or change.
        if (text) console.info("Push-to-talk: ended without sending");
        if (editing.current && text) props.onEdit(text);
        return;
      }
      if (!text) {
        props.onProblem(talkProblem("no-speech"));
        return;
      }
      const confidence = sure.current === null ? "not given" : sure.current.toFixed(2);
      if (sure.current !== null && sure.current < SURE) {
        console.info(
          `Push-to-talk: not sure of the words (confidence ${confidence}), left to check`,
        );
        props.onUnsure(text);
        return;
      }
      console.info(`Push-to-talk: sent (confidence ${confidence})`);
      props.onHeard(text);
    };
    recognition.current = r;
    props.onProblem(null);
    setListening(true);
    console.info("Push-to-talk: listening");
    try {
      r.start();
    } catch (e) {
      console.error("Push-to-talk could not start", e);
      recognition.current = null;
      setListening(false);
      props.onProblem(talkProblem("start"));
    }
  }

  function stop() {
    if (!recognition.current || stopping.current !== null) return;
    sending.current = true; // let go: sent when listening ends, even before the tail is up
    stopping.current = window.setTimeout(() => {
      stopping.current = null;
      recognition.current?.stop(); // what was heard is sent when it ends
    }, TAIL_MS);
  }

  // Pressed: starts listening, or, after a tap, sends.
  function press() {
    if (!recognition.current) {
      start();
      return;
    }
    if (latched.current) {
      latched.current = false;
      setTapped(false);
      stop();
    }
  }

  // Let go: sends, unless it was only a tap.
  // Edit: stops listening and sends nothing; what was heard stays in the box to change.
  function edit() {
    if (!recognition.current) return;
    clearTail();
    sending.current = false;
    editing.current = true;
    latched.current = false;
    setTapped(false);
    console.info("Push-to-talk: Edit chosen; left in the box to change");
    recognition.current.stop();
  }

  // Whether the pointer was let go over Edit: a held button is slid there to edit, not send.
  function overEdit(e: { clientX: number; clientY: number }): boolean {
    const box = editLink.current?.getBoundingClientRect();
    if (!box || box.width === 0) return false;
    const { clientX: x, clientY: y } = e;
    return x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
  }

  function release() {
    if (!recognition.current || latched.current || stopping.current !== null) return;
    const ms = Math.round(performance.now() - started.current);
    if (ms < TAP_MS) {
      latched.current = true;
      setTapped(true);
      console.info(`Push-to-talk: let go after ${ms} ms; listening until clicked again`);
      return;
    }
    stop();
  }

  return (
    <div className="talk-row">
      <button
        type="button"
        className={listening ? "secondary talk listening" : "secondary talk"}
        disabled={props.disabled && !listening}
        aria-pressed={listening}
        onPointerDown={(e) => {
          e.preventDefault();
          // Kept until let go, so the button growing or moving under the pointer doesn't end it.
          e.currentTarget.setPointerCapture?.(e.pointerId);
          press();
        }}
        onPointerUp={(e) => (overEdit(e) ? edit() : release())}
        // The browser took the pointer over: stopped, never kept on as a tap (review on PR #113).
        onPointerCancel={stop}
        onKeyDown={(e) => {
          if ((e.key === " " || e.key === "Enter") && !e.repeat) {
            e.preventDefault();
            press();
          }
        }}
        onKeyUp={(e) => {
          if (e.key === " " || e.key === "Enter") release();
        }}
      >
        {!listening ? "Hold to talk" : tapped ? "Click to send or…" : "Let go to send or…"}
      </button>
      {listening && (
        <button ref={editLink} type="button" className="link" onClick={edit}>
          Edit
        </button>
      )}
    </div>
  );
}
