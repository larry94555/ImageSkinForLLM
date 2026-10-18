// The exit screen (roadmap R29): shown after the person says "Goodbye.", with Start again,
// which goes back to the chat, where they say "Welcome back." The conversation is kept.

import { useEffect } from "preact/hooks";

export function ExitScreen({ onStartAgain }: { onStartAgain: () => void }) {
  useEffect(() => console.info("Exit screen shown"), []);
  return (
    <section className="exit-screen">
      <h1>Goodbye</h1>
      <p className="muted">You have left the chat. Your conversation is kept for when you return.</p>
      <button
        type="button"
        onClick={() => {
          console.info("Start again");
          onStartAgain();
        }}
      >
        Start again
      </button>
    </section>
  );
}
