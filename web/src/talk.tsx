// Push-to-talk (roadmap R24): hold the button, say the question, let go, and it is sent as if
// typed. The browser's own speech recognition turns it into text; where the browser has none
// (Firefox), the button isn't shown.

import { useEffect, useRef, useState } from "preact/hooks";

// The part of the Web Speech API used here; TypeScript's DOM types don't include it.
export interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
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
export function heard(results: ArrayLike<ArrayLike<{ transcript: string }>>): string {
  return Array.from(results, (r) => r[0]?.transcript ?? "")
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

export function TalkButton(props: {
  disabled: boolean;
  onHearing: (text: string) => void; // shown in the prompt box while speaking
  onHeard: (text: string) => void; // sent when the button is let go
  onProblem: (problem: string | null) => void;
}) {
  const Maker = speechRecognition();
  const [listening, setListening] = useState(false);
  const recognition = useRef<Recognition | null>(null);
  const said = useRef("");
  const started = useRef(0);
  const failed = useRef(false);

  useEffect(() => () => recognition.current?.stop(), []);
  if (!Maker) return null;

  function start() {
    if (props.disabled || recognition.current || !Maker) return;
    const r = new Maker();
    r.lang = navigator.language || "en-US";
    r.continuous = true; // keeps listening while the button is held
    r.interimResults = true;
    said.current = "";
    failed.current = false;
    started.current = performance.now();
    r.onresult = (e) => {
      said.current = heard(e.results);
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
      setListening(false);
      const text = said.current;
      const ms = Math.round(performance.now() - started.current);
      const words = text.split(" ").filter(Boolean).length;
      console.info(`Push-to-talk: heard ${words} words in ${ms} ms`);
      if (text) props.onHeard(text);
      else if (!failed.current) props.onProblem(talkProblem("no-speech"));
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
    recognition.current?.stop(); // what was heard is sent when it ends
  }

  return (
    <button
      type="button"
      className={listening ? "secondary talk listening" : "secondary talk"}
      disabled={props.disabled && !listening}
      aria-pressed={listening}
      onPointerDown={(e) => {
        e.preventDefault();
        start();
      }}
      onPointerUp={stop}
      onPointerLeave={stop}
      onPointerCancel={stop}
      onKeyDown={(e) => {
        if ((e.key === " " || e.key === "Enter") && !e.repeat) {
          e.preventDefault();
          start();
        }
      }}
      onKeyUp={(e) => {
        if (e.key === " " || e.key === "Enter") stop();
      }}
    >
      {listening ? "Listening… let go to send" : "Hold to talk"}
    </button>
  );
}
